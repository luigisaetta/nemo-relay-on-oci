"""Business-path and API acceptance tests for specification 002."""

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import nemo_relay
import pytest
from fastapi.testclient import TestClient
from langchain_core.exceptions import OutputParserException
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.runnables import RunnableLambda
from langchain_core.output_parsers import PydanticOutputParser
from nemo_relay.integrations.langgraph import NemoRelayCallbackHandler

from demos.order_fulfillment.api import create_app
from demos.order_fulfillment.config import AGENT_DIR, Settings
from demos.order_fulfillment.graph import build_graph
from demos.order_fulfillment.inventory import Inventory
from demos.order_fulfillment.models import ExtractedOrder, OrderItem, Product
from demos.order_fulfillment.nodes import RegisterOrderNode


def sample_settings() -> Settings:
    """Return non-secret configuration that never creates an OCI client."""
    return Settings(region="us-chicago-1", model_id="test", compartment_id="test")


def extracted(product="keyboard", quantity=2) -> dict:
    """Build a simulated structured LLM result.

    Args:
        product: Product string returned by the model.
        quantity: Requested quantity returned by the model.

    Returns:
        Structured extraction payload.
    """
    return {"items": [{"product": product, "quantity": quantity}]}


@pytest.mark.parametrize(
    "payload,status,nodes",
    [
        (
            extracted(),
            "confirmed",
            ["extract", "match", "availability", "register", "respond"],
        ),
        (extracted("unknown"), "no_match", ["extract", "match", "respond"]),
        (
            extracted("monitor"),
            "out_of_stock",
            ["extract", "match", "availability", "respond"],
        ),
        (
            extracted(quantity=11),
            "insufficient_stock",
            ["extract", "match", "availability", "respond"],
        ),
        ({"items": []}, "invalid_request", ["extract", "respond"]),
        (
            {"items": [*extracted()["items"], *extracted("mouse")["items"]]},
            "invalid_request",
            ["extract", "respond"],
        ),
        (extracted(quantity=0), "invalid_request", ["extract", "respond"]),
        (extracted(quantity=-1), "invalid_request", ["extract", "respond"]),
        (extracted(quantity=1.5), "invalid_request", ["extract", "respond"]),
        (extracted(quantity=True), "invalid_request", ["extract", "respond"]),
        (
            {"items": [{"product": "keyboard"}]},
            "invalid_request",
            ["extract", "respond"],
        ),
        (None, "invalid_request", ["extract", "respond"]),
    ],
)
def test_graph_paths(payload, status, nodes):
    """Verify node order and ensure rejection paths never register an order.

    Args:
        payload: Simulated LLM response.
        status: Expected business outcome.
        nodes: Expected executed node sequence.
    """
    inventory = Inventory.load(AGENT_DIR / "catalog.json")
    graph = build_graph(RunnableLambda(lambda _: payload), inventory)
    updates = list(
        graph.stream({"request": "Please order my items"}, stream_mode="updates")
    )
    assert [next(iter(update)) for update in updates] == nodes
    response = updates[-1]["respond"]["response"]
    assert response.status == status
    assert len(inventory.orders) == (1 if status == "confirmed" else 0)
    if status == "confirmed":
        assert response.product == "Keyboard"
        assert response.quantity == 2
        assert response.order_id == inventory.orders[0]["order_id"]
        assert response.available == 8
        assert response.request == "Please order my items"


def test_alias_exact_stock_and_exhaustion():
    """Accept normalized aliases, fulfill exact stock, then reject later orders."""
    inventory = Inventory.load(AGENT_DIR / "catalog.json")
    graph = build_graph(
        RunnableLambda(lambda _: extracted("  TASTIERA  ", 10)), inventory
    )
    assert graph.invoke({"request": "10 tastiere"})["response"].status == "confirmed"
    assert graph.invoke({"request": "10 tastiere"})["response"].status == "out_of_stock"
    assert len(inventory.orders) == 1


def test_ambiguous_alias():
    """Reject an alias that identifies more than one product."""
    inventory = Inventory(
        {
            "a": Product(product_id="a", name="A", aliases=["item"], available=2),
            "b": Product(product_id="b", name="B", aliases=["item"], available=2),
        }
    )
    result = build_graph(RunnableLambda(lambda _: extracted("item")), inventory).invoke(
        {"request": "2 items"}
    )
    assert result["response"].status == "no_match"
    assert not inventory.orders


def test_model_parser_and_prompt():
    """Exercise actual LangChain messages and structured parsing offline."""
    model = FakeListChatModel(
        responses=['{"items":[{"product":"mouse","quantity":1}]}']
    )
    extractor = model | PydanticOutputParser(pydantic_object=ExtractedOrder)
    result = build_graph(extractor, Inventory.load(AGENT_DIR / "catalog.json")).invoke(
        {"request": "One mouse please"}
    )
    assert result["response"].status == "confirmed"


def test_parser_failure():
    """Malformed LLM output requests clarification without registration."""
    extractor = RunnableLambda(Mock(side_effect=OutputParserException("bad output")))
    inventory = Inventory.load(AGENT_DIR / "catalog.json")
    result = build_graph(extractor, inventory).invoke({"request": "order something"})
    assert result["response"].status == "invalid_request"
    assert not inventory.orders


def test_stock_race_and_concurrency():
    """Recheck stock in the tool and prevent overselling across threads."""
    inventory = Inventory.load(AGENT_DIR / "catalog.json")
    stale_product = inventory.products["keyboard"]
    inventory.register("keyboard", 9)
    result = RegisterOrderNode(inventory.registration_tool())(
        {
            "product": stale_product,
            "item": OrderItem(product="keyboard", quantity=2),
        },
        {},
    )
    assert result["status"] == "insufficient_stock"
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(
            executor.map(lambda _: inventory.register("keyboard", 1), range(8))
        )
    assert sum(result["status"] == "confirmed" for result in results) == 1
    assert inventory.available("keyboard") == 0


def test_api_success_and_validation():
    """Validate HTTP inputs and confirm the full response contract."""
    app = create_app(sample_settings(), RunnableLambda(lambda _: extracted()))
    with TestClient(app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        for body in [{}, {"request": " "}, {"request": "x" * 2001}, {"request": 5}]:
            assert client.post("/orders", json=body).status_code == 422
        response = client.post("/orders", json={"request": "2 keyboards"})
        assert response.status_code == 200
        assert response.json()["status"] == "confirmed"
        assert response.json()["request"] == "2 keyboards"
        assert response.json()["order_id"]


def test_api_model_failure():
    """Return a sanitized upstream error and never register on timeout."""
    inventory = Inventory.load(AGENT_DIR / "catalog.json")
    app = create_app(
        sample_settings(),
        RunnableLambda(Mock(side_effect=TimeoutError("secret"))),
        inventory,
    )
    with TestClient(app) as client:
        response = client.post("/orders", json={"request": "2 keyboards"})
        assert response.status_code == 502
        assert "secret" not in response.text
    assert not inventory.orders


def test_relay_scopes_include_nodes_model_and_tool():
    """Observe real Relay events for graph nodes and explicit model/tool scopes."""
    names = []
    nemo_relay.subscribers.register(
        "test-order-scopes", lambda event: names.append(event.name)
    )
    try:
        graph = build_graph(
            RunnableLambda(lambda _: extracted()),
            Inventory.load(AGENT_DIR / "catalog.json"),
        )
        graph.invoke(
            {"request": "2 keyboards"},
            config={"callbacks": [NemoRelayCallbackHandler()]},
        )
        nemo_relay.subscribers.flush()
        assert {
            "extract",
            "match",
            "availability",
            "register",
            "respond",
            "extract_order_llm",
            "register_order",
        }.issubset(set(names))
    finally:
        nemo_relay.subscribers.deregister("test-order-scopes")
