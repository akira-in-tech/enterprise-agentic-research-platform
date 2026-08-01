from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Response,
    status,
)

from app.api.dependencies import (
    get_research_execution_service,
    get_research_progress_store,
    get_research_rate_limiter,
)
from app.schemas.progress import ResearchProgressRecord
from app.schemas.research import (
    CreateResearchRunRequest,
    CreateResearchRunResponse,
)
from app.services.cache import (
    MAX_RESEARCH_IDEMPOTENCY_KEY_LENGTH,
    CacheUnavailableError,
    RedisResearchProgressStore,
    RedisResearchRateLimiter,
    ResearchRateLimitDecision,
    ResearchRateLimitUnavailableError,
)
from app.services.research.idempotency import (
    IdempotentResearchExecutionService,
    ResearchIdempotencyConflictError,
    ResearchIdempotencyInProgressError,
    ResearchIdempotencyUnavailableError,
)

router = APIRouter(
    prefix="/research-runs",
    tags=[
        "research",
    ],
)


@router.get(
    "/{research_run_id}/progress",
    response_model=ResearchProgressRecord,
)
async def get_research_run_progress(
    research_run_id: UUID,
    tenant_id: Annotated[
        UUID,
        Header(alias="X-Tenant-ID"),
    ],
    progress_store: Annotated[
        RedisResearchProgressStore,
        Depends(get_research_progress_store),
    ],
) -> ResearchProgressRecord:
    """Return the latest tenant-scoped progress snapshot for one run."""

    try:
        record = await progress_store.get(
            tenant_id=tenant_id,
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


def _rate_limit_headers(
    decision: ResearchRateLimitDecision,
) -> dict[str, str]:
    """Build response headers for one rate-limit decision."""

    return {
        "X-RateLimit-Limit": str(decision.limit),
        "X-RateLimit-Remaining": str(decision.remaining),
        "X-RateLimit-Reset": str(decision.reset_after_seconds),
    }


@router.post(
    "",
    response_model=CreateResearchRunResponse,
)
async def create_research_run(
    payload: CreateResearchRunRequest,
    tenant_id: Annotated[
        UUID,
        Header(alias="X-Tenant-ID"),
    ],
    service: Annotated[
        IdempotentResearchExecutionService,
        Depends(get_research_execution_service),
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
    requested_by_user_id: Annotated[
        UUID | None,
        Header(alias="X-User-ID"),
    ] = None,
) -> CreateResearchRunResponse:
    """Execute one tenant-scoped research request."""

    try:
        rate_limit_decision = await rate_limiter.check(
            tenant_id=tenant_id,
        )
    except ResearchRateLimitUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error

    rate_limit_headers = _rate_limit_headers(
        rate_limit_decision,
    )

    if not rate_limit_decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Research request rate limit exceeded.",
            headers={
                **rate_limit_headers,
                "Retry-After": str(rate_limit_decision.reset_after_seconds),
            },
        )

    response.headers.update(
        rate_limit_headers,
    )

    try:
        result = await service.execute(
            tenant_id=tenant_id,
            requested_by_user_id=requested_by_user_id,
            query=payload.query,
            llm_provider=payload.llm_provider,
            idempotency_key=idempotency_key,
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
    )
