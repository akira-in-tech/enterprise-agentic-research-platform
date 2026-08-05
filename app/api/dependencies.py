from typing import cast

from fastapi import Request

from app.services.cache import RedisResearchProgressStore, RedisResearchRateLimiter
from app.services.knowledge import KnowledgeDocumentService
from app.services.readiness import ApplicationReadinessService
from app.services.research.idempotency import (
    IdempotentResearchExecutionService,
)
from app.services.research.jobs import ResearchJobManager
from app.services.research.reports import PostgresResearchReportStore


def get_research_execution_service(
    request: Request,
) -> IdempotentResearchExecutionService:
    """Return the application-scoped research service."""

    try:
        service = request.app.state.research_execution_service
    except AttributeError as error:
        raise RuntimeError("Research execution service is not initialized.") from error

    return cast(
        IdempotentResearchExecutionService,
        service,
    )


def get_research_rate_limiter(
    request: Request,
) -> RedisResearchRateLimiter:
    """Return the application-scoped research rate limiter."""

    try:
        rate_limiter = request.app.state.research_rate_limiter
    except AttributeError as error:
        raise RuntimeError("Research rate limiter is not initialized.") from error

    return cast(
        RedisResearchRateLimiter,
        rate_limiter,
    )


def get_research_progress_store(
    request: Request,
) -> RedisResearchProgressStore:
    """Return the application-scoped research progress store."""

    try:
        progress_store = request.app.state.research_progress_store
    except AttributeError as error:
        raise RuntimeError("Research progress store is not initialized.") from error

    return cast(
        RedisResearchProgressStore,
        progress_store,
    )


def get_research_report_store(
    request: Request,
) -> PostgresResearchReportStore:
    """Return the application-scoped durable report reader."""

    try:
        report_store = request.app.state.research_report_store
    except AttributeError as error:
        raise RuntimeError("Research report store is not initialized.") from error

    return cast(PostgresResearchReportStore, report_store)


def get_research_job_manager(
    request: Request,
) -> ResearchJobManager:
    """Return the application-scoped asynchronous job manager."""

    try:
        job_manager = request.app.state.research_job_manager
    except AttributeError as error:
        raise RuntimeError("Research job manager is not initialized.") from error

    return cast(ResearchJobManager, job_manager)


def get_knowledge_document_service(
    request: Request,
) -> KnowledgeDocumentService:
    """Return the application-scoped private-document service."""

    try:
        service = request.app.state.knowledge_document_service
    except AttributeError as error:
        raise RuntimeError("Knowledge document service is not initialized.") from error

    return cast(KnowledgeDocumentService, service)


def get_readiness_service(request: Request) -> ApplicationReadinessService:
    """Return the application-scoped dependency readiness checker."""

    try:
        service = request.app.state.readiness_service
    except AttributeError as error:
        raise RuntimeError("Readiness service is not initialized.") from error
    return cast(ApplicationReadinessService, service)
