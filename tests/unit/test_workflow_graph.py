from app.workflow.graph import research_graph


def test_research_graph_routes_simple_query_to_direct_answer() -> None:
    result = research_graph.invoke(
        {
            "query": "Hello",
            "status": "pending",
        }
    )

    assert result["query"] == "Hello"
    assert result["route"] == "direct"
    assert result["status"] == "direct_answer_ready"


def test_research_graph_routes_complex_query_to_deep_research() -> None:
    result = research_graph.invoke(
        {
            "query": "Compare Redis and PostgreSQL",
            "status": "pending",
        }
    )

    assert result["query"] == "Compare Redis and PostgreSQL"
    assert result["route"] == "deep_research"
    assert result["status"] == "deep_research_ready"