from typing import Protocol, TypeVar

from pydantic import BaseModel

StructuredModel = TypeVar(
    "StructuredModel",
    bound=BaseModel,
)


class LLMClient(Protocol):
    """Define the behavior required from an LLM provider."""

    async def generate_text(
        self,
        prompt: str,
        *,
        max_tokens: int = 64,
    ) -> str:
        """Generate an unstructured text response."""
        ...

    async def generate_structured(
        self,
        prompt: str,
        output_model: type[StructuredModel],
        *,
        max_tokens: int = 256,
    ) -> StructuredModel:
        """Generate a response validated against a Pydantic model."""
        ...


class ClosableLLMClient(
    LLMClient,
    Protocol,
):
    """Define an LLM client that owns asynchronous resources."""

    async def close(self) -> None:
        """Release provider-owned network resources."""
        ...
