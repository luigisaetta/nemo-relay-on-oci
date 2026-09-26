"""
Author: L. Saetta (Luigi Saetta)
Last modified: 2026-09-26
License: MIT

Description:
    Tests order-fulfillment business paths and FastAPI endpoints.
"""

from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import nemo_relay
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from langchain_core.exceptions import OutputParserException
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda
from langchain_core.output_parsers import PydanticOutputParser
from oci.exceptions import ServiceError

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
    """Build a simulated raw structured-output result.

    Args:
        product: Product string returned by the model.
        quantity: Requested quantity returned by the model.

    Returns:
        Include-raw structured extraction payload.
    """
    return {
        "raw": AIMessage(content=""),
        "parsed": {"items": [{"product": product, "quantity": quantity}]},
        "parsing_error": None,
    }


def raw_result(parsed, parsing_error=None, usage_metadata=None) -> dict:
    """Build an include-raw extractor result for an offline test.

    Args:
        parsed: Structured result to expose as the parsed value.
        parsing_error: Optional conversion error returned by LangChain.
        usage_metadata: Optional OCI-style token usage metadata.

    Returns:
        Include-raw result mapping with an `AIMessage`.
    """
    return {
        "raw": AIMessage(content="", usage_metadata=usage_metadata),
        "parsed": parsed,
        "parsing_error": parsing_error,
    }


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
        (raw_result({"items": []}), "invalid_request", ["extract", "respond"]),
        (
            raw_result(
                {
                    "items": [
                        *extracted()["parsed"]["items"],
                        *extracted("mouse")["parsed"]["items"],
                    ]
                }
            ),
            "invalid_request",
            ["extract", "respond"],
        ),
        (extracted(quantity=0), "invalid_request", ["extract", "respond"]),
        (extracted(quantity=-1), "invalid_request", ["extract", "respond"]),
        (extracted(quantity=1.5), "invalid_request", ["extract", "respond"]),
        (extracted(quantity=True), "invalid_request", ["extract", "respond"]),
        (
            raw_result({"items": [{"product": "keyboard"}]}),
            "invalid_request",
            ["extract", "respond"],
        ),
        (raw_result(None), "invalid_request", ["extract", "respond"]),
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
    graph = build_graph(RunnableLambda(lambda _: payload), inventory, "test")
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
        RunnableLambda(lambda _: extracted("  TASTIERA  ", 10)), inventory, "test"
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
    result = build_graph(
        RunnableLambda(lambda _: extracted("item")), inventory, "test"
    ).invoke({"request": "2 items"})
    assert result["response"].status == "no_match"
    assert not inventory.orders


def test_model_parser_and_prompt():
    """Exercise actual LangChain messages and structured parsing offline."""
    model = FakeListChatModel(
        responses=['{"items":[{"product":"mouse","quantity":1}]}']
    )
    extractor = model | PydanticOutputParser(pydantic_object=ExtractedOrder)
    extractor = extractor | RunnableLambda(raw_result)
    result = build_graph(
        extractor, Inventory.load(AGENT_DIR / "catalog.json"), "test"
    ).invoke({"request": "One mouse please"})
    assert result["response"].status == "confirmed"


def test_parser_failure():
    """Malformed LLM output requests clarification without registration."""
    extractor = RunnableLambda(Mock(side_effect=OutputParserException("bad output")))
    inventory = Inventory.load(AGENT_DIR / "catalog.json")
    result = build_graph(extractor, inventory, "test").invoke(
        {"request": "order something"}
    )
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
        assert client.get("/ready").json() == {"status": "ready"}
        for body in [{}, {"request": " "}, {"request": "x" * 2001}, {"request": 5}]:
            assert client.post("/orders", json=body).status_code == 422
        response = client.post("/orders", json={"request": "2 keyboards"})
        assert response.status_code == 200
        assert response.json()["status"] == "confirmed"
        assert response.json()["request"] == "2 keyboards"
        assert response.json()["order_id"]


def test_readiness_before_startup():
    """Return a retryable readiness failure before the graph is initialized."""
    app = create_app(sample_settings(), RunnableLambda(lambda _: extracted()))
    ready_endpoint = next(
        route.endpoint
        for route in app.routes
        if getattr(route, "path", None) == "/ready"
    )
    with pytest.raises(HTTPException) as failure:
        ready_endpoint()
    assert failure.value.status_code == 503


def test_api_model_failure(caplog):
    """Return a sanitized upstream error and never register on timeout.

    Args:
        caplog: Captured server log records.
    """
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
        assert "TimeoutError" in caplog.text
        assert "secret" not in caplog.text
    assert not inventory.orders


def test_api_oci_rejection(caplog):
    """Expose an actionable OCI status without logging raw provider content.

    Args:
        caplog: Captured server log records.
    """
    inventory = Inventory.load(AGENT_DIR / "catalog.json")
    error = ServiceError(400, "InvalidParameter", {}, "private provider message")
    app = create_app(
        sample_settings(), RunnableLambda(Mock(side_effect=error)), inventory
    )
    with TestClient(app) as client:
        response = client.post("/orders", json={"request": "2 keyboards"})
    assert response.status_code == 502
    assert "upstream status 400" in response.json()["detail"]
    assert "reasoning effort" in response.json()["detail"]
    assert "status=400 code=InvalidParameter" in caplog.text
    assert "private provider message" not in caplog.text + response.text
    assert not inventory.orders


def test_relay_scopes_use_readable_domain_names():
    """Observe named Relay events without LangGraph framework internals."""
    names = []
    nemo_relay.subscribers.register(
        "test-order-scopes", lambda event: names.append(event.name)
    )
    try:
        graph = build_graph(
            RunnableLambda(lambda _: extracted()),
            Inventory.load(AGENT_DIR / "catalog.json"),
            "test",
        )
        graph.invoke({"request": "2 keyboards"})
        nemo_relay.subscribers.flush()
        assert {
            "extract_order",
            "match_catalog_product",
            "check_inventory_availability",
            "register_order",
            "build_order_response",
        }.issubset(set(names))
        assert not {"RunnableSequence", "PydanticToolsParser", "route_outcome"} & set(
            names
        )
    finally:
        nemo_relay.subscribers.deregister("test-order-scopes")


def test_api_trace_has_one_root_with_full_payloads():
    """Record the complete order hierarchy and its semantic payloads."""
    events = []
    nemo_relay.subscribers.register("test-order-trace", events.append)
    try:
        app = create_app(
            sample_settings(),
            RunnableLambda(lambda _: extracted()),
            Inventory.load(AGENT_DIR / "catalog.json"),
        )
        with TestClient(app) as client:
            assert (
                client.post("/orders", json={"request": "2 keyboards"}).status_code
                == 200
            )
        nemo_relay.subscribers.flush()
    finally:
        nemo_relay.subscribers.deregister("test-order-trace")

    starts = {
        event.name: event
        for event in events
        if event.scope_category == "start"
        and event.name
        in {
            "order_fulfillment",
            "extract_order",
            "match_catalog_product",
            "check_inventory_availability",
            "register_order",
            "build_order_response",
        }
    }
    ends = {
        event.name: event
        for event in events
        if event.scope_category == "end"
        and event.name
        in {
            "order_fulfillment",
            "extract_order",
            "match_catalog_product",
            "check_inventory_availability",
            "register_order",
            "build_order_response",
        }
    }
    assert starts["order_fulfillment"].data == {"request": "2 keyboards"}
    assert ends["order_fulfillment"].data["status"] == "confirmed"
    assert "Extract order items" in str(starts["extract_order"].data)
    assert "2 keyboards" in str(starts["extract_order"].data)
    assert ends["extract_order"].data["choices"][0]["message"]["content"] == (
        '{"items": [{"product": "keyboard", "quantity": 2}]}'
    )
    assert starts["register_order"].data == {
        "arguments": {"product_id": "keyboard", "quantity": 2}
    }
    assert ends["register_order"].data["status"] == "confirmed"
    assert starts["match_catalog_product"].data == {"requested_product": "keyboard"}
    assert ends["match_catalog_product"].data["product"]["product_id"] == "keyboard"
    assert starts["check_inventory_availability"].data == {
        "product_id": "keyboard",
        "requested_quantity": 2,
    }
    assert ends["check_inventory_availability"].data == {"available": 10}
    assert ends["build_order_response"].data["status"] == "confirmed"

    parent_by_scope = {
        event.uuid: event.parent_uuid
        for event in events
        if event.scope_category == "start"
    }
    root_uuid = starts["order_fulfillment"].uuid
    for child_name in (
        "extract_order",
        "match_catalog_product",
        "check_inventory_availability",
        "register_order",
        "build_order_response",
    ):
        parent_uuid = starts[child_name].parent_uuid
        while parent_uuid != root_uuid:
            parent_uuid = parent_by_scope[parent_uuid]
