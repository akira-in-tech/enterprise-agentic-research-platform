from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Header,
)

from app.api.dependencies import (
    get_research_execution_service,
)
from app.schemas.research import (
    CreateResearchRunRequest,
    CreateResearchRunResponse,
)
from app.services.research.execution import (
    ResearchExecutionService,
)

router = APIRouter(
    prefix="/research-runs",
    tags=[
        "research",
    ],
)


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
        ResearchExecutionService,
        Depends(get_research_execution_service),
    ],
    requested_by_user_id: Annotated[
        UUID | None,
        Header(alias="X-User-ID"),
    ] = None,
) -> CreateResearchRunResponse:
    """Execute one tenant-scoped research request."""

    result = await service.execute(
        tenant_id=tenant_id,
        requested_by_user_id=requested_by_user_id,
        query=payload.query,
        llm_provider=payload.llm_provider,
    )

    return CreateResearchRunResponse(
        research_run_id=result.research_run_id,
        llm_provider=result.llm_provider,
        status="completed",
        cache_hit=result.cache_hit,
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
