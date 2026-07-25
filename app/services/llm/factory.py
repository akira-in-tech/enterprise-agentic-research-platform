from app.core.config import settings
from app.services.llm.anthropic import AnthropicClient
from app.services.llm.base import LLMClient
from app.services.llm.ollama import OllamaClient


def create_llm_client(
    provider: str | None = None,
) -> LLMClient:
    """Create the configured LLM provider client."""

    selected_provider = (
        provider or settings.llm_provider
    ).strip().lower()

    if selected_provider == "anthropic":
        return AnthropicClient()

    if selected_provider == "ollama":
        return OllamaClient()

    raise ValueError(
        "Unsupported LLM provider: "
        f"{selected_provider}. "
        "Expected 'anthropic' or 'ollama'."
    )