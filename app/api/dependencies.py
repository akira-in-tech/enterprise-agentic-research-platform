from typing import cast

from fastapi import Request

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
