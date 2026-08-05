from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.schemas.operations import ReadinessResponse
from app.services.cache import RedisConnection


class ApplicationReadinessService:
    """Verify required application dependencies with bounded client timeouts."""

    def __init__(self, engine: AsyncEngine, redis: RedisConnection) -> None:
        self._engine = engine
        self._redis = redis

    async def check(self) -> ReadinessResponse:
        """Fail when PostgreSQL or Redis cannot serve required operations."""

        async with self._engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        if not await self._redis.ping():
            raise RuntimeError("Redis readiness check returned false.")
        return ReadinessResponse(
            status="ready",
            postgresql="ready",
            redis="ready",
        )
