"""Native Relay exporter lifecycle for the demo process."""

from contextlib import asynccontextmanager
from urllib.parse import urlparse

from nemo_relay import plugin
from nemo_relay.observability import (
    ComponentSpec,
    ObservabilityConfig,
    OpenTelemetryEndpointConfig,
    OpenTelemetrySectionConfig,
)

from demos.order_fulfillment.config import Settings


@asynccontextmanager
async def relay_lifespan(settings: Settings):
    """Activate Relay and drain exports on application shutdown.

    Args:
        settings: Collector endpoint and service identity.

    Yields:
        The active Relay plugin host.

    Raises:
        ValueError: The configured collector URL is not HTTP or HTTPS.
    """
    endpoints = []
    if settings.traces_endpoint:
        parsed = urlparse(settings.traces_endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Collector endpoint must be an HTTP(S) URL")
        endpoints.append(
            OpenTelemetryEndpointConfig(
                type="full",
                endpoint=settings.traces_endpoint,
                service_name=settings.service_name,
                transport="http_binary",
            )
        )
    configuration = plugin.PluginConfig(
        components=[
            ComponentSpec(
                config=ObservabilityConfig(
                    opentelemetry=OpenTelemetrySectionConfig(
                        enabled=bool(endpoints),
                        endpoints=endpoints,
                    )
                ),
            )
        ]
    )
    async with plugin.activate(configuration) as activation:
        yield activation
