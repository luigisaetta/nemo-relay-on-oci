"""
Author: L. Saetta (Luigi Saetta)
Last modified: 2026-09-26
License: MIT

Description:
    Tests configuration loading, catalog validation, and Relay lifecycle behavior.
"""

import asyncio
import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
from pydantic import ValidationError

from demos.order_fulfillment.config import Settings, create_extractor, load_settings
from demos.order_fulfillment.inventory import Inventory
from demos.order_fulfillment.models import ExtractedOrder
from demos.order_fulfillment.telemetry import relay_lifespan


def test_dotenv_precedence_and_auth_modes(tmp_path, monkeypatch):
    """Load only the selected agent file and prefer process variables.

    Args:
        tmp_path: Isolated temporary directory.
        monkeypatch: Pytest environment override helper.
    """
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OCI_REGION=us-chicago-1\nMODEL_ID=file-model\nOCI_COMPARTMENT_ID=test\n"
    )
    monkeypatch.setenv("MODEL_ID", "process-model")
    monkeypatch.chdir(tmp_path)
    settings = load_settings(env_file)
    assert settings.model_id == "process-model"
    assert (
        settings.endpoint
        == "https://inference.generativeai.us-chicago-1.oci.oraclecloud.com"
    )
    assert settings.auth_type == "API_KEY"
    monkeypatch.setenv("OCI_AUTH_TYPE", "RESOURCE_PRINCIPAL")
    assert load_settings(env_file).auth_type == "RESOURCE_PRINCIPAL"
    monkeypatch.setenv("OCI_AUTH_TYPE", "INVALID")
    with pytest.raises(ValidationError):
        load_settings(env_file)


@pytest.mark.parametrize("auth_type", ["API_KEY", "RESOURCE_PRINCIPAL"])
def test_model_authentication(auth_type):
    """Pass the proper authentication settings without reading credentials.

    Args:
        auth_type: OCI authentication mode under test.
    """
    settings = Settings(
        region="us-chicago-1",
        model_id="test",
        compartment_id="test",
        auth_type=auth_type,
    )
    with patch("demos.order_fulfillment.config.ChatOCIGenAI") as model:
        create_extractor(settings)
        options = model.call_args.kwargs
        assert options["auth_type"] == auth_type
        assert options["service_endpoint"] == settings.endpoint
        assert ("auth_file_location" in options) == (auth_type == "API_KEY")
        assert ("auth_profile" in options) == (auth_type == "API_KEY")
        model.return_value.with_structured_output.assert_called_once_with(
            ExtractedOrder, method=settings.output_method, include_raw=True
        )
    with patch(
        "demos.order_fulfillment.config.ChatOCIGenAI", side_effect=ValueError("auth")
    ):
        with pytest.raises(ValueError):
            create_extractor(settings)


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"region": "https://evil", "model_id": "x", "compartment_id": "x"},
        {"region": "us-chicago-1", "model_id": " ", "compartment_id": "x"},
    ],
)
def test_invalid_settings(values):
    """Fail startup validation for missing or invalid required values.

    Args:
        values: Invalid settings payload.
    """
    with pytest.raises(ValidationError):
        Settings.model_validate(values)


@pytest.mark.parametrize(
    "entries",
    [
        [],
        [{"product_id": "x", "name": "X", "available": -1}],
        [{"product_id": "x", "name": "X", "available": 1}] * 2,
    ],
)
def test_invalid_catalog(tmp_path, entries):
    """Reject empty, negative-stock, and duplicate-ID catalogs.

    Args:
        tmp_path: Temporary directory.
        entries: Invalid catalog payload.
    """
    path = tmp_path / "catalog.json"
    path.write_text(json.dumps(entries))
    with pytest.raises(ValueError):
        Inventory.load(path)


def test_missing_catalog_and_invalid_registration(tmp_path):
    """Fail clearly for missing catalogs and unknown registration products.

    Args:
        tmp_path: Temporary directory.
    """
    with pytest.raises(OSError):
        Inventory.load(tmp_path / "missing.json")
    inventory = Inventory({})
    with pytest.raises(ValueError):
        inventory.register("unknown", 1)
    with pytest.raises(ValueError):
        inventory.register("unknown", 0)


def test_relay_configuration_and_cleanup():
    """Configure native OTLP and exit the activation even after a failure."""
    settings = Settings(
        region="us-chicago-1",
        model_id="x",
        compartment_id="x",
        traces_endpoint="http://localhost:4318/v1/traces",
    )
    activation = AsyncMock()
    factory = Mock(return_value=activation)

    async def exercise():
        """Exercise exporter cleanup through exceptional application shutdown."""
        with patch("demos.order_fulfillment.telemetry.plugin.activate", factory):
            with pytest.raises(RuntimeError):
                async with relay_lifespan(settings):
                    raise RuntimeError("application failure")
        configuration = factory.call_args.args[0].to_dict()
        endpoint = configuration["components"][0]["config"]["opentelemetry"][
            "endpoints"
        ][0]
        assert endpoint["transport"] == "http_binary"
        assert endpoint["service_name"] == "order-fulfillment"
        activation.__aexit__.assert_awaited_once()
        settings.traces_endpoint = "file:///tmp/invalid"
        with pytest.raises(ValueError):
            async with relay_lifespan(settings):
                pytest.fail("Invalid endpoint was accepted")

    asyncio.run(exercise())


@pytest.mark.parametrize("effort", ["", "NONE", "LOW"])
def test_reasoning_effort_forwarding(effort):
    """Forward only explicitly configured reasoning parameters to OCI.

    Args:
        effort: Optional SDK reasoning effort value.
    """
    settings = Settings(
        region="us-chicago-1",
        model_id="test",
        compartment_id="test",
        reasoning_effort=effort,
    )
    with patch("demos.order_fulfillment.config.ChatOCIGenAI") as model:
        create_extractor(settings)
        parameters = model.call_args.kwargs["model_kwargs"]
        if effort:
            assert parameters["reasoning_effort"] == effort
        else:
            assert "reasoning_effort" not in parameters


def test_reasoning_effort_environment(tmp_path, monkeypatch):
    """Normalize the setting to OCI SDK enums and reject unsupported values.

    Args:
        tmp_path: Temporary configuration directory.
        monkeypatch: Isolated process environment overrides.
    """
    env_file = tmp_path / ".env"
    env_file.write_text(
        "OCI_REGION=us-chicago-1\nMODEL_ID=test\nOCI_COMPARTMENT_ID=test\n"
    )
    monkeypatch.setenv("OCI_REASONING_EFFORT", " none ")
    assert load_settings(env_file).reasoning_effort == "NONE"
    monkeypatch.setenv("OCI_REASONING_EFFORT", "unsupported")
    with pytest.raises(ValidationError):
        load_settings(env_file)
