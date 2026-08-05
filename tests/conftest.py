from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager

import pytest
from fastapi import FastAPI

from app.main import app


@asynccontextmanager
async def _unit_test_lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Keep API unit tests isolated from real application resources."""

    yield


@pytest.fixture(autouse=True)
def isolate_unit_tests_from_application_lifespan(
    request: pytest.FixtureRequest,
) -> Iterator[None]:
    """Run the real lifespan only in explicitly marked integration tests."""

    if request.node.get_closest_marker("integration") is not None:
        yield
        return

    original_lifespan = app.router.lifespan_context
    app.router.lifespan_context = _unit_test_lifespan
    try:
        yield
    finally:
        app.router.lifespan_context = original_lifespan
