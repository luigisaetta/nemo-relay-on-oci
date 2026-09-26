"""
Author: L. Saetta (Luigi Saetta)
Last modified: 2026-09-26
License: MIT

Description:
    Configures NeMo Relay tracing, pricing, and exporter lifecycle management.
"""

from contextlib import asynccontextmanager, contextmanager
from base64 import b64encode
from collections.abc import Iterator
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

from demos.order_fulfillment.config import Settings, create_guardrails_client
from demos.order_fulfillment.prompt_guard import build_prompt_guard


def trace_endpoints(settings: Settings) -> list[OpenTelemetryEndpointConfig]:
    """Build one authenticated Langfuse or generic OTLP destination.

    Args:
        settings: Agent-local tracing settings.

    Returns:
        One endpoint, or an empty list when export is disabled.

    Raises:
        ValueError: Settings are incomplete, conflicting, or have an invalid URL.
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
        headers["Authorization"] = f"Basic {authorization}"
        headers["Accept"] = "application/json"
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
        or parsed.username is not None
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
    """Build a validated optional Relay model-pricing component.

    Args:
        settings: Agent-local model-pricing configuration.

    Returns:
        A pricing component when a catalog path is configured, otherwise `None`.

    Raises:
        ValueError: The configured catalog cannot be read, parsed, or validated.
    """
    configured_path = settings.model_pricing_file.strip()
    if not configured_path:
        return None
    path = Path(configured_path).expanduser()
    try:
        with path.open(encoding="utf-8") as catalog_file:
            json.load(catalog_file)
    except FileNotFoundError as error:
        raise ValueError("MODEL_PRICING_FILE does not exist") from error
    except (OSError, json.JSONDecodeError) as error:
        raise ValueError("MODEL_PRICING_FILE must be readable valid JSON") from error
    config = PricingConfig(sources=[FileSource(path=str(path))])
    diagnostics = validate_config(config)["diagnostics"]
    if any(item["level"] == "error" for item in diagnostics):
        raise ValueError("MODEL_PRICING_FILE is not a valid Relay pricing catalog")
    return PricingComponentSpec(config=config)


def pii_component(settings: Settings) -> pii_redaction.ComponentSpec | None:
    """Build a validated optional Relay phone-number redaction component.

    Args:
        settings: Agent-local PII-redaction configuration.

    Returns:
        A phone-redaction component when enabled, otherwise `None`.

    Raises:
        ValueError: The configured Relay PII-redaction policy is invalid.
    """
    if settings.pii_redaction == "off":
        return None
    config = pii_redaction.PiiRedactionConfig(
        builtin=pii_redaction.BuiltinConfig(
            action=settings.pii_redaction, detector="phone"
        )
    )
    diagnostics = pii_redaction.validate_config(config)["diagnostics"]
    if any(item["level"] == "error" for item in diagnostics):
        raise ValueError("PII_REDACTION is not a valid Relay redaction policy")
    return pii_redaction.ComponentSpec(config=config)


@asynccontextmanager
async def relay_lifespan(settings: Settings):
    """Activate Relay and drain exports on application shutdown.

    Args:
        settings: Langfuse or generic OTLP destination and service identity.

    Yields:
        The active Relay plugin host.

    Raises:
        ValueError: The configured trace destination is invalid.
    """
    endpoints = trace_endpoints(settings)
    components: list[object] = [
        ComponentSpec(
            config=ObservabilityConfig(
                enable_full_payloads=True,
                opentelemetry=OpenTelemetrySectionConfig(
                    enabled=bool(endpoints),
                    endpoints=endpoints,
                ),
            ),
        )
    ]
    if pricing := pricing_component(settings):
        components.append(pricing)
    if pii := pii_component(settings):
        components.append(pii)
    configuration = plugin.PluginConfig(components=components)
    async with plugin.activate(configuration) as activation:
        guard_registered = False
        if settings.prompt_guard != "off":
            client = (
                create_guardrails_client(settings)
                if settings.prompt_guard in {"oci", "combined"}
                else None
            )
            nemo_relay.guardrails.register_llm_conditional_execution(
                "prompt_guard", 100, build_prompt_guard(settings, client)
            )
            guard_registered = True
        try:
            yield activation
        finally:
            if guard_registered:
                nemo_relay.guardrails.deregister_llm_conditional_execution(
                    "prompt_guard"
                )


@contextmanager
def trace_scope(
    name: str, scope_type: nemo_relay.ScopeType, trace_input: dict[str, Any]
) -> Iterator[dict[str, Any]]:
    """Record a Relay scope with explicit semantic input and output.

    Args:
        name: Stable, human-readable operation name.
        scope_type: Relay semantic type for the operation.
        trace_input: JSON-compatible payload sent as the operation input.

    Yields:
        A mutable mapping. Set its ``output`` key to a JSON-compatible result
        before leaving the context.

    Raises:
        BaseException: Re-raises an exception raised by the scoped operation.
    """
    handle = nemo_relay.scope.push(name, scope_type, input=trace_input)
    trace_data: dict[str, Any] = {}
    try:
        yield trace_data
    except BaseException:
        nemo_relay.scope.pop(
            handle,
            output=trace_data.get("output"),
            metadata={"otel.status_code": "ERROR"},
        )
        raise
    nemo_relay.scope.pop(
        handle,
        output=trace_data.get("output"),
        metadata={"otel.status_code": "OK"},
    )
