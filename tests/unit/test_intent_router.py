from unittest.mock import AsyncMock

import pytest

from app.agents.intent_router import (
    IntentRouter,
    classify_route_by_rule,
)
from app.schemas.intent import IntentDecision
from app.services.llm.anthropic import AnthropicClient


def test_rule_classifier_routes_stable_question_directly() -> None:
    result = classify_route_by_rule(
        "Explain idempotency in REST APIs."
    )

    assert result == "direct"


def test_rule_classifier_routes_comparison_to_deep_research() -> None:
    result = classify_route_by_rule(
        "Compare HTTP/2 and HTTP/3 using current sources."
    )

    assert result == "deep_research"


@pytest.mark.anyio
async def test_intent_router_returns_anthropic_decision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm_client = AnthropicClient()

    generate_structured = AsyncMock(
        return_value=IntentDecision(
            route="deep_research",
            reason=(
                "The request requires current technical sources "
                "and protocol comparison."
            ),
        )
    )
    monkeypatch.setattr(
        llm_client,
        "generate_structured",
        generate_structured,
    )

    router = IntentRouter(llm_client)

    decision = await router.classify(
        "Compare HTTP/2 and HTTP/3 using current sources."
    )

    assert decision.route == "deep_research"
    assert "current technical sources" in decision.reason

    generate_structured.assert_awaited_once()


@pytest.mark.anyio
async def test_intent_router_uses_rule_fallback_on_claude_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm_client = AnthropicClient()

    generate_structured = AsyncMock(
        side_effect=RuntimeError("Claude is temporarily unavailable.")
    )
    monkeypatch.setattr(
        llm_client,
        "generate_structured",
        generate_structured,
    )

    router = IntentRouter(llm_client)

    decision = await router.classify(
        "Analyze Kubernetes Deployment and StatefulSet trade-offs."
    )

    assert decision.route == "deep_research"
    assert "fallback" in decision.reason.lower()


@pytest.mark.anyio
async def test_intent_router_rejects_empty_query() -> None:
    llm_client = AnthropicClient()
    router = IntentRouter(llm_client)

    with pytest.raises(ValueError, match="Query must not be empty"):
        await router.classify("   ")
