import asyncio
import logging
import os
import socket
from typing import Protocol
from uuid import UUID, uuid4

from app.services.llm.factory import normalize_llm_provider
from app.services.research.durability import (
    ResearchDurabilityStore,
    ResearchWorkerLeaseRecord,
)
from app.services.research.execution import (
    QueuedResearchExecution,
    ResearchExecutionResult,
)

logger = logging.getLogger(__name__)


class BackgroundResearchExecutor(Protocol):
    """Queue durable runs and execute them after the API accepts the job."""

    async def queue(
        self,
        *,
        tenant_id: UUID,
        query: str,
        llm_provider: str,
        requested_by_user_id: UUID | None = None,
        research_run_id: UUID | None = None,
    ) -> QueuedResearchExecution:
        """Persist one queued run."""

    async def execute_queued(
        self,
        queued: QueuedResearchExecution,
    ) -> ResearchExecutionResult:
        """Execute a previously persisted run."""

    async def cancel(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> bool:
        """Durably cancel one queued or running run."""


class ResearchJobManager:
    """Execute durable jobs only while this worker owns their database lease."""

    def __init__(
        self,
        executor: BackgroundResearchExecutor,
        durability_store: ResearchDurabilityStore | None = None,
        *,
        worker_id: str | None = None,
        lease_ttl_seconds: int = 30,
        heartbeat_seconds: float = 10.0,
    ) -> None:
        if heartbeat_seconds >= lease_ttl_seconds:
            raise ValueError("heartbeat_seconds must be shorter than lease_ttl_seconds.")
        self._executor = executor
        self._durability_store = durability_store
        self._worker_id = worker_id or self._default_worker_id()
        self._lease_ttl_seconds = lease_ttl_seconds
        self._heartbeat_seconds = heartbeat_seconds
        self._tasks: set[asyncio.Task[ResearchExecutionResult | None]] = set()
        self._tasks_by_run: dict[
            tuple[UUID, UUID],
            asyncio.Task[ResearchExecutionResult | None],
        ] = {}
        self._task_keys: dict[
            asyncio.Task[ResearchExecutionResult | None],
            tuple[UUID, UUID],
        ] = {}
        self._closed = False
        self._started = False

    async def start(self) -> int:
        """Recover accepted runs that no live worker currently owns."""

        if self._closed:
            raise RuntimeError("Research job manager is closed.")
        if self._started:
            return 0
        self._started = True
        if self._durability_store is None:
            return 0

        recoverable = await self._durability_store.list_recoverable_runs()
        for run in recoverable:
            self._schedule(
                QueuedResearchExecution(
                    research_run_id=run.research_run_id,
                    tenant_id=run.tenant_id,
                    requested_by_user_id=run.requested_by_user_id,
                    query=run.query,
                    llm_provider=normalize_llm_provider(run.llm_provider),
                    resume=run.status == "running",
                )
            )
        return len(recoverable)

    async def submit(
        self,
        *,
        tenant_id: UUID,
        query: str,
        llm_provider: str,
        requested_by_user_id: UUID | None = None,
    ) -> UUID:
        """Persist one queued run and start its background execution."""

        if self._closed:
            raise RuntimeError("Research job manager is closed.")

        queued = await self._executor.queue(
            tenant_id=tenant_id,
            query=query,
            llm_provider=llm_provider,
            requested_by_user_id=requested_by_user_id,
        )
        self._schedule(queued)

        return queued.research_run_id

    def _schedule(self, queued: QueuedResearchExecution) -> None:
        task = asyncio.create_task(
            self._execute_owned(queued),
            name=f"research-run-{queued.research_run_id}",
        )
        key = (queued.tenant_id, queued.research_run_id)
        self._tasks.add(task)
        self._tasks_by_run[key] = task
        self._task_keys[task] = key
        task.add_done_callback(self._task_completed)

    async def cancel(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> bool:
        """Stop local work and persist cancellation within the tenant boundary."""

        persisted = await self._executor.cancel(
            tenant_id=tenant_id,
            research_run_id=research_run_id,
        )
        if not persisted:
            return False

        task = self._tasks_by_run.get((tenant_id, research_run_id))
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        return True

    async def close(self) -> None:
        """Cancel and await outstanding tasks during application shutdown."""

        self._closed = True
        tasks = tuple(self._tasks)

        for task in tasks:
            task.cancel()

        if tasks:
            await asyncio.gather(
                *tasks,
                return_exceptions=True,
            )

        self._tasks.clear()
        self._tasks_by_run.clear()
        self._task_keys.clear()

    def _task_completed(
        self,
        task: asyncio.Task[ResearchExecutionResult | None],
    ) -> None:
        self._tasks.discard(task)
        key = self._task_keys.pop(task, None)
        if key is not None and self._tasks_by_run.get(key) is task:
            self._tasks_by_run.pop(key, None)

        if task.cancelled():
            return

        error = task.exception()

        if error is not None:
            logger.error(
                "Background research execution failed.",
                exc_info=(type(error), error, error.__traceback__),
            )

    async def _execute_owned(
        self,
        queued: QueuedResearchExecution,
    ) -> ResearchExecutionResult | None:
        store = self._durability_store
        if store is None:
            return await self._executor.execute_queued(queued)

        lease = await store.claim_lease(
            tenant_id=queued.tenant_id,
            research_run_id=queued.research_run_id,
            worker_id=self._worker_id,
            ttl_seconds=self._lease_ttl_seconds,
        )
        if lease is None:
            logger.info(
                "Research run is already owned by another worker.",
                extra={"research_run_id": str(queued.research_run_id)},
            )
            return None

        await store.append_audit_event(
            tenant_id=queued.tenant_id,
            research_run_id=queued.research_run_id,
            event_type="worker.claimed",
            actor_type="worker",
            actor_id=self._worker_id,
            details={"attempt": lease.attempt},
        )
        await store.append_checkpoint(
            tenant_id=queued.tenant_id,
            research_run_id=queued.research_run_id,
            sequence=(lease.attempt - 1) * 2,
            node_name="resumed" if queued.resume else "queued",
            state={
                "query": queued.query,
                "tenant_id": queued.tenant_id,
                "requested_by_user_id": queued.requested_by_user_id,
                "llm_provider": queued.llm_provider,
                "status": "running" if queued.resume else "queued",
            },
        )
        owner_task = asyncio.current_task()
        assert owner_task is not None
        heartbeat = asyncio.create_task(
            self._heartbeat(queued, lease, owner_task),
            name=f"research-heartbeat-{queued.research_run_id}",
        )

        try:
            result = await self._executor.execute_queued(queued)
            await store.append_checkpoint(
                tenant_id=queued.tenant_id,
                research_run_id=queued.research_run_id,
                sequence=(lease.attempt - 1) * 2 + 1,
                node_name="completed",
                state=result.state,
            )
            await store.append_audit_event(
                tenant_id=queued.tenant_id,
                research_run_id=queued.research_run_id,
                event_type="worker.completed",
                actor_type="worker",
                actor_id=self._worker_id,
                details={"attempt": lease.attempt},
            )
            return result
        except BaseException as error:
            await store.append_audit_event(
                tenant_id=queued.tenant_id,
                research_run_id=queued.research_run_id,
                event_type="worker.interrupted",
                actor_type="worker",
                actor_id=self._worker_id,
                details={"error_type": type(error).__name__},
            )
            raise
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)
            await store.release_lease(
                tenant_id=queued.tenant_id,
                research_run_id=queued.research_run_id,
                worker_id=self._worker_id,
                lease_token=lease.lease_token,
            )

    async def _heartbeat(
        self,
        queued: QueuedResearchExecution,
        lease: ResearchWorkerLeaseRecord,
        owner_task: asyncio.Task[object],
    ) -> None:
        assert self._durability_store is not None
        while True:
            await asyncio.sleep(self._heartbeat_seconds)
            renewed = await self._durability_store.renew_lease(
                tenant_id=queued.tenant_id,
                research_run_id=queued.research_run_id,
                worker_id=self._worker_id,
                lease_token=lease.lease_token,
                ttl_seconds=self._lease_ttl_seconds,
            )
            if renewed is None:
                logger.error(
                    "Research worker lost its lease.",
                    extra={"research_run_id": str(queued.research_run_id)},
                )
                owner_task.cancel()
                return

    @staticmethod
    def _default_worker_id() -> str:
        return f"{socket.gethostname()}-{os.getpid()}-{uuid4().hex[:12]}"
