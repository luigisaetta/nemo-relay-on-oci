"""
Author: L. Saetta (Luigi Saetta)
Last modified: 2026-09-26
License: MIT

Description:
    Tests Relay token-usage and model-pricing behavior without OCI calls.
"""

import asyncio
import json

import nemo_relay
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableLambda

from demos.order_fulfillment.config import AGENT_DIR, Settings
from demos.order_fulfillment.graph import build_graph
from demos.order_fulfillment.inventory import Inventory
from demos.order_fulfillment.models import ExtractedOrder
from demos.order_fulfillment.telemetry import pricing_component, relay_lifespan
from demos.order_fulfillment.api import create_app


def raw_extraction(
    *,
    tokens: dict[str, int] | None = None,
    parsed: object | None = None,
    parsing_error: object | None = None,
) -> dict[str, object]:
    """Build an include-raw structured-output result.

    Args:
        tokens: Optional OCI-style token usage.
        parsed: Parsed result, defaulting to a valid keyboard order.
        parsing_error: Optional LangChain parsing error.

    Returns:
        Mapping matching LangChain's `include_raw=True` result shape.
    """
    if parsed is None:
        parsed = ExtractedOrder(items=[{"product": "keyboard", "quantity": 2}])
    return {
        "raw": AIMessage(content="", usage_metadata=tokens),
        "parsed": parsed,
        "parsing_error": parsing_error,
    }


def token_usage() -> dict[str, int]:
    """Return deterministic token counts for usage and cost assertions.

    Returns:
        OCI-style token counts.
    """
    return {"input_tokens": 1000, "output_tokens": 500, "total_tokens": 1500}


def pricing_catalog() -> dict[str, object]:
    """Return a valid test catalog with deterministic per-million-token rates.

    Returns:
        Relay pricing catalog for the `test-model` model.
    """
    return {
        "version": 1,
        "entries": [
            {
                "provider": "oci",
                "model_id": "test-model",
                "aliases": [],
                "currency": "USD",
                "unit": "per_token",
                "pricing_as_of": "2026-09-25",
                "pricing_source": "offline-test",
                "rates": {"input_per_million": 1.0, "output_per_million": 2.0},
                "prompt_cache": {"read_accounting": "included_in_prompt_tokens"},
            }
        ],
    }


def test_bundled_pricing_catalog_is_valid() -> None:
    """Keep the documented initial GPT-5.6 Sol estimate usable.

    Returns:
        None.
    """
    catalog_path = AGENT_DIR / "pricing.example.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    entry = catalog["entries"][0]
    assert entry["model_id"] == "openai.gpt-5.6-sol"
    assert entry["rates"] == {
        "input_per_million": 4.0,
        "output_per_million": 20.0,
        "cache_read_per_million": 0.4,
        "cache_write_per_million": 5.0,
    }
    assert (
        pricing_component(
            Settings(
                region="us-chicago-1",
                model_id="openai.gpt-5.6-sol",
                compartment_id="test",
                model_pricing_file=str(catalog_path),
            )
        )
        is not None
    )


def extract_end_event(settings: Settings, extractor: RunnableLambda):
    """Run one offline extraction inside Relay activation and return its end event.

    Args:
        settings: Demo settings, optionally including a pricing catalog path.
        extractor: Injectable extraction runnable.

    Returns:
        The one completed manual OCI LLM event.
    """
    events = []

    async def exercise() -> None:
        """Activate Relay and drain the event queue for one graph invocation."""
        async with relay_lifespan(settings):
            nemo_relay.subscribers.register("test-llm-usage", events.append)
            try:
                graph = build_graph(
                    extractor,
                    Inventory.load(AGENT_DIR / "catalog.json"),
                    settings.model_id,
                )
                graph.invoke({"request": "2 keyboards"})
                await nemo_relay.subscribers.flush_async()
            finally:
                nemo_relay.subscribers.deregister("test-llm-usage")

    asyncio.run(exercise())
    llm_events = [
        event
        for event in events
        if event.name == "extract_order" and event.scope_category == "end"
    ]
    assert len(llm_events) == 1
    return llm_events[0]


def test_llm_usage_without_pricing():
    """Export OCI tokens without estimated cost when no catalog is configured."""
    settings = Settings(
        region="us-chicago-1",
        model_id="test-model",
        compartment_id="test",
        prompt_guard="off",
    )
    event = extract_end_event(
        settings,
        RunnableLambda(lambda _: raw_extraction(tokens=token_usage())),
    )
    usage = event.category_profile["annotated_response"]["usage"]
    assert usage == {
        "prompt_tokens": 1000,
        "completion_tokens": 500,
        "total_tokens": 1500,
    }
    assert "cost" not in usage


def test_llm_usage_with_pricing(tmp_path):
    """Estimate OCI cost from the configured Relay pricing catalog."""
    catalog_path = tmp_path / "pricing.json"
    catalog_path.write_text(json.dumps(pricing_catalog()), encoding="utf-8")
    settings = Settings(
        region="us-chicago-1",
        model_id="test-model",
        compartment_id="test",
        model_pricing_file=str(catalog_path),
        prompt_guard="off",
    )
    event = extract_end_event(
        settings,
        RunnableLambda(lambda _: raw_extraction(tokens=token_usage())),
    )
    usage = event.category_profile["annotated_response"]["usage"]
    assert usage["cost"]["total"] == pytest.approx(0.002)
    assert usage["cost"]["pricing_provider"] == "oci"


def test_missing_usage_metadata_exports_no_tokens():
    """Allow OCI responses without token metadata."""
    settings = Settings(
        region="us-chicago-1",
        model_id="test-model",
        compartment_id="test",
        prompt_guard="off",
    )
    event = extract_end_event(settings, RunnableLambda(lambda _: raw_extraction()))
    response = event.category_profile["annotated_response"]
    assert "usage" not in response


def test_parsing_error_returns_invalid_request_and_closes_span():
    """Close the LLM span when include-raw reports a conversion failure."""
    settings = Settings(
        region="us-chicago-1", model_id="test-model", compartment_id="test"
    )
    events = []
    nemo_relay.subscribers.register("test-parsing-error", events.append)
    try:
        graph = build_graph(
            RunnableLambda(
                lambda _: raw_extraction(parsed={}, parsing_error=ValueError("invalid"))
            ),
            Inventory.load(AGENT_DIR / "catalog.json"),
            settings.model_id,
        )
        result = graph.invoke({"request": "2 keyboards"})
        nemo_relay.subscribers.flush()
    finally:
        nemo_relay.subscribers.deregister("test-parsing-error")
    llm_events = [
        event
        for event in events
        if event.name == "extract_order" and event.scope_category == "end"
    ]
    assert result["response"].status == "invalid_request"
    assert len(llm_events) == 1
    assert llm_events[0].metadata["otel.status_code"] == "OK"


def test_extractor_exception_closes_llm_span_and_returns_502():
    """Preserve the API failure contract while finishing the OCI LLM span."""
    settings = Settings(
        region="us-chicago-1", model_id="test-model", compartment_id="test"
    )
    events = []
    nemo_relay.subscribers.register("test-extractor-error", events.append)
    try:
        app = create_app(
            settings,
            RunnableLambda(lambda _: (_ for _ in ()).throw(TimeoutError("private"))),
            Inventory.load(AGENT_DIR / "catalog.json"),
        )
        with TestClient(app) as client:
            response = client.post("/orders", json={"request": "2 keyboards"})
        nemo_relay.subscribers.flush()
    finally:
        nemo_relay.subscribers.deregister("test-extractor-error")
    llm_events = [
        event
        for event in events
        if event.name == "extract_order" and event.scope_category == "end"
    ]
    assert response.status_code == 502
    assert len(llm_events) == 1
    assert llm_events[0].metadata["error.type"] == "TimeoutError"


@pytest.mark.parametrize("contents", ["{", "[]"])
def test_invalid_pricing_file_fails_startup(tmp_path, contents):
    """Reject missing JSON and invalid Relay pricing catalog files.

    Args:
        tmp_path: Isolated pricing-catalog location.
        contents: Invalid catalog file contents.
    """
    path = tmp_path / "pricing.json"
    path.write_text(contents, encoding="utf-8")
    settings = Settings(
        region="us-chicago-1",
        model_id="test-model",
        compartment_id="test",
        model_pricing_file=str(path),
    )

    async def activate() -> None:
        """Attempt startup with the invalid catalog."""
        async with relay_lifespan(settings):
            pytest.fail("Invalid pricing catalog was accepted")

    with pytest.raises(ValueError, match="MODEL_PRICING_FILE"):
        asyncio.run(activate())


def test_missing_pricing_file_fails_startup(tmp_path):
    """Reject a configured catalog path that does not exist.

    Args:
        tmp_path: Isolated missing-path parent directory.
    """
    settings = Settings(
        region="us-chicago-1",
        model_id="test-model",
        compartment_id="test",
        model_pricing_file=str(tmp_path / "missing.json"),
    )

    async def activate() -> None:
        """Attempt startup with the missing catalog."""
        async with relay_lifespan(settings):
            pytest.fail("Missing pricing catalog was accepted")

    with pytest.raises(ValueError, match="MODEL_PRICING_FILE does not exist"):
        asyncio.run(activate())
