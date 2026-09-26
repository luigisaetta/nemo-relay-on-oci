"""
Author: L. Saetta (Luigi Saetta)
Last modified: 2026-09-26
License: MIT

Description:
    Builds the independent LangGraph workflow for Responses API fulfillment.
"""

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from demos.order_fulfillment_responses.inventory import Inventory
from demos.order_fulfillment_responses.models import OrderState
from demos.order_fulfillment_responses.nodes import (
    BuildResponseNode,
    CheckAvailabilityNode,
    ExtractRequestNode,
    MatchProductNode,
    RegisterOrderNode,
)


def route_outcome(state: OrderState) -> str:
    """Route business rejections to response generation.

    Args:
        state: Current graph state.

    Returns:
        Continue or respond edge name.
    """
    return "respond" if state.get("status") else "continue"


def build_graph(
    client: object, inventory: Inventory, model_id: str, reasoning_effort: str = ""
) -> CompiledStateGraph:
    """Compile the sequential independent order workflow.

    Args:
        client: OpenAI-compatible Responses client.
        inventory: Local independent catalog and order store.
        model_id: OCI model identifier.
        reasoning_effort: Optional model reasoning setting.

    Returns:
        Compiled graph.
    """
    graph = StateGraph(OrderState)
    graph.add_node("extract", ExtractRequestNode(client, model_id, reasoning_effort))
    graph.add_node("match", MatchProductNode(inventory))
    graph.add_node("availability", CheckAvailabilityNode(inventory))
    graph.add_node("register", RegisterOrderNode(inventory.registration_tool()))
    graph.add_node("respond", BuildResponseNode())
    graph.add_edge(START, "extract")
    for current, following in [
        ("extract", "match"),
        ("match", "availability"),
        ("availability", "register"),
    ]:
        graph.add_conditional_edges(
            current, route_outcome, {"continue": following, "respond": "respond"}
        )
    graph.add_edge("register", "respond")
    graph.add_edge("respond", END)
    return graph.compile()
