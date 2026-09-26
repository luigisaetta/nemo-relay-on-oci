"""
Author: L. Saetta (Luigi Saetta)
Last modified: 2026-09-26
License: MIT

Description:
    Diagnoses safe setup prerequisites for the OCI Responses API demonstration.
"""

from __future__ import annotations

import argparse
from base64 import b64encode
from dataclasses import dataclass
from importlib import metadata
import os
from pathlib import Path
import platform
import sys
from typing import Callable

import oci
import openai
import requests

from demos.order_fulfillment_responses.config import (
    AGENT_DIR,
    ENVIRONMENT_FIELDS,
    Settings,
    create_guardrails_client,
    create_responses_client,
    load_settings,
)
from demos.order_fulfillment_responses.nodes import output_text, responses_request
from demos.order_fulfillment_responses.prompt_guard import oci_flagged
from demos.order_fulfillment_responses.telemetry import (
    pii_component,
    pricing_component,
    trace_endpoints,
)

ROOT_DIR = AGENT_DIR.parent.parent
REQUIREMENTS_FILE = ROOT_DIR / "requirements.txt"


@dataclass
class Reporter:
    """Collect safe diagnostic outcomes.

    Attributes:
        write: Output callback.
        errors: Number of failed checks.
        warnings: Number of advisory checks.
    """

    write: Callable[[str], None] = print
    errors: int = 0
    warnings: int = 0

    def result(self, symbol: str, message: str, action: str = "") -> None:
        """Record one result without disclosing credentials or provider messages.

        Args:
            symbol: Result indicator.
            message: Safe message.
            action: Optional safe remediation.
        """
        self.write(f"{symbol} {message}")
        self.errors += symbol == "❌"
        self.warnings += symbol == "⚠️"
        if action:
            self.write(f"→ {action}")

    def summary(self) -> int:
        """Print summary and return command exit status.

        Returns:
            One if an error was reported, otherwise zero.
        """
        self.write(f"{self.errors} errors, {self.warnings} warnings")
        return int(bool(self.errors))


def expected_packages(path: Path = REQUIREMENTS_FILE) -> dict[str, str]:
    """Read exact runtime package pins.

    Args:
        path: Requirements file.

    Returns:
        Normalized package-to-version mapping.
    """
    packages = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if value and not value.startswith(("#", "-")) and "==" in value:
            name, version = value.split("==", maxsplit=1)
            packages[name.split("[", maxsplit=1)[0].lower().replace("_", "-")] = version
    return packages


def check_platform(reporter: Reporter) -> None:
    """Report supported local platform status.

    Args:
        reporter: Result collector.
    """
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        reporter.result("✅", "Platform: macOS arm64")
    else:
        reporter.result("⚠️", "Platform: untested platform, see TODO.md")


def check_python_and_conda(reporter: Reporter) -> None:
    """Check Python version and selected Conda environment.

    Args:
        reporter: Result collector.
    """
    if sys.version_info >= (3, 11):
        reporter.result(
            "✅", f"Python: {sys.version_info.major}.{sys.version_info.minor}"
        )
    else:
        reporter.result("❌", "Python: version 3.11 or newer is required")
    active = os.environ.get("CONDA_DEFAULT_ENV", "")
    if active and active != "nemo-relay-on-oci":
        reporter.result("⚠️", "Conda: a different environment is active")


def check_dependencies(reporter: Reporter) -> None:
    """Report missing or incompatible pinned dependencies.

    Args:
        reporter: Result collector.
    """
    failures = []
    for package, expected in expected_packages().items():
        try:
            actual = metadata.version(package)
        except metadata.PackageNotFoundError:
            failures.append(f"{package} is missing")
        else:
            if actual != expected:
                failures.append(f"{package} is {actual}, expected {expected}")
    if failures:
        reporter.result(
            "❌", "Dependencies: " + "; ".join(failures), "Run scripts/setup.sh."
        )
    else:
        reporter.result("✅", "Dependencies: installed versions match requirements.txt")


def check_settings(reporter: Reporter) -> Settings | None:
    """Load settings while keeping raw values out of output.

    Args:
        reporter: Result collector.

    Returns:
        Settings or none after a safe failure report.
    """
    env_file = AGENT_DIR / ".env"
    if not env_file.is_file():
        reporter.result(
            "❌",
            "Environment: .env is missing",
            "Copy .env.example to .env and configure it.",
        )
        return None
    if any(
        value.strip().strip("'\"").startswith("replace-with")
        for line in env_file.read_text(encoding="utf-8").splitlines()
        if "=" in line and not line.lstrip().startswith("#")
        for _, value in [line.split("=", maxsplit=1)]
    ):
        reporter.result("❌", "Environment: a required value is a placeholder")
        return None
    try:
        settings = load_settings(env_file)
    except ValueError as error:
        details = error.errors() if hasattr(error, "errors") else []
        location = details[0].get("loc", ()) if details else ()
        variable = ENVIRONMENT_FIELDS.get(
            str(location[0]) if location else "", "configuration"
        )
        reporter.result("❌", f"Environment: invalid setting {variable}")
        return None
    reporter.result("✅", "Environment: configuration is valid")
    return settings


def check_oci_authentication(settings: Settings, reporter: Reporter) -> None:
    """Validate local API-key prerequisites or report resource-principal scope.

    Args:
        settings: Validated configuration.
        reporter: Result collector.
    """
    if settings.auth_type == "RESOURCE_PRINCIPAL":
        reporter.result(
            "⚠️",
            "OCI credentials: RESOURCE_PRINCIPAL is not live-verified for the Responses client",
        )
        return
    path = Path(settings.config_file).expanduser()
    try:
        config = oci.config.from_file(str(path), settings.config_profile)
        oci.config.validate_config(config)
    except (OSError, ValueError, KeyError):
        reporter.result("❌", "OCI credentials: configuration or profile is invalid")
        return
    if not Path(config.get("key_file", "")).expanduser().is_file():
        reporter.result("❌", "OCI credentials: private key file is not readable")
        return
    reporter.result(
        "✅", f"OCI credentials: API_KEY profile {settings.config_profile} is valid"
    )


def check_model(settings: Settings, reporter: Reporter, skip: bool) -> None:
    """Make one small structured Responses request when allowed.

    Args:
        settings: Validated configuration.
        reporter: Result collector.
        skip: Whether network work is disabled.
    """
    if skip:
        reporter.result("ℹ️", "OCI Responses model call: skipped")
        return
    try:
        response = create_responses_client(settings).responses.create(
            **responses_request(
                settings.model_id, "I would like 1 keyboard", settings.reasoning_effort
            )
        )
        dumped = response.model_dump(mode="json")
        if output_text(dumped) is None:
            reporter.result(
                "❌",
                "OCI Responses model call: structured output was invalid",
                "Check model and reasoning settings.",
            )
            return
        reporter.result(
            "✅", "OCI Responses model call: structured extraction succeeded"
        )
    except openai.APIStatusError as error:
        actions = {
            400: "Check model, JSON schema parameters, and OCI_REASONING_EFFORT.",
            401: "Check IAM policy and compartment.",
            403: "Check IAM policy and compartment.",
            404: "Check model availability in this region and through Responses API.",
        }
        reporter.result(
            "❌",
            f"OCI Responses model call: service error {error.status_code}",
            actions.get(error.status_code, "Review OCI configuration."),
        )
    except (openai.APIConnectionError, openai.APITimeoutError, OSError):
        reporter.result(
            "❌",
            "OCI Responses model call: network or timeout failure",
            "Check region and connectivity.",
        )
    except (AttributeError, TypeError, ValueError) as error:
        reporter.result(
            "❌", f"OCI Responses model call: unexpected {type(error).__name__}"
        )


def check_optional_components(settings: Settings, reporter: Reporter) -> None:
    """Validate local pricing and PII policies without network calls.

    Args:
        settings: Validated configuration.
        reporter: Result collector.
    """
    try:
        pricing_component(settings)
        pii_component(settings)
    except ValueError as error:
        reporter.result("❌", f"Relay configuration: {error}")
    else:
        reporter.result("✅", "Relay pricing and PII configuration is valid")


def check_langfuse(settings: Settings, reporter: Reporter, offline: bool) -> None:
    """Validate configured Langfuse credentials without exposing them.

    Args:
        settings: Validated telemetry settings.
        reporter: Result collector.
        offline: Whether remote verification is disabled.
    """
    values = (
        settings.langfuse_base_url.strip(),
        settings.langfuse_public_key.get_secret_value().strip(),
        settings.langfuse_secret_key.get_secret_value().strip(),
    )
    if not any(values):
        reporter.result("⚠️", "Langfuse: traces will not be exported")
        return
    if "/api/public" in values[0]:
        reporter.result("❌", "Langfuse: use only the base URL")
        return
    try:
        trace_endpoints(settings)
    except ValueError:
        reporter.result(
            "❌", "Langfuse: configuration is incomplete or conflicts with OTLP"
        )
        return
    if offline:
        reporter.result("ℹ️", "Langfuse: network check skipped by --offline")
        return
    authorization = b64encode(f"{values[1]}:{values[2]}".encode()).decode("ascii")
    try:
        response = requests.get(
            values[0].rstrip("/") + "/api/public/projects",
            headers={"Authorization": f"Basic {authorization}"},
            timeout=5,
        )
    except requests.exceptions.RequestException:
        reporter.result("❌", "Langfuse: network request failed")
        return
    if response.status_code == 200:
        report_langfuse_project(response, reporter)
    elif response.status_code in {401, 403}:
        reporter.result(
            "❌", "Langfuse: credentials are invalid for this project or region"
        )
    else:
        reporter.result("❌", f"Langfuse: unexpected status {response.status_code}")


def report_langfuse_project(response: requests.Response, reporter: Reporter) -> None:
    """Report a safe configured-project check result.

    Args:
        response: Successful Langfuse response.
        reporter: Result collector.
    """
    try:
        payload = response.json()
    except ValueError:
        reporter.result("✅", "Langfuse: connected to configured project")
        return
    data = payload.get("data", []) if isinstance(payload, dict) else []
    if not data:
        reporter.result(
            "❌", "Langfuse: no project is associated with the configured keys"
        )
        return
    reporter.result(
        "✅", f"Langfuse: connected to {data[0].get('name', 'configured project')}"
    )


def check_pricing(settings: Settings, reporter: Reporter) -> None:
    """Report pricing-catalog coverage of the configured model.

    Args:
        settings: Validated pricing settings.
        reporter: Result collector.
    """
    if not settings.model_pricing_file.strip():
        reporter.result("⚠️", "Pricing: no cost estimates")
        return
    try:
        component = pricing_component(settings)
    except ValueError:
        reporter.result("❌", "Pricing: catalog is invalid")
        return
    if component is None:
        reporter.result("⚠️", "Pricing: no cost estimates")
    else:
        reporter.result("✅", "Pricing: catalog includes the configured model")


def check_pii(settings: Settings, reporter: Reporter) -> None:
    """Report the active PII-redaction setting.

    Args:
        settings: Validated PII settings.
        reporter: Result collector.
    """
    pii_component(settings)
    if settings.pii_redaction == "off":
        reporter.result("ℹ️", "PII redaction: off; phone numbers remain in telemetry")
    else:
        reporter.result(
            "ℹ️",
            f"PII redaction: {settings.pii_redaction}; phone numbers are sanitized in telemetry",
        )


def check_prompt_guard(settings: Settings, reporter: Reporter, offline: bool) -> None:
    """Report prompt-guard configuration and optionally call OCI safely.

    Args:
        settings: Validated guardrail settings.
        reporter: Result collector.
        offline: Whether OCI validation is disabled.
    """
    if settings.prompt_guard == "off":
        reporter.result("ℹ️", "Prompt guard: off")
        return
    if not settings.oci_guardrail_version:
        reporter.result("⚠️", "Prompt guard: OCI guardrail version is not pinned")
    if settings.prompt_guard == "pattern":
        reporter.result("✅", "Prompt guard: pattern mode is configured")
        return
    if offline:
        reporter.result("ℹ️", "Prompt guard: OCI check skipped by --offline")
        return
    try:
        flagged = oci_flagged(
            create_guardrails_client(settings), settings, "I would like 1 keyboard"
        )
    except oci.exceptions.ServiceError as error:
        reporter.result("❌", f"Prompt guard: OCI service error {error.status}")
    except (OSError, TimeoutError):
        reporter.result("❌", "Prompt guard: OCI network or timeout failure")
    except (AttributeError, TypeError, ValueError) as error:
        reporter.result("❌", f"Prompt guard: unexpected {type(error).__name__}")
    else:
        if flagged:
            reporter.result(
                "❌", "Prompt guard: innocent diagnostic request was flagged"
            )
        else:
            reporter.result(
                "✅",
                "Prompt guard: OCI classifier accepted an innocent diagnostic request",
            )


def run_doctor(
    arguments: argparse.Namespace, write: Callable[[str], None] = print
) -> int:
    """Run the safe diagnostic suite.

    Args:
        arguments: Parsed command-line arguments.
        write: Output function.

    Returns:
        Command exit status.
    """
    reporter = Reporter(write)
    check_platform(reporter)
    check_python_and_conda(reporter)
    check_dependencies(reporter)
    settings = check_settings(reporter)
    if settings is not None:
        check_oci_authentication(settings, reporter)
        check_model(
            reporter=reporter,
            settings=settings,
            skip=arguments.skip_model_call or arguments.offline,
        )
        check_optional_components(settings, reporter)
        check_langfuse(settings, reporter, arguments.offline)
        check_pricing(settings, reporter)
        check_pii(settings, reporter)
        check_prompt_guard(settings, reporter, arguments.offline)
    return reporter.summary()


def parse_arguments() -> argparse.Namespace:
    """Parse command-line switches.

    Returns:
        Parsed options.
    """
    parser = argparse.ArgumentParser(description="Diagnose Responses API demo setup.")
    parser.add_argument("--skip-model-call", action="store_true")
    parser.add_argument("--offline", action="store_true")
    return parser.parse_args()


def main() -> int:
    """Run the command-line diagnostics.

    Returns:
        Diagnostic exit status.
    """
    return run_doctor(parse_arguments())


if __name__ == "__main__":
    raise SystemExit(main())
