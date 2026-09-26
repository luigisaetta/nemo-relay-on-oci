"""
Author: L. Saetta (Luigi Saetta)
Last modified: 2026-09-26
License: MIT

Description:
    Tests the offline setup diagnostics for the order-fulfillment demo.
"""

import argparse
from pathlib import Path
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock, patch

from oci.exceptions import ServiceError
from requests.exceptions import ConnectionError as RequestsConnectionError

from demos.order_fulfillment.config import Settings
from demos.order_fulfillment import doctor
from demos.order_fulfillment.models import ExtractedOrder


def settings(**overrides) -> Settings:
    """Create safe default settings for diagnostic tests.

    Args:
        **overrides: Settings fields to replace.

    Returns:
        Validated synthetic settings.
    """
    values = {
        "region": "eu-frankfurt-1",
        "model_id": "test-model",
        "compartment_id": "ocid1.compartment.test",
    }
    return Settings(**(values | overrides))


def reporter() -> tuple[doctor.Reporter, list[str]]:
    """Create a diagnostic reporter with captured output.

    Returns:
        Reporter and its output lines.
    """
    lines = []
    return doctor.Reporter(lines.append), lines


def test_reporter_counts_results_and_summarizes():
    """Count warnings and errors while emitting actions."""
    result, lines = reporter()
    result.result("✅", "ok")
    result.result("⚠️", "warning", "fix warning")
    result.result("❌", "error", "fix error")
    assert result.summary() == 1
    assert lines == [
        "✅ ok",
        "⚠️ warning",
        "→ fix warning",
        "❌ error",
        "→ fix error",
        "1 errors, 1 warnings",
    ]


def test_expected_packages_reads_only_runtime_pins(tmp_path):
    """Ignore constraints, comments, and extras while reading pins."""
    requirements = tmp_path / "requirements.txt"
    requirements.write_text(
        "-c constraints.txt\nname[extra]==1.2\n# comment\nother==3\n"
    )
    assert doctor.expected_packages(requirements) == {"name": "1.2", "other": "3"}


@patch("demos.order_fulfillment.doctor.platform.machine", return_value="arm64")
@patch("demos.order_fulfillment.doctor.platform.system", return_value="Darwin")
def test_platform_reports_supported(system, machine):
    """Report the only tested platform as supported."""
    result, lines = reporter()
    doctor.check_platform(result)
    assert lines == ["✅ Platform: macOS arm64"]
    system.assert_called_once()
    machine.assert_called_once()


@patch("demos.order_fulfillment.doctor.platform.machine", return_value="x86_64")
@patch("demos.order_fulfillment.doctor.platform.system", return_value="Linux")
def test_platform_warns_for_untested(_system, _machine):
    """Warn rather than fail for an untested platform."""
    result, lines = reporter()
    doctor.check_platform(result)
    assert result.warnings == 1
    assert "TODO.md" in "\n".join(lines)


def test_dependencies_reports_missing_and_mismatched_packages():
    """Identify environment distribution failures safely."""
    result, lines = reporter()
    with (
        patch.object(
            doctor, "expected_packages", return_value={"one": "1", "two": "2"}
        ),
        patch.object(
            doctor.metadata,
            "version",
            side_effect=["0", doctor.metadata.PackageNotFoundError],
        ),
    ):
        doctor.check_dependencies(result)
    assert result.errors == 1
    assert "one is 0, expected 1" in lines[0]
    assert "two is missing" in lines[0]


def test_settings_detects_placeholder_and_validation_failure(tmp_path):
    """Never print placeholder values or validation details."""
    result, lines = reporter()
    environment = tmp_path / ".env"
    environment.write_text("MODEL_ID=replace-with-model\n")
    with patch.object(doctor, "AGENT_DIR", tmp_path):
        assert doctor.check_settings(result) is None
    assert "MODEL_ID" in lines[0]

    result, lines = reporter()
    environment.write_text("MODEL_ID=test\n")
    with (
        patch.object(doctor, "AGENT_DIR", tmp_path),
        patch.object(doctor, "load_settings", side_effect=InvalidSettingsError()),
    ):
        assert doctor.check_settings(result) is None
    assert "OCI_REGION" in lines[0]
    assert "secret" not in "\n".join(lines)


def test_oci_authentication_handles_resource_principal_and_missing_config(tmp_path):
    """Skip runtime credentials and report absent local config safely."""
    result, lines = reporter()
    doctor.check_oci_authentication(settings(auth_type="RESOURCE_PRINCIPAL"), result)
    assert "skipped locally" in lines[0]

    result, lines = reporter()
    doctor.check_oci_authentication(
        settings(config_file=str(tmp_path / "missing")), result
    )
    assert result.errors == 1
    assert "configuration file is missing" in lines[0]


def test_oci_authentication_accepts_valid_key_file(tmp_path):
    """Validate an API-key profile without printing the key path."""
    config = tmp_path / "config"
    key = tmp_path / "key.pem"
    config.write_text("unused")
    key.write_text("private")
    result, lines = reporter()
    with (
        patch.object(
            doctor.oci.config, "from_file", return_value={"key_file": str(key)}
        ),
        patch.object(doctor.oci.config, "validate_config"),
    ):
        doctor.check_oci_authentication(
            settings(config_file=str(config), config_profile="PROFILE"), result
        )
    assert lines == ["✅ OCI credentials: API_KEY profile PROFILE is valid"]
    assert str(key) not in "\n".join(lines)


def test_model_check_success_errors_and_skip():
    """Map model outcomes to safe corrective actions."""
    result, lines = reporter()
    extractor = Mock()
    extractor.invoke.return_value = {
        "raw": SimpleNamespace(usage_metadata={"total_tokens": 7}),
        "parsed": ExtractedOrder(items=[{"product": "keyboard", "quantity": 1}]),
        "parsing_error": None,
    }
    with (
        patch.object(doctor, "create_extractor", return_value=extractor),
        patch.object(doctor, "configure_warning_filters") as warning_filter,
    ):
        doctor.check_model(settings(), result, False)
    assert "7 total tokens" in lines[0]
    warning_filter.assert_called_once()

    result, lines = reporter()
    error = ServiceError(400, "BadRequest", {}, "private provider text")
    with patch.object(doctor, "create_extractor", side_effect=error):
        doctor.check_model(settings(), result, False)
    assert "private provider text" not in "\n".join(lines)
    assert "OCI_STRUCTURED_OUTPUT_METHOD" in "\n".join(lines)

    result, lines = reporter()
    doctor.check_model(settings(), result, True)
    assert lines == ["ℹ️ OCI model call: skipped"]


class InvalidSettingsError(ValueError):
    """Provide Pydantic-like error details without exposing a bad value."""

    def errors(self):
        """Return the invalid settings field location.

        Returns:
            Validation details compatible with Pydantic.
        """
        return [{"loc": ("region",)}]


def test_model_check_rejects_unparsed_and_unexpected_responses():
    """Report structured-output and unexpected errors without provider text."""
    result, lines = reporter()
    extractor = Mock()
    extractor.invoke.return_value = {"parsed": None, "parsing_error": ValueError("x")}
    with patch.object(doctor, "create_extractor", return_value=extractor):
        doctor.check_model(settings(), result, False)
    assert "could not be parsed" in lines[0]
    assert "OCI_STRUCTURED_OUTPUT_METHOD" in lines[1]

    result, lines = reporter()
    with patch.object(
        doctor, "create_extractor", side_effect=RuntimeError("private details")
    ):
        doctor.check_model(settings(), result, False)
    assert "RuntimeError" in lines[0]
    assert "private details" not in "\n".join(lines)


def test_langfuse_handles_disabled_offline_and_remote_errors():
    """Check optional tracing without leaking authorization values."""
    result, lines = reporter()
    doctor.check_langfuse(settings(), result, False)
    assert result.warnings == 1

    configured = settings(
        langfuse_base_url="https://cloud.langfuse.com",
        langfuse_public_key="pk",
        langfuse_secret_key="sk-lf-test-secret",
    )
    result, lines = reporter()
    with patch.object(doctor, "trace_endpoints"):
        doctor.check_langfuse(configured, result, True)
    assert "skipped" in lines[0]

    result, lines = reporter()
    with (
        patch.object(doctor, "trace_endpoints"),
        patch.object(doctor.requests, "get", side_effect=RequestsConnectionError),
    ):
        doctor.check_langfuse(configured, result, False)
    assert result.errors == 1
    assert "sk-lf-test-secret" not in "\n".join(lines)


def test_langfuse_non_json_success_uses_generic_project_name():
    """Accept a successful Langfuse status even when its body is not JSON."""
    configured = settings(
        langfuse_base_url="https://cloud.langfuse.com",
        langfuse_public_key="pk",
        langfuse_secret_key="sk",
    )
    response = Mock(status_code=200)
    response.json.side_effect = ValueError("not json")
    result, lines = reporter()
    with (
        patch.object(doctor, "trace_endpoints"),
        patch.object(doctor.requests, "get", return_value=response),
    ):
        doctor.check_langfuse(configured, result, False)
    assert lines == ["✅ Langfuse: connected to configured project"]


def test_langfuse_empty_project_list_rejects_bad_credentials():
    """Reject a successful response that has no project for the API keys."""
    configured = settings(
        langfuse_base_url="https://cloud.langfuse.com",
        langfuse_public_key="pk-invalid",
        langfuse_secret_key="sk",
    )
    response = Mock(status_code=200)
    response.json.return_value = {"data": []}
    result, lines = reporter()
    with (
        patch.object(doctor, "trace_endpoints"),
        patch.object(doctor.requests, "get", return_value=response),
    ):
        doctor.check_langfuse(configured, result, False)
    assert result.errors == 1
    assert "no project is associated" in lines[0]
    assert "pk-invalid" not in "\n".join(lines)


def test_pricing_skips_default_and_checks_custom_catalog(tmp_path):
    """Avoid validating the repository default while validating custom files."""
    default = tmp_path / "default.json"
    default.write_text('{"entries": []}')
    result, _ = reporter()
    with (
        patch.object(doctor, "DEFAULT_PRICING_FILE", default),
        patch.object(doctor, "pricing_component") as pricing,
    ):
        doctor.check_pricing(settings(model_pricing_file=str(default)), result)
    pricing.assert_not_called()
    assert result.warnings == 1

    custom = tmp_path / "custom.json"
    custom.write_text('{"entries": []}')
    result, _ = reporter()
    with patch.object(doctor, "pricing_component", side_effect=ValueError("bad")):
        doctor.check_pricing(settings(model_pricing_file=str(custom)), result)
    assert result.errors == 1


def test_pii_and_run_doctor_exit_codes():
    """Report PII mode and aggregate only errors into the exit code."""
    result, lines = reporter()
    with patch.object(doctor, "pii_component"):
        doctor.check_pii(settings(pii_redaction="mask"), result)
    assert "mask" in lines[0]

    calls = [
        doctor.check_platform,
        doctor.check_python_and_conda,
        doctor.check_dependencies,
    ]
    with (
        patch.object(doctor, "check_platform") as platform_check,
        patch.object(doctor, "check_python_and_conda") as python_check,
        patch.object(doctor, "check_dependencies") as dependency_check,
        patch.object(doctor, "check_settings", return_value=None),
    ):
        arguments = argparse.Namespace(skip_model_call=False, offline=True)
        assert doctor.run_doctor(arguments, lambda _: None) == 0
    assert all(call.called for call in [platform_check, python_check, dependency_check])
    assert calls


def test_prompt_guard_diagnostics_cover_offline_success_and_errors():
    """Report safe OCI guardrail outcomes and an unpinned-version warning."""
    result, lines = reporter()
    doctor.check_prompt_guard(settings(prompt_guard="off"), result, False)
    assert lines == ["ℹ️ Prompt guard: off"]

    result, lines = reporter()
    doctor.check_prompt_guard(settings(oci_guardrail_version=""), result, True)
    assert result.warnings == 1
    assert "skipped by --offline" in lines[-1]

    result, lines = reporter()
    with (
        patch.object(doctor, "create_guardrails_client", return_value=Mock()),
        patch.object(doctor, "oci_flagged", return_value=False),
    ):
        doctor.check_prompt_guard(settings(), result, False)
    assert "accepted an innocent" in lines[0]

    result, lines = reporter()
    with patch.object(
        doctor,
        "oci_flagged",
        side_effect=ServiceError(403, "NotAuthorized", {}, "private details"),
    ):
        doctor.check_prompt_guard(settings(), result, False)
    assert "private details" not in "\n".join(lines)
    assert "service error 403" in lines[0]


def test_setup_script_is_valid_posix_shell():
    """Keep the setup script parseable by POSIX sh."""
    script = Path("scripts/setup.sh")
    assert script.is_file()
    assert subprocess.run(["sh", "-n", str(script)], check=False).returncode == 0
    assert 'cd "$(dirname "$0")/.."' in script.read_text(encoding="utf-8")
