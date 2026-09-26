"""
Author: L. Saetta (Luigi Saetta)
Last modified: 2026-09-26
License: MIT

Description:
    Creates the FastAPI application for OCI Responses API order fulfillment.
"""

from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI, HTTPException
import nemo_relay
import openai

from demos.order_fulfillment_responses.config import (
    AGENT_DIR,
    Settings,
    create_responses_client,
    load_settings,
)
from demos.order_fulfillment_responses.graph import build_graph
from demos.order_fulfillment_responses.inventory import Inventory
from demos.order_fulfillment_responses.models import OrderRequest, OrderResponse
from demos.order_fulfillment_responses.telemetry import relay_lifespan, trace_scope

LOGGER = logging.getLogger(__name__)


def create_app(
    settings: Settings | None = None,
    client: object | None = None,
    inventory: Inventory | None = None,
) -> FastAPI:
    """Create the independent Responses API application.

    Args:
        settings: Explicit settings, or load the agent-local dotenv file.
        client: OpenAI-compatible client, injectable for offline tests.
        inventory: Independent catalog override.

    Returns:
        FastAPI application ready for Uvicorn factory mode.
    """

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        """Initialize graph resources and Relay lifecycle once.

        Args:
            application: API application receiving its compiled graph.

        Yields:
            Control while the server is running.
        """
        active_settings = settings or load_settings()
        active_inventory = inventory or Inventory.load(AGENT_DIR / "catalog.json")
        active_client = client or create_responses_client(active_settings)
        async with relay_lifespan(active_settings):
            application.state.graph = build_graph(
                active_client,
                active_inventory,
                active_settings.model_id,
                active_settings.reasoning_effort,
            )
            yield

    app = FastAPI(title="Order fulfillment agent (Responses API)", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict:
        """Report local liveness.

        Returns:
            Static health response.
        """
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> dict:
        """Report graph initialization status.

        Returns:
            Ready response after lifespan startup.

        Raises:
            HTTPException: Graph initialization has not completed.
        """
        if not hasattr(app.state, "graph"):
            raise HTTPException(503, "Order workflow is not ready")
        return {"status": "ready"}

    @app.post("/orders", response_model=OrderResponse)
    def place_order(body: OrderRequest) -> OrderResponse:
        """Process one natural-language order.

        Args:
            body: Validated HTTP request.

        Returns:
            Business outcome.

        Raises:
            HTTPException: OCI Responses API is unavailable or rejects the call.
        """
        with trace_scope(
            "order_fulfillment_responses",
            nemo_relay.ScopeType.Agent,
            {"request": body.request},
        ) as trace:
            try:
                result = app.state.graph.invoke({"request": body.request})
            except openai.APIStatusError as error:
                LOGGER.error(
                    "OCI Responses API status failure: status=%s", error.status_code
                )
                raise HTTPException(
                    502,
                    f"Model service rejected the request (upstream status {error.status_code}).",
                ) from error
            except (openai.APIConnectionError, openai.APITimeoutError) as error:
                LOGGER.error(
                    "OCI Responses transport failure: type=%s", type(error).__name__
                )
                raise HTTPException(502, "model service unavailable") from error
            trace["output"] = {"response": result["response"].model_dump(mode="json")}
            return result["response"]

    return app
