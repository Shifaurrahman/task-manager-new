from langgraph.graph import END, StateGraph

from app.graph.nodes import extract_concepts_node, update_meta_node, write_concepts_node
from app.graph.state import PipelineState


def build_graph():
    graph = StateGraph(PipelineState)

    graph.add_node("extract_concepts", extract_concepts_node)
    graph.add_node("write_concepts", write_concepts_node)
    graph.add_node("update_meta", update_meta_node)

    graph.set_entry_point("extract_concepts")
    graph.add_edge("extract_concepts", "write_concepts")
    graph.add_edge("write_concepts", "update_meta")
    graph.add_edge("update_meta", END)

    return graph.compile()


pipeline = build_graph()