"""
Author: L. Saetta (Luigi Saetta)
Last modified: 2026-09-26
License: MIT

Description:
    Tests phone-number PII redaction in Relay telemetry events.
"""

import json
from uuid import uuid4
from unittest.mock import patch

import nemo_relay
import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableLambda
from pydantic import ValidationError

from demos.order_fulfillment.api import create_app
from demos.order_fulfillment.config import AGENT_DIR, Settings, load_settings
from demos.order_fulfillment.inventory import Inventory
from demos.order_fulfillment.models import ExtractedOrder
from demos.order_fulfillment.telemetry import pii_component, trace_scope

PHONE_NUMBER = "+39 333 123 4567"
ORDER_REQUEST = f"I would like 2 keyboards, call me at {PHONE_NUMBER}"


def raw_extraction(tokens: dict[str, int] | None = None) -> dict[str, object]:
    """Build an include-raw extraction result for a keyboard order.

    Args:
        tokens: Optional OCI-style token-usage metadata.

    Returns:
        Mapping matching LangChain's `include_raw=True` result shape.
    """
    return {
        "raw": AIMessage(content="", usage_metadata=tokens),
        "parsed": ExtractedOrder(items=[{"product": "keyboard", "quantity": 2}]),
        "parsing_error": None,
    }


def event_json(value: object) -> object:
    """Convert Relay event objects to JSON-compatible values.

    Args:
        value: Value encountered by the JSON encoder.

    Returns:
        JSON-compatible representation of the Relay event.

    Raises:
        TypeError: The value is not a serializable Relay event object.
    """
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return to_dict()
    raise TypeError(f"Unsupported event value: {type(value).__name__}")


def pricing_catalog() -> dict[str, object]:
    """Build a deterministic Relay pricing catalog for PII regression tests.

    Returns:
        Valid local Relay pricing-catalog JSON data.
    """
    entry: dict[str, object] = {
        "provider": "oci",
        "model_id": "test-model",
        "currency": "USD",
        "unit": "per_token",
        "aliases": [],
    }
    entry["pricing_as_of"] = "2026-09-26"
    entry["pricing_source"] = "offline-pii-test"
    entry["rates"] = {"input_per_million": 1.0, "output_per_million": 2.0}
    entry["prompt_cache"] = {"read_accounting": "included_in_prompt_tokens"}
    return {"version": 1, "entries": [entry]}


def run_order(
    mode: str,
    request: str = ORDER_REQUEST,
    model_pricing_file: str = "",
) -> tuple[object, list[HumanMessage], list[object]]:
    """Run one offline order and capture already-sanitized Relay events.

    Args:
        mode: PII-redaction mode accepted by the demo settings.
        request: Natural-language order request sent to the API.
        model_pricing_file: Optional local pricing catalog path.

    Returns:
        HTTP response, extractor human messages, and emitted Relay events.
    """
    received_messages: list[HumanMessage] = []
    events: list[object] = []

    def extract(messages: list[object]) -> dict[str, object]:
        """Record the model input and return a deterministic extraction."""
        received_messages.extend(
            message for message in messages if isinstance(message, HumanMessage)
        )
        return raw_extraction(
            {"input_tokens": 1000, "output_tokens": 500, "total_tokens": 1500}
        )

    settings = Settings(
        region="us-chicago-1",
        model_id="test-model",
        compartment_id="test",
        pii_redaction=mode,
        model_pricing_file=model_pricing_file,
    )
    app = create_app(
        settings,
        RunnableLambda(extract),
        Inventory.load(AGENT_DIR / "catalog.json"),
    )
    subscriber = f"test-pii-redaction-{mode}"
    with TestClient(app) as client:
        nemo_relay.subscribers.register(subscriber, events.append)
        try:
            response = client.post("/orders", json={"request": request})
            nemo_relay.subscribers.flush()
        finally:
            nemo_relay.subscribers.deregister(subscriber)
    return response, received_messages, events


def serialized_events(events: list[object]) -> str:
    """Serialize captured Relay events as an exporter would receive them.

    Args:
        events: Events delivered to the Relay subscriber.

    Returns:
        Stable JSON representation of the event payloads.
    """
    return json.dumps(events, default=event_json, sort_keys=True)


def test_mask_sanitizes_events_but_not_model_or_http_response():
    """Keep the original phone number outside telemetry while masking events."""
    response, messages, events = run_order("mask")
    serialized = serialized_events(events)
    assert response.status_code == 200
    assert response.json()["status"] == "confirmed"
    assert response.json()["request"] == ORDER_REQUEST
    assert messages[0].content == ORDER_REQUEST
    assert PHONE_NUMBER not in serialized
    assert "************4567" in serialized
    assert "keyboard" in serialized
    assert '"quantity": 2' in serialized
    assert '"product_id": "keyboard"' in serialized
    assert '"order_id":' in serialized


def test_mask_preserves_the_confirmed_order_id_across_scope_events():
    """Keep one order ID while masking the phone in all exported scope data."""
    response, _, events = run_order("mask")
    order_id = response.json()["order_id"]
    ends = {
        event.name: event
        for event in events
        if event.scope_category == "end"
        and event.name
        in {"order_fulfillment", "register_order", "build_order_response"}
    }
    assert ends["order_fulfillment"].data["response"]["order_id"] == order_id
    assert ends["register_order"].data["order_id"] == order_id
    assert ends["build_order_response"].data["response"]["order_id"] == order_id
    serialized = serialized_events(events)
    assert PHONE_NUMBER not in serialized
    assert "************4567" in serialized


def test_redact_replaces_phone_number_in_events():
    """Replace detected phone numbers rather than preserving suffix digits."""
    _, _, events = run_order("redact")
    serialized = serialized_events(events)
    assert PHONE_NUMBER not in serialized
    assert "[REDACTED]" in serialized


def test_off_preserves_current_unredacted_event_behavior():
    """Retain complete phone numbers when the redaction component is disabled."""
    _, _, events = run_order("off")
    assert PHONE_NUMBER in serialized_events(events)


def test_mask_retains_token_usage_and_pricing(tmp_path):
    """Preserve token counts and estimated cost when redaction is enabled."""
    catalog_path = tmp_path / "pricing.json"
    catalog_path.write_text(json.dumps(pricing_catalog()), encoding="utf-8")
    _, _, events = run_order("mask", model_pricing_file=str(catalog_path))
    end_events = [
        event
        for event in events
        if event.name == "extract_order" and event.scope_category == "end"
    ]
    assert len(end_events) == 1
    usage = end_events[0].category_profile["annotated_response"]["usage"]
    assert usage["prompt_tokens"] == 1000
    assert usage["completion_tokens"] == 500
    assert usage["total_tokens"] == 1500
    assert usage["cost"]["total"] == pytest.approx(0.002)


@pytest.mark.parametrize(
    "phone_number",
    ["+39 333 123 4567", "+393331234567", "(333) 123 4567", "333 123 4567"],
)
def test_supported_phone_formats_are_masked(phone_number):
    """Mask every documented phone format with the explicit pattern."""
    request = f"I would like 2 keyboards, call me at {phone_number}"
    response, messages, events = run_order("mask", request)
    serialized = serialized_events(events)
    assert response.status_code == 200
    assert messages[0].content == request
    assert phone_number not in serialized


def test_dashed_phone_number_is_intentionally_not_masked():
    """Document the UUID-safety tradeoff for dashed-only phone numbers."""
    phone_number = "333-123-4567"
    _, messages, events = run_order(
        "mask", f"I would like 2 keyboards, call me at {phone_number}"
    )
    assert messages[0].content.endswith(phone_number)
    assert phone_number in serialized_events(events)


def test_mask_preserves_uuid_order_ids_in_real_relay_events():
    """Keep UUIDs intact while sanitizing Relay subscriber events."""
    identifiers = [
        "b05e461a-2c81-4929-815d-959e89093bbf",
        "b4a4b471-8a57-49a1-8016-218a23cdc7e8",
        *(str(uuid4()) for _ in range(1000)),
    ]
    events: list[object] = []
    settings = Settings(
        region="us-chicago-1",
        model_id="test-model",
        compartment_id="test",
        pii_redaction="mask",
    )
    app = create_app(
        settings,
        RunnableLambda(lambda _: raw_extraction()),
        Inventory.load(AGENT_DIR / "catalog.json"),
    )
    with TestClient(app):
        nemo_relay.subscribers.register("test-pii-uuid-safety", events.append)
        try:
            for identifier in identifiers:
                notice = f"Order {identifier} registered, available 8"
                with trace_scope(
                    "uuid_safety", nemo_relay.ScopeType.Agent, {"notice": notice}
                ) as trace:
                    trace["output"] = {"notice": notice}
            nemo_relay.subscribers.flush()
        finally:
            nemo_relay.subscribers.deregister("test-pii-uuid-safety")
    serialized = serialized_events(events)
    for identifier in identifiers:
        assert identifier in serialized


def test_invalid_pii_redaction_setting_fails_validation(tmp_path, monkeypatch):
    """Reject unsupported environment values before application startup."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OCI_REGION=us-chicago-1\nMODEL_ID=test\nOCI_COMPARTMENT_ID=test\n"
        "PII_REDACTION=invalid\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("PII_REDACTION", raising=False)
    with pytest.raises(ValidationError, match="pii_redaction"):
        load_settings(env_file)


@pytest.mark.parametrize("mode", ["mask", "redact"])
def test_pii_component_uses_requested_action(mode):
    """Configure the Relay component with the requested redaction action."""
    component = pii_component(
        Settings(
            region="us-chicago-1",
            model_id="test-model",
            compartment_id="test",
            pii_redaction=mode,
        )
    )
    assert component is not None
    assert component.config.builtin.action == mode
    assert component.config.builtin.detector is None
    assert component.config.builtin.pattern
    assert component.config.builtin.unmasked_suffix == (4 if mode == "mask" else None)


def test_off_does_not_create_pii_component():
    """Avoid installing a redaction component when it is explicitly disabled."""
    settings = Settings(
        region="us-chicago-1",
        model_id="test-model",
        compartment_id="test",
        pii_redaction="off",
    )
    assert pii_component(settings) is None


def test_invalid_relay_pii_policy_fails_component_creation():
    """Reject an error diagnostic returned by Relay policy validation."""
    settings = Settings(
        region="us-chicago-1",
        model_id="test-model",
        compartment_id="test",
    )
    with patch(
        "demos.order_fulfillment.telemetry.pii_redaction.validate_config",
        return_value={"diagnostics": [{"level": "error"}]},
    ):
        with pytest.raises(ValueError, match="PII_REDACTION"):
            pii_component(settings)
