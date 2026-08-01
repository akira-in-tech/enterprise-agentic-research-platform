from unittest.mock import Mock

import pytest
from fastapi import FastAPI

from app import main as main_module


class RecordingEngine:
    def __init__(self) -> None:
        self.disposed = False

    async def dispose(self) -> None:
        self.disposed = True


class RecordingRedisConnection:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


@pytest.mark.anyio
async def test_lifespan_wires_and_closes_application_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = RecordingEngine()
    redis_connection = RecordingRedisConnection()
    database_session_factory = object()
    research_store = object()
    result_cache = object()
    execution_service = object()

    create_engine = Mock(
        return_value=engine,
    )
    create_sessions = Mock(
        return_value=database_session_factory,
    )
    create_store = Mock(
        return_value=research_store,
    )
    redis_connection_type = Mock()
    redis_connection_type.from_url.return_value = redis_connection
    create_cache = Mock(
        return_value=result_cache,
    )
    create_execution_service = Mock(
        return_value=execution_service,
    )

    monkeypatch.setattr(
        main_module,
        "create_database_engine",
        create_engine,
    )
    monkeypatch.setattr(
        main_module,
        "create_session_factory",
        create_sessions,
    )
    monkeypatch.setattr(
        main_module,
        "PostgresResearchRunStore",
        create_store,
    )
    monkeypatch.setattr(
        main_module,
        "RedisConnection",
        redis_connection_type,
    )
    monkeypatch.setattr(
        main_module,
        "RedisResearchResultCache",
        create_cache,
    )
    monkeypatch.setattr(
        main_module,
        "ResearchExecutionService",
        create_execution_service,
    )

    application = FastAPI()

    async with main_module.lifespan(
        application,
    ):
        assert application.state.research_execution_service is execution_service
        assert engine.disposed is False
        assert redis_connection.closed is False

    assert redis_connection.closed is True
    assert engine.disposed is True

    create_engine.assert_called_once_with()
    create_sessions.assert_called_once_with(
        engine,
    )
    create_store.assert_called_once_with(
        database_session_factory,
    )
    redis_connection_type.from_url.assert_called_once_with()
    create_cache.assert_called_once_with(
        redis_connection,
    )
    create_execution_service.assert_called_once_with(
        research_store,
        result_cache=result_cache,
    )
