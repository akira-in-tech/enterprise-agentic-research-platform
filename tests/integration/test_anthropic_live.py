from typing import Literal

import pytest
from pydantic import BaseModel

from app.core.config import settings
from app.services.llm.anthropic import AnthropicClient


class AnthropicHealthResponse(BaseModel):
    status: Literal["ready"]


@pytest.mark.integration
@pytest.mark.anyio
async def test_anthropic_live_structured_output() -> None:
    """Verify the configured Claude model and structured-output path."""

    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    api_key = settings.anthropic_api_key.get_secret_value().strip()

    if not api_key:
        pytest.fail("ANTHROPIC_API_KEY is required for the live Anthropic test.")

    client = AnthropicClient()

    try:
        response = await client.generate_structured(
            "Confirm service readiness by setting status to ready.",
            AnthropicHealthResponse,
            max_tokens=64,
        )

        assert response.status == "ready"
    finally:
        await client.close()
