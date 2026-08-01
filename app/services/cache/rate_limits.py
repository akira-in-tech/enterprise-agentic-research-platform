from dataclasses import dataclass
from uuid import UUID

from app.core.config import settings
from app.services.cache.base import (
    CacheUnavailableError,
    RateLimitCounterClient,
)
from app.services.cache.keys import (
    create_research_rate_limit_redis_key,
)


@dataclass(frozen=True)
class ResearchRateLimitDecision:
    """Describe whether one tenant request may proceed."""

    allowed: bool
    limit: int
    remaining: int
    reset_after_seconds: int


class ResearchRateLimitUnavailableError(RuntimeError):
    """Signal that request-rate enforcement cannot be guaranteed."""


class RedisResearchRateLimiter:
    """Enforce a tenant-scoped fixed-window research request limit."""

    def __init__(
        self,
        client: RateLimitCounterClient,
        *,
        request_limit: int | None = None,
        window_seconds: int | None = None,
    ) -> None:
        selected_limit = (
            request_limit
            if request_limit is not None
            else settings.redis_research_rate_limit_requests
        )
        selected_window = (
            window_seconds
            if window_seconds is not None
            else settings.redis_research_rate_limit_window_seconds
        )

        if selected_limit < 1:
            raise ValueError("Research rate-limit request_limit must be at least 1.")

        if selected_window < 1:
            raise ValueError("Research rate-limit window_seconds must be at least 1.")

        self._client = client
        self._request_limit = selected_limit
        self._window_seconds = selected_window

    async def check(
        self,
        *,
        tenant_id: UUID,
    ) -> ResearchRateLimitDecision:
        """Consume one request allowance and return the current decision."""

        redis_key = create_research_rate_limit_redis_key(
            tenant_id=tenant_id,
        )

        try:
            request_count, remaining_ttl = await self._client.increment_with_ttl(
                key=redis_key,
                ttl_seconds=self._window_seconds,
            )
        except CacheUnavailableError as error:
            raise ResearchRateLimitUnavailableError(
                "Research rate limiting is unavailable."
            ) from error

        allowed = request_count <= self._request_limit

        return ResearchRateLimitDecision(
            allowed=allowed,
            limit=self._request_limit,
            remaining=max(
                self._request_limit - request_count,
                0,
            ),
            reset_after_seconds=max(
                remaining_ttl,
                1,
            ),
        )
