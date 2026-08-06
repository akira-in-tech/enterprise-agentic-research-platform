import asyncio
import json
import time
from collections.abc import AsyncIterator
from typing import Annotated, cast
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Query,
    Response,
    status,
)
from fastapi.responses import StreamingResponse

from app.api.dependencies import (
    get_current_session,
    get_knowledge_document_service,
    get_research_execution_service,
    get_research_job_manager,
    get_research_progress_store,
    get_research_rate_limiter,
    get_research_report_export_service,
    get_research_report_store,
    get_research_run_store,
)
from app.db.models import ResearchRun
from app.schemas.intent import ResearchRoute
from app.schemas.progress import ResearchProgressRecord
from app.schemas.report import (
    ResearchReportExportResponse,
    ResearchReportResponse,
    ResearchReportSourceResponse,
)
from app.schemas.research import (
    CancelResearchRunResponse,
    CreateResearchJobResponse,
    CreateResearchRunRequest,
    CreateResearchRunResponse,
    PersistedLLMProvider,
    ResearchRunResponse,
    ResearchRunStatus,
)
from app.services.auth import ResolvedSession
from app.services.cache import (
    MAX_RESEARCH_IDEMPOTENCY_KEY_LENGTH,
    CacheUnavailableError,
    RedisResearchProgressStore,
    RedisResearchRateLimiter,
    ResearchRateLimitDecision,
    ResearchRateLimitUnavailableError,
)
from app.services.knowledge import (
    KnowledgeDocumentNotFoundError,
    KnowledgeDocumentNotReadyError,
    KnowledgeDocumentService,
)
from app.services.research.exports import ResearchReportExportService
from app.services.research.idempotency import (
    IdempotentResearchExecutionService,
    ResearchIdempotencyConflictError,
    ResearchIdempotencyInProgressError,
    ResearchIdempotencyUnavailableError,
)
from app.services.research.jobs import ResearchJobManager
from app.services.research.postgres import PostgresResearchRunStore
from app.services.research.reports import PostgresResearchReportStore
from app.services.storage import DocumentNotFoundError, DocumentStorageError

router = APIRouter(
    prefix="/research-runs",
    tags=[
        "research",
    ],
)


def _to_run_response(run: ResearchRun) -> ResearchRunResponse:
    return ResearchRunResponse(
        research_run_id=run.id,
        llm_provider=cast(PersistedLLMProvider, run.llm_provider),
        status=cast(ResearchRunStatus, run.status),
        query=run.query,
        route=cast("ResearchRoute | None", run.route),
        route_reason=run.route_reason,
        error_message=run.error_message,
        created_at=run.created_at,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


@router.get(
    "",
    response_model=list[ResearchRunResponse],
)
async def list_research_runs(
    current_session: Annotated[ResolvedSession, Depends(get_current_session)],
    run_store: Annotated[
        PostgresResearchRunStore,
        Depends(get_research_run_store),
    ],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> list[ResearchRunResponse]:
    """Return one tenant's most recent research runs, newest first."""

    runs = await run_store.list_recent(
        tenant_id=current_session.tenant_id,
        limit=limit,
    )

    return [_to_run_response(run) for run in runs]


@router.get(
    "/{research_run_id}",
    response_model=ResearchRunResponse,
)
async def get_research_run(
    research_run_id: UUID,
    current_session: Annotated[ResolvedSession, Depends(get_current_session)],
    run_store: Annotated[
        PostgresResearchRunStore,
        Depends(get_research_run_store),
    ],
) -> ResearchRunResponse:
    """Return one durable research run's current lifecycle state."""

    run = await run_store.get(
        tenant_id=current_session.tenant_id,
        research_run_id=research_run_id,
    )

    if run is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research run was not found.",
        )

    return _to_run_response(run)


async def _research_progress_events(
    *,
    tenant_id: UUID,
    research_run_id: UUID,
    progress_store: RedisResearchProgressStore,
    poll_interval_seconds: float = 0.25,
    heartbeat_interval_seconds: float = 8.0,
) -> AsyncIterator[str]:
    """Poll tenant-scoped progress and encode it as SSE frames.

    A single agent step can legitimately run for a minute or more (a local
    LLM call), during which nothing changes and this generator would
    otherwise write no bytes at all. Dev-server proxies and many
    intermediate proxies drop a streaming connection after some period of
    silence, which the client then reports as a disconnect even though the
    run is still healthy server-side. A periodic SSE comment line (ignored
    by clients, but still bytes on the wire) keeps the connection alive
    without changing the actual progress payload.
    """

    previous_payload: str | None = None
    last_sent_at = time.monotonic()

    while True:
        try:
            record = await progress_store.get(
                tenant_id=tenant_id,
                research_run_id=research_run_id,
            )
        except CacheUnavailableError:
            payload = json.dumps(
                {"detail": "Research progress is temporarily unavailable."},
                separators=(",", ":"),
            )
            yield f"event: error\ndata: {payload}\n\n"
            return

        if record is None:
            payload = json.dumps(
                {"detail": "Research progress was not found."},
                separators=(",", ":"),
            )
            yield f"event: not_found\ndata: {payload}\n\n"
            return

        payload = record.model_dump_json()
        now = time.monotonic()

        if payload != previous_payload:
            yield f"event: progress\ndata: {payload}\n\n"
            previous_payload = payload
            last_sent_at = now
        elif now - last_sent_at >= heartbeat_interval_seconds:
            yield ": keepalive\n\n"
            last_sent_at = now

        if record.status in {"completed", "failed", "cancelled"}:
            return

        await asyncio.sleep(poll_interval_seconds)


@router.get(
    "/{research_run_id}/progress",
    response_model=ResearchProgressRecord,
)
async def get_research_run_progress(
    research_run_id: UUID,
    current_session: Annotated[ResolvedSession, Depends(get_current_session)],
    progress_store: Annotated[
        RedisResearchProgressStore,
        Depends(get_research_progress_store),
    ],
) -> ResearchProgressRecord:
    """Return the latest tenant-scoped progress snapshot for one run."""

    try:
        record = await progress_store.get(
            tenant_id=current_session.tenant_id,
            research_run_id=research_run_id,
        )
    except CacheUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Research progress is temporarily unavailable.",
        ) from error

    if record is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research progress was not found.",
        )

    return record


@router.get(
    "/{research_run_id}/events",
    response_class=StreamingResponse,
)
async def stream_research_run_progress(
    research_run_id: UUID,
    current_session: Annotated[ResolvedSession, Depends(get_current_session)],
    progress_store: Annotated[
        RedisResearchProgressStore,
        Depends(get_research_progress_store),
    ],
) -> StreamingResponse:
    """Stream tenant-scoped progress snapshots until one terminal state."""

    return StreamingResponse(
        _research_progress_events(
            tenant_id=current_session.tenant_id,
            research_run_id=research_run_id,
            progress_store=progress_store,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get(
    "/{research_run_id}/report",
    response_model=ResearchReportResponse,
)
async def get_research_run_report(
    research_run_id: UUID,
    current_session: Annotated[ResolvedSession, Depends(get_current_session)],
    report_store: Annotated[
        PostgresResearchReportStore,
        Depends(get_research_report_store),
    ],
) -> ResearchReportResponse:
    """Return one durable report only within its tenant boundary."""

    report = await report_store.get(
        tenant_id=current_session.tenant_id,
        research_run_id=research_run_id,
    )

    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research report was not found.",
        )

    return report


@router.post(
    "/{research_run_id}/report/export",
    response_model=ResearchReportExportResponse,
    status_code=status.HTTP_201_CREATED,
)
async def export_research_run_report(
    research_run_id: UUID,
    current_session: Annotated[ResolvedSession, Depends(get_current_session)],
    report_store: Annotated[
        PostgresResearchReportStore,
        Depends(get_research_report_store),
    ],
    export_service: Annotated[
        ResearchReportExportService,
        Depends(get_research_report_export_service),
    ],
) -> ResearchReportExportResponse:
    """Store an immutable object-storage snapshot of one durable report."""

    report = await report_store.get(
        tenant_id=current_session.tenant_id,
        research_run_id=research_run_id,
    )

    if report is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research report was not found.",
        )

    try:
        storage_key = await export_service.export(
            tenant_id=current_session.tenant_id,
            research_run_id=research_run_id,
            content=report.content,
        )
    except DocumentStorageError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Report export storage is temporarily unavailable.",
        ) from error

    return ResearchReportExportResponse(storage_key=storage_key)


@router.get("/{research_run_id}/report/export")
async def download_research_run_report_export(
    research_run_id: UUID,
    current_session: Annotated[ResolvedSession, Depends(get_current_session)],
    export_service: Annotated[
        ResearchReportExportService,
        Depends(get_research_report_export_service),
    ],
) -> Response:
    """Download one previously exported report snapshot as Markdown."""

    try:
        content = await export_service.retrieve(
            tenant_id=current_session.tenant_id,
            research_run_id=research_run_id,
        )
    except DocumentNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report export was not found.",
        ) from error
    except DocumentStorageError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Report export storage is temporarily unavailable.",
        ) from error

    return Response(
        content=content,
        media_type="text/markdown; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="report-{research_run_id}.md"',
        },
    )


@router.get(
    "/{research_run_id}/sources",
    response_model=list[ResearchReportSourceResponse],
)
async def list_research_run_sources(
    research_run_id: UUID,
    current_session: Annotated[ResolvedSession, Depends(get_current_session)],
    report_store: Annotated[
        PostgresResearchReportStore,
        Depends(get_research_report_store),
    ],
) -> list[ResearchReportSourceResponse]:
    """Return scored evidence only within the report's tenant boundary."""

    sources = await report_store.list_sources(
        tenant_id=current_session.tenant_id,
        research_run_id=research_run_id,
    )
    if sources is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Research sources were not found.",
        )
    return sources


@router.post(
    "/{research_run_id}/cancel",
    response_model=CancelResearchRunResponse,
)
async def cancel_research_run(
    research_run_id: UUID,
    current_session: Annotated[ResolvedSession, Depends(get_current_session)],
    job_manager: Annotated[
        ResearchJobManager,
        Depends(get_research_job_manager),
    ],
) -> CancelResearchRunResponse:
    """Cancel one queued or running research job within its tenant boundary."""

    cancelled = await job_manager.cancel(
        tenant_id=current_session.tenant_id,
        research_run_id=research_run_id,
    )
    if not cancelled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Research run is not active or was not found.",
        )
    return CancelResearchRunResponse(
        research_run_id=research_run_id,
        status="cancelled",
    )


async def _resolve_document_ids(
    *,
    tenant_id: UUID,
    document_ids: list[UUID] | None,
    knowledge_service: KnowledgeDocumentService,
) -> list[str] | None:
    """Translate durable document IDs into vector-store document IDs."""

    if document_ids is None:
        return None

    try:
        return await knowledge_service.resolve_vector_document_ids(
            tenant_id=tenant_id,
            document_ids=document_ids,
        )
    except KnowledgeDocumentNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(error),
        ) from error
    except KnowledgeDocumentNotReadyError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error


def _rate_limit_headers(
    decision: ResearchRateLimitDecision,
) -> dict[str, str]:
    """Build response headers for one rate-limit decision."""

    return {
        "X-RateLimit-Limit": str(decision.limit),
        "X-RateLimit-Remaining": str(decision.remaining),
        "X-RateLimit-Reset": str(decision.reset_after_seconds),
    }


async def _enforce_rate_limit(
    *,
    tenant_id: UUID,
    rate_limiter: RedisResearchRateLimiter,
    response: Response,
) -> None:
    """Apply the same tenant limit to synchronous and asynchronous requests."""

    try:
        decision = await rate_limiter.check(
            tenant_id=tenant_id,
        )
    except ResearchRateLimitUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error

    headers = _rate_limit_headers(decision)

    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Research request rate limit exceeded.",
            headers={
                **headers,
                "Retry-After": str(decision.reset_after_seconds),
            },
        )

    response.headers.update(headers)


@router.post(
    "/jobs",
    response_model=CreateResearchJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_research_job(
    payload: CreateResearchRunRequest,
    current_session: Annotated[ResolvedSession, Depends(get_current_session)],
    job_manager: Annotated[
        ResearchJobManager,
        Depends(get_research_job_manager),
    ],
    knowledge_service: Annotated[
        KnowledgeDocumentService,
        Depends(get_knowledge_document_service),
    ],
    rate_limiter: Annotated[
        RedisResearchRateLimiter,
        Depends(get_research_rate_limiter),
    ],
    response: Response,
) -> CreateResearchJobResponse:
    """Persist and accept one research run for background execution."""

    await _enforce_rate_limit(
        tenant_id=current_session.tenant_id,
        rate_limiter=rate_limiter,
        response=response,
    )
    document_ids = await _resolve_document_ids(
        tenant_id=current_session.tenant_id,
        document_ids=payload.document_ids,
        knowledge_service=knowledge_service,
    )
    research_run_id = await job_manager.submit(
        tenant_id=current_session.tenant_id,
        requested_by_user_id=current_session.user_id,
        query=payload.query,
        llm_provider=payload.llm_provider,
        document_ids=document_ids,
    )
    base_url = f"/research-runs/{research_run_id}"

    return CreateResearchJobResponse(
        research_run_id=research_run_id,
        status="queued",
        progress_url=f"{base_url}/progress",
        events_url=f"{base_url}/events",
        report_url=f"{base_url}/report",
    )


@router.post(
    "",
    response_model=CreateResearchRunResponse,
)
async def create_research_run(
    payload: CreateResearchRunRequest,
    current_session: Annotated[ResolvedSession, Depends(get_current_session)],
    service: Annotated[
        IdempotentResearchExecutionService,
        Depends(get_research_execution_service),
    ],
    knowledge_service: Annotated[
        KnowledgeDocumentService,
        Depends(get_knowledge_document_service),
    ],
    rate_limiter: Annotated[
        RedisResearchRateLimiter,
        Depends(get_research_rate_limiter),
    ],
    response: Response,
    idempotency_key: Annotated[
        str | None,
        Header(
            alias="Idempotency-Key",
            min_length=1,
            max_length=MAX_RESEARCH_IDEMPOTENCY_KEY_LENGTH,
            pattern=r".*\S.*",
        ),
    ] = None,
) -> CreateResearchRunResponse:
    """Execute one tenant-scoped research request."""

    await _enforce_rate_limit(
        tenant_id=current_session.tenant_id,
        rate_limiter=rate_limiter,
        response=response,
    )
    document_ids = await _resolve_document_ids(
        tenant_id=current_session.tenant_id,
        document_ids=payload.document_ids,
        knowledge_service=knowledge_service,
    )

    try:
        result = await service.execute(
            tenant_id=current_session.tenant_id,
            requested_by_user_id=current_session.user_id,
            query=payload.query,
            llm_provider=payload.llm_provider,
            idempotency_key=idempotency_key,
            document_ids=document_ids,
        )
    except (
        ResearchIdempotencyConflictError,
        ResearchIdempotencyInProgressError,
    ) as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except ResearchIdempotencyUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error

    return CreateResearchRunResponse(
        research_run_id=result.research_run_id,
        llm_provider=result.llm_provider,
        status="completed",
        cache_hit=result.cache_hit,
        idempotency_replayed=result.idempotency_replayed,
        workflow_status=result.state.get(
            "status",
            "completed",
        ),
        route=result.state.get(
            "route",
        ),
        route_reason=result.state.get(
            "route_reason",
        ),
        answer=result.state.get(
            "answer",
        ),
        citation_valid=(
            result.state["citation_audit"].valid if "citation_audit" in result.state else None
        ),
        citation_coverage=(
            result.state["citation_audit"].coverage_ratio
            if "citation_audit" in result.state
            else None
        ),
        reflection_status=(
            result.state["reflection"].status if "reflection" in result.state else None
        ),
        reflection_reasons=(
            result.state["reflection"].reasons if "reflection" in result.state else []
        ),
        human_review_required=(
            result.state["reflection"].human_review_required
            if "reflection" in result.state
            else False
        ),
        human_review_reason=(
            result.state["reflection"].human_review_reason
            if "reflection" in result.state
            else None
        ),
    )
