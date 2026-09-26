"""
Author: L. Saetta (Luigi Saetta)
Last modified: 2026-09-26
License: MIT

Description:
    Covers all offline diagnostics of the Responses API demo doctor.
"""

import argparse
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
import openai
import pytest
from requests.exceptions import ConnectionError as RequestsConnectionError

from demos.order_fulfillment_responses import doctor
from demos.order_fulfillment_responses.config import Settings


def settings(**overrides) -> Settings:
    """Create test diagnostics settings.

    Args:
        **overrides: Settings changes.

    Returns:
        Validated non-secret configuration.
    """
    values = {
        "region": "us-chicago-1",
        "model_id": "test-model",
        "compartment_id": "test-compartment",
        "prompt_guard": "off",
        "pii_redaction": "off",
    }
    return Settings(**(values | overrides))


def reporter() -> tuple[doctor.Reporter, list[str]]:
    """Create a reporter with captured output.

    Returns:
        Reporter and its output lines.
    """
    lines: list[str] = []
    return doctor.Reporter(lines.append), lines


def test_reporter_and_expected_package_parsing(tmp_path):
    """Count result levels and parse only direct requirement pins."""
    result, lines = reporter()
    result.result("⚠️", "warning")
    result.result("❌", "error", "action")
    assert result.summary() == 1
    assert lines[-2:] == ["→ action", "1 errors, 1 warnings"]
    requirements = tmp_path / "requirements.txt"
    requirements.write_text("-c constraints.txt\nname[extra]==1\n", encoding="utf-8")
    assert doctor.expected_packages(requirements) == {"name": "1"}


@patch(
    "demos.order_fulfillment_responses.doctor.platform.machine", return_value="arm64"
)
@patch(
    "demos.order_fulfillment_responses.doctor.platform.system", return_value="Darwin"
)
def test_platform_and_dependency_diagnostics(_system, _machine):
    """Report platform and package mismatch outcomes without network access."""
    result, lines = reporter()
    doctor.check_platform(result)
    assert lines == ["✅ Platform: macOS arm64"]
    result, _ = reporter()
    with (
        patch.object(doctor, "expected_packages", return_value={"one": "1"}),
        patch.object(doctor.metadata, "version", return_value="0"),
    ):
        doctor.check_dependencies(result)
    assert result.errors == 1


def test_settings_and_authentication_diagnostics(tmp_path):
    """Handle missing dotenv, placeholders, resource principals, and key files."""
    result, _ = reporter()
    with patch.object(doctor, "AGENT_DIR", tmp_path):
        assert doctor.check_settings(result) is None
    environment = tmp_path / ".env"
    environment.write_text("MODEL_ID=replace-with-model\n", encoding="utf-8")
    result, _ = reporter()
    with patch.object(doctor, "AGENT_DIR", tmp_path):
        assert doctor.check_settings(result) is None
    result, lines = reporter()
    doctor.check_oci_authentication(settings(auth_type="RESOURCE_PRINCIPAL"), result)
    assert result.warnings == 1
    key = tmp_path / "key.pem"
    key.write_text("key", encoding="utf-8")
    result, _ = reporter()
    with (
        patch.object(
            doctor.oci.config, "from_file", return_value={"key_file": str(key)}
        ),
        patch.object(doctor.oci.config, "validate_config"),
    ):
        doctor.check_oci_authentication(
            settings(config_file=str(tmp_path / "config")), result
        )
    assert result.errors == 0
    assert lines


def test_langfuse_diagnostics_cover_disabled_offline_network_and_project():
    """Exercise all safe Langfuse diagnostic outcomes."""
    result, _ = reporter()
    doctor.check_langfuse(settings(), result, False)
    assert result.warnings == 1
    configured = settings(
        langfuse_base_url="https://langfuse.example",
        langfuse_public_key="pk",
        langfuse_secret_key="sk",
    )
    result, lines = reporter()
    doctor.check_langfuse(configured, result, True)
    assert "skipped" in lines[0]
    result, _ = reporter()
    with patch.object(doctor.requests, "get", side_effect=RequestsConnectionError):
        doctor.check_langfuse(configured, result, False)
    assert result.errors == 1
    response = Mock(status_code=200)
    response.json.return_value = {"data": [{"name": "demo"}]}
    result, lines = reporter()
    with patch.object(doctor.requests, "get", return_value=response):
        doctor.check_langfuse(configured, result, False)
    assert lines == ["✅ Langfuse: connected to demo"]


def test_pricing_pii_and_prompt_guard_diagnostics(tmp_path):
    """Cover local component and remote guardrail diagnostic branches."""
    result, _ = reporter()
    doctor.check_pricing(settings(), result)
    assert result.warnings == 1
    result, lines = reporter()
    doctor.check_pii(settings(pii_redaction="off"), result)
    assert "off" in lines[0]
    result, lines = reporter()
    doctor.check_prompt_guard(settings(prompt_guard="off"), result, False)
    assert lines == ["ℹ️ Prompt guard: off"]
    result, _ = reporter()
    doctor.check_prompt_guard(settings(prompt_guard="combined"), result, True)
    assert not result.errors
    result, _ = reporter()
    with (
        patch.object(doctor, "create_guardrails_client", return_value=Mock()),
        patch.object(doctor, "oci_flagged", return_value=False),
    ):
        doctor.check_prompt_guard(settings(prompt_guard="oci"), result, False)
    assert result.errors == 0
    assert tmp_path


@pytest.mark.parametrize("failure", ["invalid", "network"])
def test_model_and_run_doctor_failure_paths(failure):
    """Report malformed model output or network failure and aggregate results.

    Args:
        failure: Model failure mode to simulate.
    """
    result, _ = reporter()
    if failure == "invalid":
        client = SimpleNamespace(
            responses=SimpleNamespace(
                create=lambda **_: SimpleNamespace(
                    model_dump=lambda mode: {"status": "completed", "output": []}
                )
            )
        )
    else:
        client = SimpleNamespace(
            responses=SimpleNamespace(
                create=Mock(
                    side_effect=openai.APIConnectionError(
                        request=httpx.Request("POST", "https://example.test")
                    )
                )
            )
        )
    with patch.object(doctor, "create_responses_client", return_value=client):
        doctor.check_model(settings(), result, False)
    assert result.errors == 1
    arguments = argparse.Namespace(skip_model_call=True, offline=True)
    with patch.object(doctor, "check_settings", return_value=None):
        assert doctor.run_doctor(arguments, lambda _: None) == 0
