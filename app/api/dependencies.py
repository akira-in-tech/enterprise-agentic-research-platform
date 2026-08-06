from typing import Annotated, cast

from fastapi import Depends, HTTPException, Request, status

from app.core.config import settings
from app.services.auth import AuthService, ResolvedSession
from app.services.cache import RedisResearchProgressStore, RedisResearchRateLimiter
from app.services.knowledge import KnowledgeDocumentService
from app.services.readiness import ApplicationReadinessService
from app.services.research.idempotency import (
    IdempotentResearchExecutionService,
)
from app.services.research.jobs import ResearchJobManager
from app.services.research.postgres import PostgresResearchRunStore
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


def get_research_run_store(
    request: Request,
) -> PostgresResearchRunStore:
    """Return the application-scoped durable research-run reader."""

    try:
        run_store = request.app.state.research_run_store
    except AttributeError as error:
        raise RuntimeError("Research run store is not initialized.") from error

    return cast(PostgresResearchRunStore, run_store)


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


def get_auth_service(
    request: Request,
) -> AuthService:
    """Return the application-scoped authentication service."""

    try:
        service = request.app.state.auth_service
    except AttributeError as error:
        raise RuntimeError("Auth service is not initialized.") from error

    return cast(AuthService, service)


async def get_current_session(
    request: Request,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> ResolvedSession:
    """Resolve the caller's session cookie into a tenant user, or reject the request."""

    token = request.cookies.get(settings.session_cookie_name)

    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated.")

    resolved_session = await auth_service.resolve_session(token=token)

    if resolved_session is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated.")

    return resolved_session
