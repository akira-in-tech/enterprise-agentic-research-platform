from uuid import uuid4

import pytest

from app.services.cache import (
    RESEARCH_RATE_LIMIT_VERSION,
    CacheUnavailableError,
    RedisResearchRateLimiter,
    ResearchRateLimitUnavailableError,
    create_research_rate_limit_redis_key,
)


class RecordingRateLimitCounterClient:
    def __init__(
        self,
        *,
        result: tuple[int, int] = (
            1,
            60,
        ),
        error: CacheUnavailableError | None = None,
    ) -> None:
        self.result = result
        self.error = error
        self.calls: list[tuple[str, int]] = []

    async def increment_with_ttl(
        self,
        *,
        key: str,
        ttl_seconds: int,
    ) -> tuple[int, int]:
        self.calls.append(
            (
                key,
                ttl_seconds,
            )
        )

        if self.error is not None:
            raise self.error

        return self.result


def test_rate_limit_key_is_tenant_scoped_and_versioned() -> None:
    tenant_id = uuid4()

    key = create_research_rate_limit_redis_key(
        tenant_id=tenant_id,
    )

    assert key == (
        f"enterprise-research:{RESEARCH_RATE_LIMIT_VERSION}:tenant:{tenant_id}:research-rate-limit"
    )


def test_rate_limit_key_isolates_tenants() -> None:
    assert create_research_rate_limit_redis_key(
        tenant_id=uuid4(),
    ) != create_research_rate_limit_redis_key(
        tenant_id=uuid4(),
    )


@pytest.mark.anyio
async def test_rate_limiter_allows_request_with_remaining_capacity() -> None:
    client = RecordingRateLimitCounterClient(
        result=(
            3,
            42,
        ),
    )
    limiter = RedisResearchRateLimiter(
        client,
        request_limit=5,
        window_seconds=60,
    )
    tenant_id = uuid4()

    decision = await limiter.check(
        tenant_id=tenant_id,
    )

    assert decision.allowed is True
    assert decision.limit == 5
    assert decision.remaining == 2
    assert decision.reset_after_seconds == 42
    assert client.calls == [
        (
            create_research_rate_limit_redis_key(
                tenant_id=tenant_id,
            ),
            60,
        )
    ]


@pytest.mark.anyio
async def test_rate_limiter_rejects_request_above_limit() -> None:
    limiter = RedisResearchRateLimiter(
        RecordingRateLimitCounterClient(
            result=(
                6,
                37,
            ),
        ),
        request_limit=5,
        window_seconds=60,
    )

    decision = await limiter.check(
        tenant_id=uuid4(),
    )

    assert decision.allowed is False
    assert decision.remaining == 0
    assert decision.reset_after_seconds == 37


@pytest.mark.anyio
async def test_rate_limiter_fails_closed_when_redis_is_unavailable() -> None:
    limiter = RedisResearchRateLimiter(
        RecordingRateLimitCounterClient(
            error=CacheUnavailableError("Redis is unavailable."),
        ),
        request_limit=5,
        window_seconds=60,
    )

    with pytest.raises(
        ResearchRateLimitUnavailableError,
        match="rate limiting is unavailable",
    ):
        await limiter.check(
            tenant_id=uuid4(),
        )


@pytest.mark.parametrize(
    (
        "request_limit",
        "window_seconds",
        "message",
    ),
    [
        (
            0,
            60,
            "request_limit must be at least 1",
        ),
        (
            5,
            0,
            "window_seconds must be at least 1",
        ),
    ],
)
def test_rate_limiter_rejects_invalid_configuration(
    request_limit: int,
    window_seconds: int,
    message: str,
) -> None:
    with pytest.raises(
        ValueError,
        match=message,
    ):
        RedisResearchRateLimiter(
            RecordingRateLimitCounterClient(),
            request_limit=request_limit,
            window_seconds=window_seconds,
        )
