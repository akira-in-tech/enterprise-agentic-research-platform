import pytest
from pydantic import BaseModel, Field

from app.core.config import settings
from app.services.llm.ollama import OllamaClient


class EngineeringDefinition(BaseModel):
    term: str = Field(
        min_length=1,
    )
    explanation: str = Field(
        min_length=1,
    )


@pytest.mark.integration
@pytest.mark.anyio
async def test_ollama_llm_live_text_and_structured_output() -> None:
    """Verify real Qwen text and structured generation."""

    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    client = OllamaClient()

    try:
        text_response = await client.generate_text(
            ("In one concise sentence, explain what a mutex does in concurrent software."),
            max_tokens=96,
        )

        structured_response = await client.generate_structured(
            ("Define the software engineering term mutex. Set the term field exactly to mutex."),
            EngineeringDefinition,
            max_tokens=128,
        )

        assert text_response
        assert structured_response.term.lower() == "mutex"
        assert structured_response.explanation
    finally:
        await client.close()
