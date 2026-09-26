"""
Author: L. Saetta (Luigi Saetta)
Last modified: 2026-09-26
License: MIT

Description:
    Loads and validates environment settings and constructs the OCI model.
"""

import os
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
from langchain_oci import ChatOCIGenAI
from pydantic import BaseModel, Field, SecretStr

from demos.order_fulfillment.models import ExtractedOrder, Name

AGENT_DIR = Path(__file__).resolve().parent


class Settings(BaseModel):
    """Validated settings loaded without modifying the process environment."""

    region: str = Field(pattern=r"^[a-z]+(?:-[a-z0-9]+)+-\d+$")
    model_id: Name
    compartment_id: Name
    auth_type: Literal["API_KEY", "RESOURCE_PRINCIPAL"] = "API_KEY"
    config_file: str = "~/.oci/config"
    config_profile: Name = "DEFAULT"
    output_method: Literal["function_calling", "json_schema", "json_mode"] = (
        "function_calling"
    )
    reasoning_effort: Literal["", "NONE", "MINIMAL", "LOW", "MEDIUM", "HIGH"] = ""
    traces_endpoint: str = ""
    service_name: Name = "order-fulfillment"
    model_pricing_file: str = ""
    langfuse_base_url: str = ""
    langfuse_public_key: SecretStr = SecretStr("")
    langfuse_secret_key: SecretStr = SecretStr("")
    langfuse_ingestion_version: Literal["", "4"] = ""

    @property
    def endpoint(self) -> str:
        """Return the commercial-realm OCI inference endpoint."""
        return f"https://inference.generativeai.{self.region}.oci.oraclecloud.com"


def load_settings(env_file: Path = AGENT_DIR / ".env") -> Settings:
    """Load the agent file with process environment taking precedence.

    Args:
        env_file: Explicit agent-local dotenv path.

    Returns:
        Validated configuration; no environment values are logged.

    Raises:
        ValueError: Required configuration is missing or invalid.
    """
    values = {**dotenv_values(env_file), **os.environ}
    fields = {
        "region": "OCI_REGION",
        "model_id": "MODEL_ID",
        "compartment_id": "OCI_COMPARTMENT_ID",
        "auth_type": "OCI_AUTH_TYPE",
        "config_file": "OCI_CONFIG_FILE",
        "config_profile": "OCI_CONFIG_PROFILE",
        "output_method": "OCI_STRUCTURED_OUTPUT_METHOD",
        "reasoning_effort": "OCI_REASONING_EFFORT",
        "traces_endpoint": "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
        "service_name": "OTEL_SERVICE_NAME",
        "model_pricing_file": "MODEL_PRICING_FILE",
        "langfuse_base_url": "LANGFUSE_BASE_URL",
        "langfuse_public_key": "LANGFUSE_PUBLIC_KEY",
        "langfuse_secret_key": "LANGFUSE_SECRET_KEY",
        "langfuse_ingestion_version": "LANGFUSE_INGESTION_VERSION",
    }
    selected = {name: values[key] for name, key in fields.items() if key in values}
    if isinstance(selected.get("reasoning_effort"), str):
        selected["reasoning_effort"] = selected["reasoning_effort"].strip().upper()
    return Settings.model_validate(selected)


def create_extractor(settings: Settings):
    """Build an OCI model returning validated structured order items.

    Args:
        settings: Validated OCI configuration.

    Returns:
        LangChain structured-output runnable.
    """
    options = {
        "model_id": settings.model_id,
        "service_endpoint": settings.endpoint,
        "compartment_id": settings.compartment_id,
        "auth_type": settings.auth_type,
        "model_kwargs": {"temperature": 0},
    }
    if settings.reasoning_effort:
        options["model_kwargs"]["reasoning_effort"] = settings.reasoning_effort
    if settings.auth_type == "API_KEY":
        options.update(
            auth_file_location=str(Path(settings.config_file).expanduser()),
            auth_profile=settings.config_profile,
        )
    model = ChatOCIGenAI(**options)
    return model.with_structured_output(
        ExtractedOrder, method=settings.output_method, include_raw=True
    )
