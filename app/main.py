import logging
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager

from fastapi import FastAPI

from app.api.research import router as research_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import (
    create_database_engine,
    create_session_factory,
)
from app.services.cache import (
    RedisConnection,
    RedisResearchIdempotencyLockManager,
    RedisResearchIdempotencyStore,
    RedisResearchResultCache,
)
from app.services.research.execution import (
    ResearchExecutionService,
)
from app.services.research.idempotency import (
    IdempotentResearchExecutionService,
)
from app.services.research.postgres import (
    PostgresResearchRunStore,
)

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

        session_factory = create_session_factory(
            engine,
        )
        research_store = PostgresResearchRunStore(
            session_factory,
        )
        result_cache = RedisResearchResultCache(
            redis_connection,
        )
        idempotency_store = RedisResearchIdempotencyStore(
            redis_connection,
        )
        idempotency_lock_manager = RedisResearchIdempotencyLockManager(
            redis_connection,
        )
        execution_service = ResearchExecutionService(
            research_store,
            result_cache=result_cache,
        )

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

app.include_router(
    research_router,
)


@app.get("/health")
def health_check() -> dict[str, str]:
    """Return the current health status of the API service."""

    logger.info("Health check requested")

    return {
        "status": "healthy",
        "environment": settings.app_env,
    }
