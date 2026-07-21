from langgraph.graph import END, START, StateGraph

from app.workflow.state import ResearchState


def initialize_node(state: ResearchState) -> dict[str, str]:
    """Initialize the workflow status for a new research request."""

    return {
        "status": "initialized",
    }


def build_research_graph():
    """Build and compile the initial research workflow graph."""

    graph_builder = StateGraph(ResearchState)

    graph_builder.add_node("initialize", initialize_node)

    graph_builder.add_edge(START, "initialize")
    graph_builder.add_edge("initialize", END)

    return graph_builder.compile()


research_graph = build_research_graph()