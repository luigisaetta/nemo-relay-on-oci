"""Explicit LangGraph control flow for a single order request."""

from langchain_core.runnables import Runnable
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from demos.order_fulfillment.inventory import Inventory
from demos.order_fulfillment.models import OrderState
from demos.order_fulfillment.nodes import (
    BuildResponseNode,
    CheckAvailabilityNode,
    ExtractRequestNode,
    MatchProductNode,
    RegisterOrderNode,
)


def route_outcome(state: OrderState) -> str:
    """Choose whether to continue processing or return a business outcome.

    Args:
        state: State after extraction, matching, or availability checking.

    Returns:
        Routing key for the graph's explicit conditional edges.
    """
    return "respond" if state.get("status") else "continue"


def build_graph(extractor: Runnable, inventory: Inventory) -> CompiledStateGraph:
    """Compile the sequential workflow with explicit rejection branches.

    Args:
        extractor: Structured-output OCI model or test runnable.
        inventory: Shared in-memory catalog and order store.

    Returns:
        Compiled graph with isolated state for each invocation.
    """
    graph = StateGraph(OrderState)
    graph.add_node("extract", ExtractRequestNode(extractor))
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
