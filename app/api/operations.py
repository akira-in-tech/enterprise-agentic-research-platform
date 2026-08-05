from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_readiness_service
from app.core.config import settings
from app.schemas.operations import ProviderCapabilityResponse, ReadinessResponse
from app.services.readiness import ApplicationReadinessService

router = APIRouter(tags=["operations"])


@router.get("/providers", response_model=list[ProviderCapabilityResponse])
async def list_research_providers() -> list[ProviderCapabilityResponse]:
    """Return stable user-facing providers without exposing credentials."""

    return [
        ProviderCapabilityResponse(
            id="claude",
            canonical_provider="anthropic",
            label="Claude Cloud",
            execution="cloud",
            configured=bool(settings.anthropic_api_key.get_secret_value().strip()),
        ),
        ProviderCapabilityResponse(
            id="qwen",
            canonical_provider="ollama",
            label="Qwen Local",
            execution="local",
            configured=bool(settings.ollama_model.strip()),
        ),
    ]


@router.get("/ready", response_model=ReadinessResponse)
async def readiness_check(
    service: Annotated[
        ApplicationReadinessService,
        Depends(get_readiness_service),
    ],
) -> ReadinessResponse:
    """Return ready only when required durable dependencies respond."""

    try:
        return await service.check()
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Required application dependencies are unavailable.",
        ) from error
