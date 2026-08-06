import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from functools import partial

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.agents.local_scout import LocalScoutAgent
from app.api.auth import router as auth_router
from app.api.documents import router as documents_router
from app.api.operations import router as operations_router
from app.api.research import router as research_router
from app.core.config import parse_cors_allowed_origins, settings
from app.core.correlation import CorrelationIdMiddleware
from app.core.logging import configure_logging
from app.db.session import (
    create_database_engine,
    create_session_factory,
)
from app.services.auth import AuthService
from app.services.cache import (
    RedisConnection,
    RedisResearchIdempotencyLockManager,
    RedisResearchIdempotencyStore,
    RedisResearchProgressStore,
    RedisResearchRateLimiter,
    RedisResearchResultCache,
)
from app.services.embeddings.factory import create_embedding_client
from app.services.knowledge import KnowledgeDocumentService, PostgresKnowledgeDocumentStore
from app.services.knowledge.indexing import KnowledgeIndexer
from app.services.knowledge.retrieval import PrivateKnowledgeRetriever
from app.services.mcp import MCPReferenceScout
from app.services.readiness import ApplicationReadinessService
from app.services.research.checkpointing import open_langgraph_checkpointer
from app.services.research.execution import (
    ResearchExecutionService,
    create_default_workflow,
)
from app.services.research.idempotency import (
    IdempotentResearchExecutionService,
)
from app.services.research.jobs import ResearchJobManager
from app.services.research.postgres import (
    PostgresResearchDurabilityStore,
    PostgresResearchRunStore,
)
from app.services.research.reports import PostgresResearchReportStore
from app.services.storage import create_document_storage
from app.services.vector_store.factory import create_vector_store

configure_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(
    application: FastAPI,
) -> AsyncIterator[None]:
    """Initialize and dispose application-scoped resources."""

    async with AsyncExitStack() as resource_stack:
        engine = create_database_engine()
        resource_stack.push_async_callback(
            engine.dispose,
        )

        redis_connection = RedisConnection.from_url()
        resource_stack.push_async_callback(
            redis_connection.close,
        )
        application.state.readiness_service = ApplicationReadinessService(
            engine,
            redis_connection,
        )

        embedding_client = create_embedding_client()
        resource_stack.push_async_callback(
            embedding_client.close,
        )
        vector_store = create_vector_store(dimensions=embedding_client.dimensions)
        resource_stack.push_async_callback(
            vector_store.close,
        )
        local_scout = LocalScoutAgent(
            PrivateKnowledgeRetriever(
                embedding_client,
                vector_store,
            )
        )

        session_factory = create_session_factory(
            engine,
        )
        checkpointer = await resource_stack.enter_async_context(
            open_langgraph_checkpointer(settings.database_url)
        )
        document_storage = create_document_storage()
        resource_stack.push_async_callback(document_storage.close)
        application.state.knowledge_document_service = KnowledgeDocumentService(
            PostgresKnowledgeDocumentStore(session_factory),
            document_storage,
            KnowledgeIndexer(embedding_client, vector_store),
            vector_store,
            max_upload_bytes=settings.document_max_upload_bytes,
        )
        application.state.auth_service = AuthService(
            session_factory,
            session_ttl_seconds=settings.session_ttl_seconds,
        )

        research_store = PostgresResearchRunStore(
            session_factory,
        )
        application.state.research_run_store = research_store
        application.state.research_report_store = PostgresResearchReportStore(
            session_factory,
        )
        result_cache = RedisResearchResultCache(
            redis_connection,
        )
        progress_store = RedisResearchProgressStore(
            redis_connection,
        )
        application.state.research_progress_store = progress_store
        idempotency_store = RedisResearchIdempotencyStore(
            redis_connection,
        )
        idempotency_lock_manager = RedisResearchIdempotencyLockManager(
            redis_connection,
        )
        application.state.research_rate_limiter = RedisResearchRateLimiter(
            redis_connection,
        )
        if settings.mcp_endpoint.strip():
            mcp_scout = MCPReferenceScout(
                settings.mcp_endpoint,
                server_name=settings.mcp_server_name,
            )
            workflow_factory = partial(
                create_default_workflow,
                local_scout=local_scout,
                mcp_scout=mcp_scout,
                checkpointer=checkpointer,
            )
        else:
            workflow_factory = partial(
                create_default_workflow,
                local_scout=local_scout,
                checkpointer=checkpointer,
            )

        execution_service = ResearchExecutionService(
            research_store,
            workflow_factory,
            result_cache=result_cache,
            progress_store=progress_store,
        )
        research_job_manager = ResearchJobManager(
            execution_service,
            PostgresResearchDurabilityStore(session_factory),
            lease_ttl_seconds=settings.research_worker_lease_ttl_seconds,
            heartbeat_seconds=settings.research_worker_heartbeat_seconds,
        )
        resource_stack.push_async_callback(
            research_job_manager.close,
        )
        await research_job_manager.start()
        application.state.research_job_manager = research_job_manager

        application.state.research_execution_service = IdempotentResearchExecutionService(
            execution_service,
            idempotency_store,
            idempotency_lock_manager,
        )

        logger.info("Application started")

        yield

    logger.info("Application stopped")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(CorrelationIdMiddleware)

cors_allowed_origins = parse_cors_allowed_origins(settings.cors_allowed_origins)
if cors_allowed_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-Correlation-ID",
            "X-RateLimit-Limit",
            "X-RateLimit-Remaining",
            "X-RateLimit-Reset",
        ],
    )

app.include_router(
    auth_router,
)
app.include_router(
    research_router,
)
app.include_router(
    documents_router,
)
app.include_router(operations_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Return the current health status of the API service."""

    logger.info("Health check requested")

    return {
        "status": "healthy",
        "environment": settings.app_env,
    }
