import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.research import router as research_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.session import (
    create_database_engine,
    create_session_factory,
)
from app.services.research.execution import (
    ResearchExecutionService,
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

    engine = create_database_engine()
    session_factory = create_session_factory(
        engine,
    )
    research_store = PostgresResearchRunStore(
        session_factory,
    )
    application.state.research_execution_service = ResearchExecutionService(
        research_store,
    )

    logger.info("Application started")

    try:
        yield
    finally:
        await engine.dispose()
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
