from anthropic import AsyncAnthropic

from app.core.config import settings


class ClaudeClient:
    """Create and manage the asynchronous Anthropic API client."""

    def __init__(self) -> None:
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is not configured.")

        self._client = AsyncAnthropic(
            api_key=settings.anthropic_api_key,
            timeout=30.0,
            max_retries=2,
        )

    @property
    def client(self) -> AsyncAnthropic:
        """Return the underlying Anthropic SDK client."""
        return self._client