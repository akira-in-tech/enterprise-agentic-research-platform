import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.services.research.durability import (
    ResearchCheckpointRecord,
    ResearchWorkerLeaseRecord,
)
from app.services.research.execution import (
    QueuedResearchExecution,
    ResearchExecutionResult,
)
from app.services.research.jobs import ResearchJobManager


class RecordingBackgroundExecutor:
    def __init__(self, *, block: bool = False) -> None:
        self.block = block
        self.queue_calls: list[dict[str, object]] = []
        self.execute_calls: list[QueuedResearchExecution] = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def queue(
        self,
        *,
        tenant_id: UUID,
        query: str,
        llm_provider: str,
        requested_by_user_id: UUID | None = None,
        research_run_id: UUID | None = None,
    ) -> QueuedResearchExecution:
        queued = QueuedResearchExecution(
            research_run_id=research_run_id or uuid4(),
            tenant_id=tenant_id,
            requested_by_user_id=requested_by_user_id,
            query=query.strip(),
            llm_provider="ollama",
        )
        self.queue_calls.append(
            {
                "tenant_id": tenant_id,
                "query": query,
                "llm_provider": llm_provider,
                "requested_by_user_id": requested_by_user_id,
            }
        )
        return queued

    async def execute_queued(
        self,
        queued: QueuedResearchExecution,
    ) -> ResearchExecutionResult:
        self.execute_calls.append(queued)
        self.started.set()

        if self.block:
            await self.release.wait()

        return ResearchExecutionResult(
            research_run_id=queued.research_run_id,
            llm_provider=queued.llm_provider,
            state={
                "query": queued.query,
                "status": "direct_answer_completed",
                "answer": "Completed in the background.",
            },
        )


class RecordingDurabilityStore:
    def __init__(self, *, claim: bool = True) -> None:
        self.claim = claim
        self.lease_token = uuid4()
        self.claim_calls: list[dict[str, object]] = []
        self.renew_calls = 0
        self.release_calls: list[dict[str, object]] = []
        self.released = asyncio.Event()
        self.checkpoints: list[tuple[int, str, Mapping[str, object]]] = []
        self.audit_events: list[str] = []

    def _lease(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        worker_id: str,
    ) -> ResearchWorkerLeaseRecord:
        now = datetime.now(UTC)
        return ResearchWorkerLeaseRecord(
            tenant_id=tenant_id,
            research_run_id=research_run_id,
            worker_id=worker_id,
            lease_token=self.lease_token,
            attempt=1,
            acquired_at=now,
            heartbeat_at=now,
            expires_at=now + timedelta(seconds=30),
        )

    async def claim_lease(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        worker_id: str,
        ttl_seconds: int,
    ) -> ResearchWorkerLeaseRecord | None:
        self.claim_calls.append(
            {
                "tenant_id": tenant_id,
                "research_run_id": research_run_id,
                "worker_id": worker_id,
                "ttl_seconds": ttl_seconds,
            }
        )
        if not self.claim:
            return None
        return self._lease(
            tenant_id=tenant_id,
            research_run_id=research_run_id,
            worker_id=worker_id,
        )

    async def renew_lease(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        worker_id: str,
        lease_token: UUID,
        ttl_seconds: int,
    ) -> ResearchWorkerLeaseRecord | None:
        del lease_token, ttl_seconds
        self.renew_calls += 1
        return self._lease(
            tenant_id=tenant_id,
            research_run_id=research_run_id,
            worker_id=worker_id,
        )

    async def release_lease(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        worker_id: str,
        lease_token: UUID,
    ) -> bool:
        self.release_calls.append(
            {
                "tenant_id": tenant_id,
                "research_run_id": research_run_id,
                "worker_id": worker_id,
                "lease_token": lease_token,
            }
        )
        self.released.set()
        return True

    async def append_checkpoint(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        sequence: int,
        node_name: str,
        state: Mapping[str, object],
    ) -> ResearchCheckpointRecord:
        del tenant_id, research_run_id
        self.checkpoints.append((sequence, node_name, state))
        return ResearchCheckpointRecord(
            sequence=sequence,
            node_name=node_name,
            state=dict(state),
            created_at=datetime.now(UTC),
        )

    async def get_latest_checkpoint(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> ResearchCheckpointRecord | None:
        del tenant_id, research_run_id
        return None

    async def append_audit_event(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
        event_type: str,
        actor_type: str,
        actor_id: str | None = None,
        details: Mapping[str, object] | None = None,
    ) -> None:
        del tenant_id, research_run_id, actor_type, actor_id, details
        self.audit_events.append(event_type)


@pytest.mark.anyio
async def test_job_manager_persists_queue_before_returning_identity() -> None:
    executor = RecordingBackgroundExecutor(block=True)
    manager = ResearchJobManager(executor)
    tenant_id = uuid4()
    user_id = uuid4()

    research_run_id = await manager.submit(
        tenant_id=tenant_id,
        query="  Explain epoll.  ",
        llm_provider="qwen",
        requested_by_user_id=user_id,
    )
    await executor.started.wait()

    assert executor.queue_calls == [
        {
            "tenant_id": tenant_id,
            "query": "  Explain epoll.  ",
            "llm_provider": "qwen",
            "requested_by_user_id": user_id,
        }
    ]
    assert executor.execute_calls[0].research_run_id == research_run_id

    executor.release.set()
    await asyncio.sleep(0)
    await manager.close()


@pytest.mark.anyio
async def test_job_manager_rejects_submission_after_close() -> None:
    manager = ResearchJobManager(RecordingBackgroundExecutor())
    await manager.close()

    with pytest.raises(RuntimeError, match="job manager is closed"):
        await manager.submit(
            tenant_id=uuid4(),
            query="Explain epoll.",
            llm_provider="qwen",
        )


@pytest.mark.anyio
async def test_job_manager_cancels_outstanding_tasks_on_close() -> None:
    executor = RecordingBackgroundExecutor(block=True)
    manager = ResearchJobManager(executor)

    await manager.submit(
        tenant_id=uuid4(),
        query="Explain epoll.",
        llm_provider="qwen",
    )
    await executor.started.wait()
    await manager.close()

    assert len(executor.execute_calls) == 1


@pytest.mark.anyio
async def test_job_manager_executes_only_after_claiming_durable_lease() -> None:
    executor = RecordingBackgroundExecutor()
    durability = RecordingDurabilityStore()
    manager = ResearchJobManager(
        executor,
        durability,
        worker_id="worker-test",
    )

    await manager.submit(
        tenant_id=uuid4(),
        query="Explain epoll.",
        llm_provider="qwen",
    )
    await executor.started.wait()
    await durability.released.wait()
    await manager.close()

    assert durability.claim_calls[0]["worker_id"] == "worker-test"
    assert [item[:2] for item in durability.checkpoints] == [
        (0, "queued"),
        (1, "completed"),
    ]
    assert durability.audit_events == ["worker.claimed", "worker.completed"]
    assert durability.release_calls[0]["lease_token"] == durability.lease_token


@pytest.mark.anyio
async def test_job_manager_does_not_execute_run_owned_by_another_worker() -> None:
    executor = RecordingBackgroundExecutor()
    durability = RecordingDurabilityStore(claim=False)
    manager = ResearchJobManager(
        executor,
        durability,
        worker_id="worker-test",
    )

    await manager.submit(
        tenant_id=uuid4(),
        query="Explain epoll.",
        llm_provider="qwen",
    )
    await asyncio.sleep(0)
    await asyncio.sleep(0)
    await manager.close()

    assert executor.execute_calls == []
    assert durability.checkpoints == []
    assert durability.release_calls == []


@pytest.mark.anyio
async def test_job_manager_renews_lease_while_execution_is_running() -> None:
    executor = RecordingBackgroundExecutor(block=True)
    durability = RecordingDurabilityStore()
    manager = ResearchJobManager(
        executor,
        durability,
        worker_id="worker-test",
        lease_ttl_seconds=1,
        heartbeat_seconds=0.01,
    )

    await manager.submit(
        tenant_id=uuid4(),
        query="Explain epoll.",
        llm_provider="qwen",
    )
    await executor.started.wait()
    await asyncio.sleep(0.03)
    executor.release.set()
    await asyncio.sleep(0)
    await manager.close()

    assert durability.renew_calls >= 1
