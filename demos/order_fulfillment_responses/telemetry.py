"""
Author: L. Saetta (Luigi Saetta)
Last modified: 2026-09-26
License: MIT

Description:
    Configures Relay telemetry and guardrail lifecycle for the Responses demo.
"""

from base64 import b64encode
from collections.abc import Iterator
from contextlib import asynccontextmanager, contextmanager
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import nemo_relay
from nemo_relay import pii_redaction, plugin
from nemo_relay.model_pricing import ComponentSpec as PricingComponentSpec
from nemo_relay.model_pricing import FileSource, PricingConfig, validate_config
from nemo_relay.observability import (
    ComponentSpec,
    ObservabilityConfig,
    OpenTelemetryEndpointConfig,
    OpenTelemetrySectionConfig,
)

from demos.order_fulfillment_responses.config import Settings, create_guardrails_client
from demos.order_fulfillment_responses.prompt_guard import build_prompt_guard


def trace_endpoints(settings: Settings) -> list[OpenTelemetryEndpointConfig]:
    """Build the optional Langfuse or generic OTLP endpoint.

    Args:
        settings: Agent-local telemetry settings.

    Returns:
        One endpoint or an empty list.

    Raises:
        ValueError: Telemetry settings are invalid or conflicting.
    """
    base_url = settings.langfuse_base_url.strip().rstrip("/")
    public_key = settings.langfuse_public_key.get_secret_value().strip()
    secret_key = settings.langfuse_secret_key.get_secret_value().strip()
    endpoint = settings.traces_endpoint.strip()
    headers = {}
    if any((base_url, public_key, secret_key)):
        if not all((base_url, public_key, secret_key)):
            raise ValueError(
                "Set LANGFUSE_BASE_URL, LANGFUSE_PUBLIC_KEY, and LANGFUSE_SECRET_KEY together"
            )
        if endpoint:
            raise ValueError(
                "Leave OTEL_EXPORTER_OTLP_TRACES_ENDPOINT empty for Langfuse"
            )
        endpoint = base_url + "/api/public/otel/v1/traces"
        authorization = b64encode(f"{public_key}:{secret_key}".encode()).decode("ascii")
        headers = {
            "Authorization": f"Basic {authorization}",
            "Accept": "application/json",
        }
        if settings.langfuse_ingestion_version:
            headers["x-langfuse-ingestion-version"] = (
                settings.langfuse_ingestion_version
            )
    if not endpoint:
        return []
    parsed = urlparse(endpoint)
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or any((parsed.query, parsed.fragment))
    ):
        raise ValueError(
            "Trace URL must be HTTP(S), without credentials, query, or fragment"
        )
    return [
        OpenTelemetryEndpointConfig(
            type="openinference",
            endpoint=endpoint,
            service_name=settings.service_name,
            transport="http_binary",
            headers=headers,
            attribute_mappings=[
                {"key": "llm.cost.total", "alias": "gen_ai.usage.cost"}
            ],
        )
    ]


def pricing_component(settings: Settings) -> PricingComponentSpec | None:
    """Build optional validated Relay pricing configuration.

    Args:
        settings: Settings containing an optional catalog path.

    Returns:
        Pricing component or none.

    Raises:
        ValueError: The catalog is missing, unreadable, or invalid.
    """
    if not settings.model_pricing_file.strip():
        return None
    path = Path(settings.model_pricing_file).expanduser()
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ValueError("MODEL_PRICING_FILE does not exist") from error
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("MODEL_PRICING_FILE must be readable valid JSON") from error
    config = PricingConfig(sources=[FileSource(path=str(path))])
    if any(item["level"] == "error" for item in validate_config(config)["diagnostics"]):
        raise ValueError("MODEL_PRICING_FILE is not a valid Relay pricing catalog")
    return PricingComponentSpec(config=config)


def pii_component(settings: Settings) -> pii_redaction.ComponentSpec | None:
    """Build optional phone-number redaction policy.

    Args:
        settings: Redaction configuration.

    Returns:
        Relay PII component or none.

    Raises:
        ValueError: Relay rejects the configured policy.
    """
    if settings.pii_redaction == "off":
        return None
    config = pii_redaction.PiiRedactionConfig(
        builtin=pii_redaction.BuiltinConfig(
            action=settings.pii_redaction, detector="phone"
        )
    )
    if any(
        item["level"] == "error"
        for item in pii_redaction.validate_config(config)["diagnostics"]
    ):
        raise ValueError("PII_REDACTION is not a valid Relay redaction policy")
    return pii_redaction.ComponentSpec(config=config)


@asynccontextmanager
async def relay_lifespan(settings: Settings):
    """Activate Relay components and register the prompt guard.

    Args:
        settings: Telemetry and guardrail configuration.

    Yields:
        Active Relay plugin host.
    """
    endpoints = trace_endpoints(settings)
    components: list[object] = [
        ComponentSpec(
            config=ObservabilityConfig(
                enable_full_payloads=True,
                opentelemetry=OpenTelemetrySectionConfig(
                    enabled=bool(endpoints), endpoints=endpoints
                ),
            )
        )
    ]
    if pricing := pricing_component(settings):
        components.append(pricing)
    if pii := pii_component(settings):
        components.append(pii)
    async with plugin.activate(
        plugin.PluginConfig(components=components)
    ) as activation:
        registered = False
        if settings.prompt_guard != "off":
            client = (
                create_guardrails_client(settings)
                if settings.prompt_guard in {"oci", "combined"}
                else None
            )
            nemo_relay.guardrails.register_llm_conditional_execution(
                "prompt_guard", 100, build_prompt_guard(settings, client)
            )
            registered = True
        try:
            yield activation
        finally:
            if registered:
                nemo_relay.guardrails.deregister_llm_conditional_execution(
                    "prompt_guard"
                )


@contextmanager
def trace_scope(
    name: str, scope_type: nemo_relay.ScopeType, trace_input: dict[str, Any]
) -> Iterator[dict[str, Any]]:
    """Record a semantic Relay scope with its input and output.

    Args:
        name: Stable scope name.
        scope_type: Relay semantic scope type.
        trace_input: JSON-compatible input payload.

    Yields:
        Mutable mapping whose output key is exported on scope close.
    """
    handle = nemo_relay.scope.push(name, scope_type, input=trace_input)
    data: dict[str, Any] = {}
    try:
        yield data
    except BaseException:
        nemo_relay.scope.pop(
            handle, output=data.get("output"), metadata={"otel.status_code": "ERROR"}
        )
        raise
    nemo_relay.scope.pop(
        handle, output=data.get("output"), metadata={"otel.status_code": "OK"}
    )
