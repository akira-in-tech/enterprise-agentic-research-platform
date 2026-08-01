from typing import Protocol
from uuid import UUID

from app.schemas.idempotency import ResearchIdempotencyRecord
from app.schemas.research import CreateResearchRunResponse
from app.services.cache import (
    CacheUnavailableError,
    create_research_request_fingerprint,
)
from app.services.llm.factory import (
    normalize_llm_provider,
)
from app.services.research.execution import ResearchExecutionResult
from app.workflow.state import ResearchState


class ResearchExecutor(Protocol):
    """Execute one non-idempotent research operation."""

    async def execute(
        self,
        *,
        tenant_id: UUID,
        query: str,
        llm_provider: str,
        requested_by_user_id: UUID | None = None,
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


class ResearchIdempotencyConflictError(ValueError):
    """Signal reuse of one key for a different request."""


class ResearchIdempotencyUnavailableError(RuntimeError):
    """Signal that idempotency correctness cannot be guaranteed."""


class IdempotentResearchExecutionService:
    """Replay completed requests before delegating new execution."""

    def __init__(
        self,
        executor: ResearchExecutor,
        store: ResearchIdempotencyStore,
    ) -> None:
        self._executor = executor
        self._store = store

    async def execute(
        self,
        *,
        tenant_id: UUID,
        query: str,
        llm_provider: str,
        requested_by_user_id: UUID | None = None,
        idempotency_key: str | None = None,
    ) -> ResearchExecutionResult:
        """Replay or execute one sequential idempotent request."""

        if idempotency_key is None:
            return await self._executor.execute(
                tenant_id=tenant_id,
                query=query,
                llm_provider=llm_provider,
                requested_by_user_id=requested_by_user_id,
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
        )

        existing_record = await self._get_record(
            tenant_id=tenant_id,
            client_key=normalized_key,
        )

        if existing_record is not None:
            if existing_record.request_fingerprint != request_fingerprint:
                raise ResearchIdempotencyConflictError(
                    "Idempotency key was already used for a different research request."
                )

            return self._restore_result(
                query=normalized_query,
                response=existing_record.response,
            )

        result = await self._executor.execute(
            tenant_id=tenant_id,
            query=normalized_query,
            llm_provider=llm_provider,
            requested_by_user_id=requested_by_user_id,
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
