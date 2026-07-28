import pytest

from app.core.config import settings
from app.services.cache import RedisConnection


@pytest.mark.integration
@pytest.mark.anyio
async def test_redis_live_connection_round_trip() -> None:
    """Verify the real Redis connection pool and health check."""

    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    connection = RedisConnection.from_url()

    try:
        assert await connection.ping() is True
        assert await connection.ping() is True
    finally:
        await connection.close()
