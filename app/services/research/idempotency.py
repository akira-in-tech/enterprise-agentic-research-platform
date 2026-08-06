import asyncio
import logging
from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from app.core.config import settings
from app.schemas.idempotency import ResearchIdempotencyRecord
from app.schemas.research import CreateResearchRunResponse
from app.services.cache import (
    CacheUnavailableError,
    ResearchIdempotencyLockLease,
    create_research_request_fingerprint,
)
from app.services.llm.factory import (
    normalize_llm_provider,
)
from app.services.research.execution import ResearchExecutionResult
from app.workflow.state import ResearchState

logger = logging.getLogger(__name__)


class ResearchExecutor(Protocol):
    """Execute one non-idempotent research operation."""

    async def execute(
        self,
        *,
        tenant_id: UUID,
        query: str,
        llm_provider: str,
        requested_by_user_id: UUID | None = None,
        document_ids: Sequence[str] | None = None,
    ) -> ResearchExecutionResult:
        """Execute one research request."""


class ResearchIdempotencyStore(Protocol):
    """Read and write completed idempotency records."""

    async def get(
        self,
        *,
        tenant_id: UUID,
        client_key: str,
    ) -> ResearchIdempotencyRecord | None:
        """Return one completed record or a miss."""

    async def set(
        self,
        *,
        tenant_id: UUID,
        client_key: str,
        record: ResearchIdempotencyRecord,
    ) -> None:
        """Store one completed record."""


class ResearchIdempotencyLockManager(Protocol):
    """Coordinate exclusive execution for one idempotency key."""

    async def acquire(
        self,
        *,
        tenant_id: UUID,
        client_key: str,
    ) -> ResearchIdempotencyLockLease | None:
        """Acquire one lock lease or return None when already held."""

    async def release(
        self,
        lease: ResearchIdempotencyLockLease,
    ) -> bool:
        """Release a currently owned lock lease."""

    async def renew(
        self,
        lease: ResearchIdempotencyLockLease,
    ) -> bool:
        """Extend a currently owned lock lease's TTL."""


class ResearchIdempotencyConflictError(ValueError):
    """Signal reuse of one key for a different request."""


class ResearchIdempotencyUnavailableError(RuntimeError):
    """Signal that idempotency correctness cannot be guaranteed."""


class ResearchIdempotencyInProgressError(RuntimeError):
    """Signal that an equivalent idempotent request is still running."""


class IdempotentResearchExecutionService:
    """Replay completed requests before delegating new execution."""

    def __init__(
        self,
        executor: ResearchExecutor,
        store: ResearchIdempotencyStore,
        lock_manager: ResearchIdempotencyLockManager,
        *,
        renew_interval_seconds: float | None = None,
    ) -> None:
        self._executor = executor
        self._store = store
        self._lock_manager = lock_manager
        self._renew_interval_seconds = (
            renew_interval_seconds
            if renew_interval_seconds is not None
            else settings.redis_research_idempotency_lock_renew_interval_seconds
        )

    async def execute(
        self,
        *,
        tenant_id: UUID,
        query: str,
        llm_provider: str,
        requested_by_user_id: UUID | None = None,
        idempotency_key: str | None = None,
        document_ids: Sequence[str] | None = None,
    ) -> ResearchExecutionResult:
        """Replay or execute one sequential idempotent request."""

        if idempotency_key is None:
            return await self._executor.execute(
                tenant_id=tenant_id,
                query=query,
                llm_provider=llm_provider,
                requested_by_user_id=requested_by_user_id,
                document_ids=document_ids,
            )

        normalized_key = idempotency_key.strip()

        if not normalized_key:
            raise ValueError("idempotency_key must not be empty.")

        normalized_query = query.strip()

        if not normalized_query:
            raise ValueError("query must not be empty.")

        canonical_provider = normalize_llm_provider(
            llm_provider,
        )
        request_fingerprint = create_research_request_fingerprint(
            query=normalized_query,
            llm_provider=canonical_provider,
            requested_by_user_id=requested_by_user_id,
            document_ids=document_ids,
        )

        existing_result = await self._restore_existing_record(
            tenant_id=tenant_id,
            client_key=normalized_key,
            query=normalized_query,
            request_fingerprint=request_fingerprint,
        )

        if existing_result is not None:
            return existing_result

        lease = await self._acquire_lock(
            tenant_id=tenant_id,
            client_key=normalized_key,
        )

        if lease is None:
            raise ResearchIdempotencyInProgressError(
                "Research request with this idempotency key is already in progress."
            )

        try:
            existing_result = await self._restore_existing_record(
                tenant_id=tenant_id,
                client_key=normalized_key,
                query=normalized_query,
                request_fingerprint=request_fingerprint,
            )

            if existing_result is not None:
                return existing_result

            result = await self._execute_with_lease_renewal(
                lease,
                tenant_id=tenant_id,
                query=normalized_query,
                llm_provider=llm_provider,
                requested_by_user_id=requested_by_user_id,
                document_ids=document_ids,
            )
            record = ResearchIdempotencyRecord(
                request_fingerprint=request_fingerprint,
                response=self._build_response(
                    result,
                ),
            )

            await self._set_record(
                tenant_id=tenant_id,
                client_key=normalized_key,
                record=record,
            )

            return result
        finally:
            await self._release_lock(
                lease,
            )

    async def _execute_with_lease_renewal(
        self,
        lease: ResearchIdempotencyLockLease,
        *,
        tenant_id: UUID,
        query: str,
        llm_provider: str,
        requested_by_user_id: UUID | None,
        document_ids: Sequence[str] | None = None,
    ) -> ResearchExecutionResult:
        """Run the executor while periodically renewing the coordination lock.

        The lock's TTL is a fixed bound (default 300s); without renewal, an
        execution that runs longer than the TTL would lose exclusivity mid-
        flight, letting a concurrent request for the same idempotency key
        start a second execution. If renewal ever confirms the lease was
        lost, this cancels the execution itself rather than let two
        processes race to write the same completed idempotency record.
        """

        owner_task = asyncio.current_task()
        assert owner_task is not None

        heartbeat = asyncio.create_task(
            self._renew_lease_periodically(lease, owner_task),
        )

        try:
            return await self._executor.execute(
                tenant_id=tenant_id,
                query=query,
                llm_provider=llm_provider,
                requested_by_user_id=requested_by_user_id,
                document_ids=document_ids,
            )
        finally:
            heartbeat.cancel()
            await asyncio.gather(heartbeat, return_exceptions=True)

    async def _renew_lease_periodically(
        self,
        lease: ResearchIdempotencyLockLease,
        owner_task: asyncio.Task[object],
    ) -> None:
        while True:
            await asyncio.sleep(self._renew_interval_seconds)

            try:
                renewed = await self._lock_manager.renew(lease)
            except CacheUnavailableError:
                logger.warning(
                    "Research idempotency lock could not be renewed; "
                    "Redis is temporarily unavailable.",
                    exc_info=True,
                )
                continue

            if not renewed:
                logger.error(
                    "Research idempotency lock lease was lost before execution "
                    "completed; cancelling the in-flight execution to avoid a "
                    "duplicate completed record."
                )
                owner_task.cancel()
                return

    async def _restore_existing_record(
        self,
        *,
        tenant_id: UUID,
        client_key: str,
        query: str,
        request_fingerprint: str,
    ) -> ResearchExecutionResult | None:
        existing_record = await self._get_record(
            tenant_id=tenant_id,
            client_key=client_key,
        )

        if existing_record is None:
            return None

        if existing_record.request_fingerprint != request_fingerprint:
            raise ResearchIdempotencyConflictError(
                "Idempotency key was already used for a different research request."
            )

        return self._restore_result(
            query=query,
            response=existing_record.response,
        )

    async def _acquire_lock(
        self,
        *,
        tenant_id: UUID,
        client_key: str,
    ) -> ResearchIdempotencyLockLease | None:
        try:
            return await self._lock_manager.acquire(
                tenant_id=tenant_id,
                client_key=client_key,
            )
        except CacheUnavailableError as error:
            raise ResearchIdempotencyUnavailableError(
                "Research idempotency lock is unavailable."
            ) from error

    async def _release_lock(
        self,
        lease: ResearchIdempotencyLockLease,
    ) -> None:
        try:
            released = await self._lock_manager.release(
                lease,
            )
        except CacheUnavailableError:
            logger.warning(
                "Research idempotency lock could not be released; "
                "the lock TTL will provide eventual cleanup.",
                exc_info=True,
            )
            return

        if not released:
            logger.warning("Research idempotency lock lease no longer owns its Redis key.")

    async def _get_record(
        self,
        *,
        tenant_id: UUID,
        client_key: str,
    ) -> ResearchIdempotencyRecord | None:
        try:
            return await self._store.get(
                tenant_id=tenant_id,
                client_key=client_key,
            )
        except CacheUnavailableError as error:
            raise ResearchIdempotencyUnavailableError(
                "Research idempotency store is unavailable."
            ) from error

    async def _set_record(
        self,
        *,
        tenant_id: UUID,
        client_key: str,
        record: ResearchIdempotencyRecord,
    ) -> None:
        try:
            await self._store.set(
                tenant_id=tenant_id,
                client_key=client_key,
                record=record,
            )
        except CacheUnavailableError as error:
            raise ResearchIdempotencyUnavailableError(
                "Research idempotency record could not be stored."
            ) from error

    @staticmethod
    def _build_response(
        result: ResearchExecutionResult,
    ) -> CreateResearchRunResponse:
        return CreateResearchRunResponse(
            research_run_id=result.research_run_id,
            llm_provider=result.llm_provider,
            status="completed",
            cache_hit=result.cache_hit,
            workflow_status=result.state.get(
                "status",
                "completed",
            ),
            route=result.state.get("route"),
            route_reason=result.state.get("route_reason"),
            answer=result.state.get("answer"),
            citation_valid=(
                result.state["citation_audit"].valid if "citation_audit" in result.state else None
            ),
            citation_coverage=(
                result.state["citation_audit"].coverage_ratio
                if "citation_audit" in result.state
                else None
            ),
            reflection_status=(
                result.state["reflection"].status if "reflection" in result.state else None
            ),
            reflection_reasons=(
                result.state["reflection"].reasons if "reflection" in result.state else []
            ),
            human_review_required=(
                result.state["reflection"].human_review_required
                if "reflection" in result.state
                else False
            ),
            human_review_reason=(
                result.state["reflection"].human_review_reason
                if "reflection" in result.state
                else None
            ),
        )

    @staticmethod
    def _restore_result(
        *,
        query: str,
        response: CreateResearchRunResponse,
    ) -> ResearchExecutionResult:
        state: ResearchState = {
            "query": query,
            "status": response.workflow_status,
        }

        if response.route is not None:
            state["route"] = response.route

        if response.route_reason is not None:
            state["route_reason"] = response.route_reason

        if response.answer is not None:
            state["answer"] = response.answer

        return ResearchExecutionResult(
            research_run_id=response.research_run_id,
            llm_provider=response.llm_provider,
            state=state,
            cache_hit=response.cache_hit,
            idempotency_replayed=True,
        )
