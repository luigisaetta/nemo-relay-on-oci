"""
Author: L. Saetta (Luigi Saetta)
Last modified: 2026-09-26
License: MIT

Description:
    Tests Responses API configuration and prompt-guard lifecycle cleanup.
"""

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import nemo_relay
import pytest
from pydantic import ValidationError

from demos.order_fulfillment_responses.config import Settings, load_settings
from demos.order_fulfillment_responses.telemetry import pii_component, relay_lifespan


def settings(**overrides) -> Settings:
    """Build valid local test settings.

    Args:
        **overrides: Explicit values to change.

    Returns:
        Validated settings.
    """
    values = {
        "region": "us-chicago-1",
        "model_id": "test-model",
        "compartment_id": "test-compartment",
        "prompt_guard": "pattern",
    }
    return Settings(**(values | overrides))


def test_dotenv_precedence_endpoint_and_invalid_settings(tmp_path, monkeypatch):
    """Prefer process values and reject malformed configuration before startup."""
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OCI_REGION=us-chicago-1\nMODEL_ID=file\nOCI_COMPARTMENT_ID=test\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MODEL_ID", "process")
    loaded = load_settings(env_file)
    assert loaded.model_id == "process"
    assert loaded.endpoint.endswith("us-chicago-1.oci.oraclecloud.com/openai/v1")
    with pytest.raises(ValidationError):
        Settings.model_validate({})


def test_relay_lifespan_deregisters_prompt_guard():
    """Always remove the process-wide guard callback after lifecycle shutdown."""
    activation = AsyncMock()
    activate = Mock(return_value=activation)
    registered = Mock()
    deregistered = Mock()

    async def exercise() -> None:
        """Enter and exit the configured lifecycle."""
        with (
            patch(
                "demos.order_fulfillment_responses.telemetry.plugin.activate", activate
            ),
            patch.object(
                nemo_relay.guardrails,
                "register_llm_conditional_execution",
                registered,
            ),
            patch.object(
                nemo_relay.guardrails,
                "deregister_llm_conditional_execution",
                deregistered,
            ),
        ):
            async with relay_lifespan(settings()):
                pass

    asyncio.run(exercise())
    registered.assert_called_once()
    deregistered.assert_called_once_with("prompt_guard")


@pytest.mark.parametrize("mode", ["mask", "redact"])
def test_pii_mask_and_redact_components_use_the_selected_action(mode):
    """Configure each supported active PII policy.

    Args:
        mode: Requested Relay built-in action.
    """
    component = pii_component(settings(pii_redaction=mode))
    assert component is not None
    assert component.config.builtin.action == mode


def test_pii_off_omits_the_component():
    """Avoid installing a telemetry sanitizer when explicitly disabled."""
    assert pii_component(settings(pii_redaction="off")) is None
