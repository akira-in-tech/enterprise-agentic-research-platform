import pytest

from app.core.config import settings
from app.db.session import create_database_engine
from app.services.cache import RedisConnection
from app.services.readiness import ApplicationReadinessService

pytestmark = pytest.mark.integration


@pytest.mark.anyio
async def test_required_dependencies_are_live_and_ready() -> None:
    if not settings.run_live_tests:
        pytest.skip("Set RUN_LIVE_TESTS=true to run external integration tests.")

    engine = create_database_engine(echo=False)
    redis = RedisConnection.from_url()
    try:
        result = await ApplicationReadinessService(engine, redis).check()
        assert result.status == "ready"
        assert result.postgresql == "ready"
        assert result.redis == "ready"
    finally:
        await redis.close()
        await engine.dispose()
