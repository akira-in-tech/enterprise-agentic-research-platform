from typing import TypeVar

import pytest
from pydantic import BaseModel

from app.agents.direct_answer import DirectAnswerAgent

StructuredModel = TypeVar(
    "StructuredModel",
    bound=BaseModel,
)


class FakeLLMClient:
    """Provide deterministic LLM responses without external API calls."""

    def __init__(self, text_response: str) -> None:
        self.text_response = text_response
        self.requests: list[tuple[str, int]] = []

    async def generate_text(
        self,
        prompt: str,
        *,
        max_tokens: int = 64,
    ) -> str:
        self.requests.append((prompt, max_tokens))
        return self.text_response

    async def generate_structured(
        self,
        prompt: str,
        output_model: type[StructuredModel],
        *,
        max_tokens: int = 256,
    ) -> StructuredModel:
        raise AssertionError("DirectAnswerAgent must not request structured output.")


@pytest.mark.anyio
async def test_direct_answer_returns_llm_response() -> None:
    llm_client = FakeLLMClient("A mutex protects shared state from concurrent access.")
    agent = DirectAnswerAgent(llm_client)

    answer = await agent.answer("What is a mutex?")

    assert answer == ("A mutex protects shared state from concurrent access.")
    assert len(llm_client.requests) == 1

    prompt, max_tokens = llm_client.requests[0]

    assert "User question: What is a mutex?" in prompt
    assert "Do not invent citations" in prompt
    assert max_tokens == 1_200


@pytest.mark.anyio
async def test_direct_answer_rejects_empty_query() -> None:
    llm_client = FakeLLMClient("Unused response.")
    agent = DirectAnswerAgent(llm_client)

    with pytest.raises(
        ValueError,
        match="Query must not be empty",
    ):
        await agent.answer("   ")

    assert llm_client.requests == []


@pytest.mark.anyio
async def test_direct_answer_rejects_empty_llm_response() -> None:
    llm_client = FakeLLMClient("   ")
    agent = DirectAnswerAgent(llm_client)

    with pytest.raises(
        RuntimeError,
        match="LLM provider returned an empty direct answer",
    ):
        await agent.answer("Explain idempotency in REST APIs.")
