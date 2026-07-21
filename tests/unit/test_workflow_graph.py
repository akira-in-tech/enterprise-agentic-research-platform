from app.workflow.graph import research_graph


def test_research_graph_initializes_state() -> None:
    result = research_graph.invoke(
        {
            "query": "Compare Redis and PostgreSQL",
            "status": "pending",
        }
    )

    assert result["query"] == "Compare Redis and PostgreSQL"
    assert result["status"] == "initialized"