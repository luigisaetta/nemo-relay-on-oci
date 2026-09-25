"""Verify prompt wiring without claiming to test live LLM reasoning."""

from unittest.mock import Mock

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_core.runnables import RunnableLambda

from demos.order_fulfillment.graph import build_graph
from demos.order_fulfillment.inventory import Inventory
from demos.order_fulfillment.models import Product
from demos.order_fulfillment.nodes import EXTRACTION_PROMPT


def test_extraction_prompt_has_no_catalog_and_preserves_features():
    """Pass normalization instructions and user text without inventory data."""
    model = Mock(
        return_value={"items": [{"product": "wireless keyboard", "quantity": 2}]}
    )
    inventory = Inventory(
        {
            "keyboard": Product(product_id="keyboard", name="Keyboard", available=10),
            "private": Product(
                product_id="private", name="PrivateCatalogItem", available=37
            ),
        }
    )
    graph = build_graph(
        RunnableLambda(
            lambda messages: {
                "raw": AIMessage(content=""),
                "parsed": model(messages),
                "parsing_error": None,
            }
        ),
        inventory,
        "test",
    )
    result = graph.invoke({"request": "2 nice wireless keyboards"})
    messages = model.call_args.args[0]
    assert isinstance(messages[0], SystemMessage)
    assert messages[0].content == EXTRACTION_PROMPT
    assert isinstance(messages[1], HumanMessage)
    assert messages[1].content == "2 nice wireless keyboards"
    assert "PrivateCatalogItem" not in messages[0].content
    assert "available" not in messages[0].content.replace("available products", "")
    assert result["response"].status == "no_match"
    assert not inventory.orders
