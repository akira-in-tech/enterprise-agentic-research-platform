from typing import Literal

from app.core.circuit_breaker import CircuitBreaker
from app.core.config import settings
from app.services.llm.anthropic import AnthropicClient
from app.services.llm.base import ClosableLLMClient
from app.services.llm.ollama import OllamaClient

CanonicalLLMProvider = Literal[
    "anthropic",
    "ollama",
]

PROVIDER_ALIASES: dict[
    str,
    CanonicalLLMProvider,
] = {
    "anthropic": "anthropic",
    "claude": "anthropic",
    "ollama": "ollama",
    "qwen": "ollama",
}


def normalize_llm_provider(
    provider: str | None = None,
) -> CanonicalLLMProvider:
    """Normalize user-facing and internal provider names."""

    selected_value = settings.llm_provider if provider is None else provider
    selected_provider = selected_value.strip().lower()
    canonical_provider = PROVIDER_ALIASES.get(selected_provider)

    if canonical_provider is None:
        raise ValueError(
            "Unsupported LLM provider: "
            f"{selected_provider}. "
            "Expected one of: anthropic, claude, "
            "ollama, qwen."
        )

    return canonical_provider


def create_llm_client(
    provider: str | None = None,
) -> ClosableLLMClient:
    """Create the selected LLM provider client."""

    selected_provider = normalize_llm_provider(provider)

    if selected_provider == "anthropic":
        return AnthropicClient(circuit_breaker=CircuitBreaker())

    return OllamaClient()
