import json
from collections.abc import Callable

import httpx
import pytest

from app.schemas.evaluation import EvaluationCase
from app.services.evaluation import (
    EvaluationAuthenticationError,
    authenticate,
    execute_case,
    run_evaluation,
)


def make_client(handler: Callable[[httpx.Request], httpx.Response]) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url="http://testserver",
        transport=httpx.MockTransport(handler),
    )


def json_response(status_code: int, body: object) -> httpx.Response:
    return httpx.Response(
        status_code,
        content=json.dumps(body),
        headers={"Content-Type": "application/json"},
    )


def create_case(
    *,
    expected_route: str = "deep_research",
    min_independent_sources: int = 0,
    requires_private_knowledge: bool = False,
    expected_report_sections: list[str] | None = None,
) -> EvaluationCase:
    return EvaluationCase(
        id="case-1",
        query="Compare HTTP/2 and HTTP/3.",
        expected_route=expected_route,  # type: ignore[arg-type]
        min_independent_sources=min_independent_sources,
        requires_private_knowledge=requires_private_knowledge,
        expected_report_sections=expected_report_sections or [],
    )


class TestAuthenticate:
    @pytest.mark.anyio
    async def test_logs_in_without_registering_when_the_account_exists(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)

            if request.url.path == "/auth/login":
                return json_response(200, {"user": {}, "tenant": {}})

            raise AssertionError("register must not be called when login succeeds.")

        async with make_client(handler) as client:
            await authenticate(
                client,
                email="eval@example.com",
                password="correct-horse-battery",
                tenant_name="Evaluation",
            )

        assert calls == ["/auth/login"]

    @pytest.mark.anyio
    async def test_registers_when_no_account_exists_yet(self) -> None:
        calls: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request.url.path)

            if request.url.path == "/auth/login":
                return json_response(401, {"detail": "Invalid email or password."})

            if request.url.path == "/auth/register":
                return json_response(201, {"user": {}, "tenant": {}})

            raise AssertionError(f"unexpected path {request.url.path}")

        async with make_client(handler) as client:
            await authenticate(
                client,
                email="eval@example.com",
                password="correct-horse-battery",
                tenant_name="Evaluation",
            )

        assert calls == ["/auth/login", "/auth/register"]

    @pytest.mark.anyio
    async def test_raises_when_both_login_and_register_fail(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/auth/login":
                return json_response(401, {"detail": "Invalid email or password."})

            return json_response(409, {"detail": "Email is already registered."})

        async with make_client(handler) as client:
            with pytest.raises(EvaluationAuthenticationError):
                await authenticate(
                    client,
                    email="eval@example.com",
                    password="wrong-password",
                    tenant_name="Evaluation",
                )


class TestExecuteCase:
    @pytest.mark.anyio
    async def test_captures_a_successful_deep_research_outcome(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/research-runs":
                return json_response(
                    200,
                    {
                        "research_run_id": "89e4ac76-dfc4-4fc1-b0d7-a4ed6923f589",
                        "status": "completed",
                        "route": "deep_research",
                        "answer": "# Executive Summary\n\nHTTP/3 uses QUIC.\n\n## Trade-offs\n",
                        "citation_valid": True,
                        "citation_coverage": 0.9,
                        "human_review_required": False,
                        "cache_hit": False,
                    },
                )

            assert request.url.path == (
                "/research-runs/89e4ac76-dfc4-4fc1-b0d7-a4ed6923f589/sources"
            )
            return json_response(
                200,
                [
                    {"source_id": "WEB-1", "origin": "web", "cited": True},
                    {"source_id": "WEB-2", "origin": "web", "cited": False},
                    {"source_id": "PRIVATE-1", "origin": "private", "cited": True},
                ],
            )

        async with make_client(handler) as client:
            outcome = await execute_case(client, create_case(), provider="qwen")

        assert outcome.status == "completed"
        assert outcome.route == "deep_research"
        assert outcome.cited_source_count == 2
        assert outcome.cited_private_source_count == 1
        assert outcome.report_sections == ["Executive Summary", "Trade-offs"]
        assert outcome.error is None
        assert outcome.latency_seconds >= 0

    @pytest.mark.anyio
    async def test_direct_route_with_no_sources_endpoint_defaults_to_zero_sources(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/research-runs":
                return json_response(
                    200,
                    {
                        "research_run_id": "89e4ac76-dfc4-4fc1-b0d7-a4ed6923f589",
                        "status": "completed",
                        "route": "direct",
                        "answer": "A mutex is a mutual-exclusion lock.",
                    },
                )

            return json_response(404, {"detail": "Research sources were not found."})

        async with make_client(handler) as client:
            outcome = await execute_case(
                client,
                create_case(expected_route="direct", min_independent_sources=0),
                provider="qwen",
            )

        assert outcome.status == "completed"
        assert outcome.cited_source_count == 0
        assert outcome.report_sections == []

    @pytest.mark.anyio
    async def test_records_an_http_error_status_as_a_failed_outcome(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            return json_response(429, {"detail": "Research request rate limit exceeded."})

        async with make_client(handler) as client:
            outcome = await execute_case(client, create_case(), provider="qwen")

        assert outcome.status == "failed"
        assert outcome.error is not None
        assert "429" in outcome.error

    @pytest.mark.anyio
    async def test_records_a_network_error_as_a_failed_outcome(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Connection refused.", request=request)

        async with make_client(handler) as client:
            outcome = await execute_case(client, create_case(), provider="qwen")

        assert outcome.status == "failed"
        assert outcome.error is not None
        assert "ConnectError" in outcome.error


class TestRunEvaluation:
    @pytest.mark.anyio
    async def test_isolates_one_case_failure_from_the_rest(self) -> None:
        cases = [
            create_case(expected_route="direct", min_independent_sources=0),
            create_case(expected_route="deep_research"),
        ]

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path != "/research-runs":
                return json_response(200, [])

            payload = json.loads(request.content)

            if payload["llm_provider"] == "qwen" and "second" not in payload["query"]:
                return json_response(500, {"detail": "boom"})

            return json_response(
                200,
                {
                    "research_run_id": "89e4ac76-dfc4-4fc1-b0d7-a4ed6923f589",
                    "status": "completed",
                    "route": "deep_research",
                    "answer": "",
                },
            )

        async with make_client(handler) as client:
            results = await run_evaluation(cases, client, provider="qwen")

        assert len(results) == 2
        assert results[0].outcome.status == "failed"
        assert results[0].passed is False
