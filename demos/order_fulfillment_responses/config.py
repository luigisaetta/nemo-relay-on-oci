"""
Author: L. Saetta (Luigi Saetta)
Last modified: 2026-09-26
License: MIT

Description:
    Loads Responses API settings and creates OCI-authenticated OpenAI clients.
"""

import os
from pathlib import Path
from typing import Literal

from dotenv import dotenv_values
import httpx
from openai import OpenAI
import oci
from oci_genai_auth import OciResourcePrincipalAuth, OciUserPrincipalAuth
from pydantic import BaseModel, Field, SecretStr

from demos.order_fulfillment_responses.models import Name

AGENT_DIR = Path(__file__).resolve().parent
ENVIRONMENT_FIELDS = {
    "region": "OCI_REGION",
    "model_id": "MODEL_ID",
    "compartment_id": "OCI_COMPARTMENT_ID",
    "auth_type": "OCI_AUTH_TYPE",
    "config_file": "OCI_CONFIG_FILE",
    "config_profile": "OCI_CONFIG_PROFILE",
    "reasoning_effort": "OCI_REASONING_EFFORT",
    "traces_endpoint": "OTEL_EXPORTER_OTLP_TRACES_ENDPOINT",
    "service_name": "OTEL_SERVICE_NAME",
    "model_pricing_file": "MODEL_PRICING_FILE",
    "pii_redaction": "PII_REDACTION",
    "langfuse_base_url": "LANGFUSE_BASE_URL",
    "langfuse_public_key": "LANGFUSE_PUBLIC_KEY",
    "langfuse_secret_key": "LANGFUSE_SECRET_KEY",
    "langfuse_ingestion_version": "LANGFUSE_INGESTION_VERSION",
    "prompt_guard": "PROMPT_GUARD",
    "oci_guardrail_version": "OCI_GUARDRAIL_VERSION",
    "prompt_guard_on_error": "PROMPT_GUARD_ON_ERROR",
}


class Settings(BaseModel):
    """Validated agent-local settings without exposing secrets."""

    region: str = Field(pattern=r"^[a-z]+(?:-[a-z0-9]+)+-\d+$")
    model_id: Name
    compartment_id: Name
    auth_type: Literal["API_KEY", "RESOURCE_PRINCIPAL"] = "API_KEY"
    config_file: str = "~/.oci/config"
    config_profile: Name = "DEFAULT"
    reasoning_effort: Literal["", "none", "minimal", "low", "medium", "high"] = ""
    traces_endpoint: str = ""
    service_name: Name = "order-fulfillment-responses"
    model_pricing_file: str = ""
    pii_redaction: Literal["mask", "redact", "off"] = "mask"
    prompt_guard: Literal["combined", "oci", "pattern", "off"] = "combined"
    oci_guardrail_version: str = "1.1.3"
    prompt_guard_on_error: Literal["allow", "block"] = "allow"
    langfuse_base_url: str = ""
    langfuse_public_key: SecretStr = SecretStr("")
    langfuse_secret_key: SecretStr = SecretStr("")
    langfuse_ingestion_version: Literal["", "4"] = ""

    @property
    def endpoint(self) -> str:
        """Return the OCI OpenAI-compatible Responses endpoint.

        Returns:
            Regional OCI OpenAI API base URL.
        """
        return f"https://inference.generativeai.{self.region}.oci.oraclecloud.com/openai/v1"


def load_settings(env_file: Path = AGENT_DIR / ".env") -> Settings:
    """Load agent-local dotenv values with process values taking precedence.

    Args:
        env_file: Explicit dotenv path.

    Returns:
        Validated settings.

    Raises:
        ValueError: A required or constrained setting is invalid.
    """
    values = {**dotenv_values(env_file), **os.environ}
    selected = {
        name: values[key] for name, key in ENVIRONMENT_FIELDS.items() if key in values
    }
    if isinstance(selected.get("reasoning_effort"), str):
        selected["reasoning_effort"] = selected["reasoning_effort"].strip().lower()
    return Settings.model_validate(selected)


def create_responses_client(settings: Settings) -> OpenAI:
    """Create the official SDK client with OCI IAM HTTPX authentication.

    Args:
        settings: Validated OCI region, compartment, and authentication settings.

    Returns:
        OpenAI SDK client configured for OCI's Responses endpoint.
    """
    if settings.auth_type == "API_KEY":
        auth = OciUserPrincipalAuth(
            config_file=str(Path(settings.config_file).expanduser()),
            profile_name=settings.config_profile,
        )
    else:
        auth = OciResourcePrincipalAuth()
    return OpenAI(
        base_url=settings.endpoint,
        api_key="not-used",
        default_headers={
            "opc-compartment-id": settings.compartment_id,
            "CompartmentId": settings.compartment_id,
        },
        http_client=httpx.Client(auth=auth, timeout=httpx.Timeout(30.0, connect=10.0)),
    )


def create_guardrails_client(settings: Settings):
    """Create OCI ApplyGuardrails client using the selected IAM mode.

    Args:
        settings: Validated OCI configuration.

    Returns:
        OCI Generative AI inference client.
    """
    endpoint = settings.endpoint.removesuffix("/openai/v1")
    options = {"service_endpoint": endpoint, "timeout": (5, 10)}
    if settings.auth_type == "API_KEY":
        config = oci.config.from_file(
            str(Path(settings.config_file).expanduser()), settings.config_profile
        )
        return oci.generative_ai_inference.GenerativeAiInferenceClient(
            config, **options
        )
    signer = oci.auth.signers.get_resource_principals_signer()
    return oci.generative_ai_inference.GenerativeAiInferenceClient(
        {}, signer=signer, **options
    )
