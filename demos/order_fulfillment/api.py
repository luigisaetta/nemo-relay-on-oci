"""
Author: L. Saetta (Luigi Saetta)
Last modified: 2026-09-26
License: MIT

Description:
    Creates the FastAPI application for the order-fulfillment workflow.
"""

from contextlib import asynccontextmanager
import logging
import re
import warnings

from fastapi import FastAPI, HTTPException
from langchain_core.runnables import Runnable
import nemo_relay
from oci.exceptions import ConnectTimeout, RequestException as OCIRequestException
from oci.exceptions import ServiceError
from requests.exceptions import RequestException

from demos.order_fulfillment.config import (
    AGENT_DIR,
    Settings,
    create_extractor,
    load_settings,
)
from demos.order_fulfillment.graph import build_graph
from demos.order_fulfillment.inventory import Inventory
from demos.order_fulfillment.models import OrderRequest, OrderResponse
from demos.order_fulfillment.telemetry import relay_lifespan, trace_scope

LOGGER = logging.getLogger(__name__)
OCI_TRANSPORT_EXCEPTIONS = (
    RequestException,
    OCIRequestException,
    ConnectTimeout,
    TimeoutError,
)


def configure_warning_filters() -> None:
    """Suppress only the known OCI tool-call-only empty-text warning.

    The filter applies to this server process. Install it once at startup,
    rather than changing shared warning filters inside concurrent requests.
    """
    message = (
        "GenericProvider could not extract text and returned an empty "
        "string. Ensure the selected provider matches the response "
        "payload format, otherwise content extraction will return an "
        "empty string."
    )
    warnings.filterwarnings(
        "ignore",
        message=r"\A" + re.escape(message) + r"\Z",
        category=UserWarning,
        # The library uses stacklevel=2, attributing it to this caller module.
        module=r"\Alangchain_oci\.chat_models\.oci_generative_ai\Z",
    )


def create_app(
    settings: Settings | None = None,
    extractor: Runnable | None = None,
    inventory: Inventory | None = None,
) -> FastAPI:
    """Create the API, with injectable dependencies for offline tests.

    Args:
        settings: Explicit configuration, or load the agent's .env at startup.
        extractor: Structured-output model; defaults to OCI.
        inventory: Inventory override; defaults to the agent's JSON catalog.

    Returns:
        FastAPI application ready for Uvicorn's factory mode.
    """

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        """Load resources once and close the exporter at shutdown.

        Args:
            application: API instance receiving the compiled graph.

        Yields:
            Control while the API is serving requests.
        """
        active_settings = settings or load_settings()
        if active_settings.output_method == "function_calling":
            configure_warning_filters()
        active_inventory = inventory or Inventory.load(AGENT_DIR / "catalog.json")
        active_extractor = extractor or create_extractor(active_settings)
        async with relay_lifespan(active_settings):
            application.state.graph = build_graph(
                active_extractor, active_inventory, active_settings.model_id
            )
            yield

    app = FastAPI(title="Order fulfillment agent", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict:
        """Report readiness without invoking cloud services.

        Returns:
            Local application readiness status.
        """
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> dict:
        """Report whether startup initialized the order workflow.

        Returns:
            Readiness status after the graph is available.

        Raises:
            HTTPException: The graph has not completed initialization.
        """
        if not hasattr(app.state, "graph"):
            raise HTTPException(503, "Order workflow is not ready")
        return {"status": "ready"}

    @app.post("/orders", response_model=OrderResponse)
    def place_order(body: OrderRequest) -> OrderResponse:
        """Run the graph for one natural-language order attempt.

        Args:
            body: Validated request body.

        Returns:
            Confirmation or a business rejection.

        Raises:
            HTTPException: OCI inference fails before registration.
        """
        with trace_scope(
            "order_fulfillment", nemo_relay.ScopeType.Agent, {"request": body.request}
        ) as trace:
            try:
                result = app.state.graph.invoke({"request": body.request})
            except ServiceError as error:
                LOGGER.error(
                    "OCI model request failed: status=%s code=%s",
                    error.status,
                    error.code,
                )
                raise HTTPException(
                    502,
                    f"OCI rejected the model request (upstream status {error.status}). "
                    "Check model settings, structured output, reasoning effort, and OCI access.",
                ) from error
            except OCI_TRANSPORT_EXCEPTIONS as error:
                LOGGER.error("Model transport failed: type=%s", type(error).__name__)
                raise HTTPException(
                    502, "The model service is unavailable. Please retry later."
                ) from error
            trace["output"] = result["response"].model_dump(mode="json")
            return result["response"]

    return app
