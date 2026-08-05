import asyncio
import logging
import os
import socket
from typing import Protocol
from uuid import UUID, uuid4

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
        self._closed = False

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
        task = asyncio.create_task(
            self._execute_owned(queued),
            name=f"research-run-{queued.research_run_id}",
        )
        self._tasks.add(task)
        task.add_done_callback(self._task_completed)

        return queued.research_run_id

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

    def _task_completed(
        self,
        task: asyncio.Task[ResearchExecutionResult | None],
    ) -> None:
        self._tasks.discard(task)

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
            sequence=0,
            node_name="queued",
            state={
                "query": queued.query,
                "tenant_id": queued.tenant_id,
                "requested_by_user_id": queued.requested_by_user_id,
                "llm_provider": queued.llm_provider,
                "status": "queued",
            },
        )
        heartbeat = asyncio.create_task(
            self._heartbeat(queued, lease),
            name=f"research-heartbeat-{queued.research_run_id}",
        )

        try:
            result = await self._executor.execute_queued(queued)
            await store.append_checkpoint(
                tenant_id=queued.tenant_id,
                research_run_id=queued.research_run_id,
                sequence=1,
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
                return

    @staticmethod
    def _default_worker_id() -> str:
        return f"{socket.gethostname()}-{os.getpid()}-{uuid4().hex[:12]}"
