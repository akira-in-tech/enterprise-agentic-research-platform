import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import cast
from uuid import UUID, uuid4

import pytest

from app.api.research import _research_progress_events
from app.schemas.progress import ResearchProgressRecord


class StaticProgressStore:
    """Return the same unchanged record on every poll, like a long-running step."""

    def __init__(self, record: ResearchProgressRecord) -> None:
        self.record = record

    async def get(
        self,
        *,
        tenant_id: UUID,
        research_run_id: UUID,
    ) -> ResearchProgressRecord | None:
        return self.record


@pytest.mark.anyio
async def test_heartbeat_keeps_the_stream_alive_during_an_unchanged_step() -> None:
    """A long agent step publishes no new progress, but the stream must not go silent.

    Real dev-server and intermediate proxies drop a streaming connection
    after a period with no bytes on the wire. Without a periodic
    keepalive, a single long LLM call (a minute or more) leaves the SSE
    response silent for the whole call, which is exactly what an idle
    proxy timeout looks for.
    """

    record = ResearchProgressRecord(
        research_run_id=uuid4(),
        status="running",
        message="Running analyst.",
        updated_at=datetime.now(UTC),
        workflow_status="analyst",
    )
    store = StaticProgressStore(record)

    events = cast(
        AsyncGenerator[str],
        _research_progress_events(
            tenant_id=uuid4(),
            research_run_id=record.research_run_id,
            progress_store=store,  # type: ignore[arg-type]
            poll_interval_seconds=0.01,
            heartbeat_interval_seconds=0.05,
        ),
    )

    try:
        first = await asyncio.wait_for(anext(events), timeout=2)
        assert first.startswith("event: progress\n")

        heartbeat = await asyncio.wait_for(anext(events), timeout=2)
        assert heartbeat == ": keepalive\n\n"
    finally:
        await events.aclose()
