from typing import cast

from fastapi import Request

from app.services.cache import RedisResearchRateLimiter
from app.services.research.idempotency import (
    IdempotentResearchExecutionService,
)


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
