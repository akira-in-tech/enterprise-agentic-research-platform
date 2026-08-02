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


class RecordingJobManager:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class RecordingEmbeddingClient:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


class RecordingVectorStore:
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
    idempotency_store = object()
    execution_service = object()
    idempotent_execution_service = object()
    idempotency_lock_manager = object()
    rate_limiter = object()
    progress_store = object()
    report_store = object()
    job_manager = RecordingJobManager()
    embedding_client = RecordingEmbeddingClient()
    vector_store = RecordingVectorStore()
    private_retriever = object()
    local_scout = object()
    expected_workflow = object()

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
    create_idempotency_store = Mock(
        return_value=idempotency_store,
    )
    create_execution_service = Mock(
        return_value=execution_service,
    )
    create_idempotent_execution_service = Mock(
        return_value=idempotent_execution_service,
    )
    create_idempotency_lock_manager = Mock(
        return_value=idempotency_lock_manager,
    )
    create_rate_limiter = Mock(
        return_value=rate_limiter,
    )
    create_progress_store = Mock(
        return_value=progress_store,
    )
    create_report_store = Mock(
        return_value=report_store,
    )
    create_job_manager = Mock(
        return_value=job_manager,
    )
    create_embedding_client = Mock(
        return_value=embedding_client,
    )
    create_vector_store = Mock(
        return_value=vector_store,
    )
    create_private_retriever = Mock(
        return_value=private_retriever,
    )
    create_local_scout = Mock(
        return_value=local_scout,
    )
    create_workflow = Mock(
        return_value=expected_workflow,
    )
    monkeypatch.setattr(
        main_module,
        "RedisResearchIdempotencyStore",
        create_idempotency_store,
    )
    monkeypatch.setattr(
        main_module,
        "IdempotentResearchExecutionService",
        create_idempotent_execution_service,
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
    monkeypatch.setattr(
        main_module,
        "RedisResearchIdempotencyLockManager",
        create_idempotency_lock_manager,
    )
    monkeypatch.setattr(
        main_module,
        "RedisResearchRateLimiter",
        create_rate_limiter,
    )
    monkeypatch.setattr(
        main_module,
        "RedisResearchProgressStore",
        create_progress_store,
    )
    monkeypatch.setattr(
        main_module,
        "PostgresResearchReportStore",
        create_report_store,
    )
    monkeypatch.setattr(
        main_module,
        "ResearchJobManager",
        create_job_manager,
    )
    monkeypatch.setattr(
        main_module,
        "OllamaEmbeddingClient",
        create_embedding_client,
    )
    monkeypatch.setattr(
        main_module,
        "create_vector_store",
        create_vector_store,
    )
    monkeypatch.setattr(
        main_module,
        "PrivateKnowledgeRetriever",
        create_private_retriever,
    )
    monkeypatch.setattr(
        main_module,
        "LocalScoutAgent",
        create_local_scout,
    )
    monkeypatch.setattr(
        main_module,
        "create_default_workflow",
        create_workflow,
    )

    application = FastAPI()

    async with main_module.lifespan(
        application,
    ):
        assert application.state.research_execution_service is idempotent_execution_service
        assert application.state.research_rate_limiter is rate_limiter
        assert application.state.research_progress_store is progress_store
        assert application.state.research_report_store is report_store
        assert application.state.research_job_manager is job_manager
        assert engine.disposed is False
        assert redis_connection.closed is False
        assert job_manager.closed is False
        assert embedding_client.closed is False
        assert vector_store.closed is False

    assert redis_connection.closed is True
    assert engine.disposed is True
    assert job_manager.closed is True
    assert embedding_client.closed is True
    assert vector_store.closed is True

    create_idempotency_store.assert_called_once_with(
        redis_connection,
    )
    create_idempotent_execution_service.assert_called_once_with(
        execution_service,
        idempotency_store,
        idempotency_lock_manager,
    )
    create_idempotency_lock_manager.assert_called_once_with(
        redis_connection,
    )
    create_rate_limiter.assert_called_once_with(
        redis_connection,
    )
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
    create_progress_store.assert_called_once_with(
        redis_connection,
    )
    create_report_store.assert_called_once_with(
        database_session_factory,
    )
    create_job_manager.assert_called_once_with(
        execution_service,
    )
    create_embedding_client.assert_called_once_with()
    create_vector_store.assert_called_once_with()
    create_private_retriever.assert_called_once_with(
        embedding_client,
        vector_store,
    )
    create_local_scout.assert_called_once_with(
        private_retriever,
    )
    execution_call = create_execution_service.call_args
    assert execution_call.args[0] is research_store
    workflow_factory = execution_call.args[1]
    assert workflow_factory("ollama") is expected_workflow
    create_workflow.assert_called_once_with(
        "ollama",
        local_scout=local_scout,
    )
    assert execution_call.kwargs == {
        "result_cache": result_cache,
        "progress_store": progress_store,
    }
