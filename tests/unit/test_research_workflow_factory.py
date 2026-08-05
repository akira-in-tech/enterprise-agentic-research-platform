from unittest.mock import Mock

import pytest

from app.services.research import execution as execution_module


class RecordingLLMClient:
    def __init__(self) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


@pytest.mark.anyio
async def test_default_workflow_injects_local_scout_and_closes_request_llm(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm_client = RecordingLLMClient()
    local_scout = Mock()
    graph = Mock()
    create_client = Mock(return_value=llm_client)
    build_graph = Mock(return_value=graph)
    monkeypatch.setattr(
        execution_module,
        "create_llm_client",
        create_client,
    )
    monkeypatch.setattr(
        execution_module,
        "build_research_graph_for_client",
        build_graph,
    )

    workflow = execution_module.create_default_workflow(
        "ollama",
        local_scout=local_scout,
    )

    create_client.assert_called_once_with("ollama")
    build_graph.assert_called_once_with(
        llm_client,
        local_scout=local_scout,
        mcp_scout=None,
        checkpointer=None,
    )
    assert llm_client.closed is False

    await workflow.close()

    assert llm_client.closed is True
