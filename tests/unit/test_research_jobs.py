import asyncio
from uuid import UUID, uuid4

import pytest

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
