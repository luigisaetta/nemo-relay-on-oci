"""
Author: L. Saetta (Luigi Saetta)
Last modified: 2026-09-26
License: MIT

Description:
    Diagnoses user-dependent setup for the order-fulfillment demonstration.
"""

from __future__ import annotations

import argparse
from base64 import b64encode
from dataclasses import dataclass
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import sys
from typing import Callable

import oci
from oci.exceptions import ServiceError
from langchain_core.messages import HumanMessage
import requests
from requests.exceptions import RequestException

from demos.order_fulfillment.api import configure_warning_filters
from demos.order_fulfillment.config import (
    AGENT_DIR,
    Settings,
    create_extractor,
    load_settings,
)
from demos.order_fulfillment.telemetry import (
    pii_component,
    pricing_component,
    trace_endpoints,
)

ROOT_DIR = AGENT_DIR.parent.parent
REQUIREMENTS_FILE = ROOT_DIR / "requirements.txt"
DEFAULT_PRICING_FILE = AGENT_DIR / "pricing.example.json"


@dataclass
class Reporter:
    """Collect and print safe diagnostic results.

    Attributes:
        write: Output function, replaceable by offline tests.
        errors: Count of failed checks.
        warnings: Count of advisory checks.
    """

    write: Callable[[str], None] = print
    errors: int = 0
    warnings: int = 0

    def result(self, symbol: str, message: str, action: str = "") -> None:
        """Print one diagnostic result and optional corrective action.

        Args:
            symbol: Result symbol defined by the command interface.
            message: Safe user-facing result text.
            action: Optional concrete safe corrective action.
        """
        self.write(f"{symbol} {message}")
        if symbol == "❌":
            self.errors += 1
        elif symbol == "⚠️":
            self.warnings += 1
        if action:
            self.write(f"→ {action}")

    def summary(self) -> int:
        """Print the summary and return the process exit code.

        Returns:
            One when errors occurred, otherwise zero.
        """
        self.write(f"{self.errors} errors, {self.warnings} warnings")
        return int(bool(self.errors))


def expected_packages(path: Path = REQUIREMENTS_FILE) -> dict[str, str]:
    """Read exact runtime package pins from the requirements file.

    Args:
        path: Runtime requirements file.

    Returns:
        Mapping of normalized distribution names to required versions.
    """
    packages = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        value = line.strip()
        if not value or value.startswith(("#", "-")) or "==" not in value:
            continue
        name, version = value.split("==", maxsplit=1)
        packages[name.split("[", maxsplit=1)[0].lower().replace("_", "-")] = version
    return packages


def check_platform(reporter: Reporter) -> None:
    """Report whether the documented platform is in use.

    Args:
        reporter: Result collector.
    """
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        reporter.result("✅", "Platform: macOS arm64")
        return
    reporter.result(
        "⚠️",
        "Platform: untested platform, see TODO.md",
        "Use macOS Apple Silicon for the tested setup.",
    )


def check_python_and_conda(reporter: Reporter) -> None:
    """Report Python compatibility and active Conda environment.

    Args:
        reporter: Result collector.
    """
    if sys.version_info >= (3, 11):
        reporter.result(
            "✅", f"Python: {sys.version_info.major}.{sys.version_info.minor}"
        )
    else:
        reporter.result(
            "❌", "Python: version 3.11 or newer is required", "Run scripts/setup.sh."
        )
    active_environment = os.environ.get("CONDA_DEFAULT_ENV", "")
    if active_environment and active_environment != "nemo-relay-on-oci":
        reporter.result(
            "⚠️",
            "Conda: a different environment is active",
            "Activate nemo-relay-on-oci.",
        )


def check_dependencies(reporter: Reporter) -> None:
    """Compare installed runtime distributions with required exact pins.

    Args:
        reporter: Result collector.
    """
    failures = []
    for package, expected in expected_packages().items():
        try:
            installed = metadata.version(package)
        except metadata.PackageNotFoundError:
            failures.append(f"{package} is missing")
        else:
            if installed != expected:
                failures.append(f"{package} is {installed}, expected {expected}")
    if failures:
        reporter.result(
            "❌", "Dependencies: " + "; ".join(failures), "Run scripts/setup.sh."
        )
    else:
        reporter.result("✅", "Dependencies: installed versions match requirements.txt")


def check_settings(reporter: Reporter) -> Settings | None:
    """Require and validate the agent-local environment file.

    Args:
        reporter: Result collector.

    Returns:
        Validated settings, or `None` after a safe error report.
    """
    env_file = AGENT_DIR / ".env"
    if not env_file.is_file():
        reporter.result(
            "❌",
            "Environment: .env is missing",
            "Copy .env.example to .env and configure it.",
        )
        return None
    values = {}
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", maxsplit=1)
            values[key] = value.strip().strip("'\"")
    for name, value in values.items():
        if value.startswith("replace-with"):
            reporter.result(
                "❌", f"Environment: {name} is a placeholder", f"Set {name} in .env."
            )
            return None
    try:
        settings = load_settings(env_file)
    except ValueError as error:
        details = error.errors() if hasattr(error, "errors") else []
        location = details[0].get("loc", ()) if details else ()
        field = ".".join(str(part) for part in location) or "configuration"
        reporter.result(
            "❌",
            f"Environment: invalid setting {field}",
            "Correct the named .env variable.",
        )
        return None
    reporter.result("✅", "Environment: configuration is valid")
    return settings


def check_oci_authentication(settings: Settings, reporter: Reporter) -> None:
    """Validate safe local OCI authentication prerequisites.

    Args:
        settings: Validated demo settings.
        reporter: Result collector.
    """
    if settings.auth_type == "RESOURCE_PRINCIPAL":
        reporter.result(
            "ℹ️", "OCI credentials: provided by the OCI runtime; skipped locally"
        )
        return
    config_path = Path(settings.config_file).expanduser()
    if not config_path.is_file():
        reporter.result(
            "❌",
            "OCI credentials: configuration file is missing",
            "Configure OCI_CONFIG_FILE and OCI_CONFIG_PROFILE.",
        )
        return
    try:
        config = oci.config.from_file(str(config_path), settings.config_profile)
        oci.config.validate_config(config)
    except (OSError, ValueError, KeyError):
        reporter.result(
            "❌",
            "OCI credentials: configuration or profile is invalid",
            "Check OCI_CONFIG_PROFILE and the OCI SDK configuration.",
        )
        return
    key_file = config.get("key_file", "")
    if not key_file or not Path(key_file).expanduser().is_file():
        reporter.result(
            "❌",
            "OCI credentials: private key file is not readable",
            "Mount or configure the OCI key file for this environment.",
        )
        return
    reporter.result(
        "✅", f"OCI credentials: API_KEY profile {settings.config_profile} is valid"
    )


def check_model(settings: Settings, reporter: Reporter, skip: bool) -> None:
    """Exercise the demo structured-output model path with a small request.

    Args:
        settings: Validated demo settings.
        reporter: Result collector.
        skip: Whether the external call must be skipped.
    """
    if skip:
        reporter.result("ℹ️", "OCI model call: skipped")
        return
    try:
        if settings.output_method == "function_calling":
            configure_warning_filters()
        result = create_extractor(settings).invoke(
            [HumanMessage("I would like 1 keyboard")]
        )
        raw = result.get("raw") if isinstance(result, dict) else None
        usage = getattr(raw, "usage_metadata", None)
        detail = ""
        if isinstance(usage, dict) and "total_tokens" in usage:
            detail = f" ({usage['total_tokens']} total tokens)"
        reporter.result(
            "✅", "OCI model call: structured extraction succeeded" + detail
        )
    except ServiceError as error:
        actions = {
            400: "Check OCI_STRUCTURED_OUTPUT_METHOD and try OCI_REASONING_EFFORT=NONE.",
            401: "Check IAM policy and compartment access.",
            403: "Check IAM policy and compartment access.",
            404: "Check that the model is available in the selected region.",
        }
        reporter.result(
            "❌",
            f"OCI model call: service error {error.status} ({error.code})",
            actions.get(error.status, "Review OCI configuration."),
        )
    except (RequestException, TimeoutError, OSError):
        reporter.result(
            "❌",
            "OCI model call: network or timeout failure",
            "Check region and network connectivity.",
        )


def check_langfuse(settings: Settings, reporter: Reporter, offline: bool) -> None:
    """Validate and optionally contact the configured Langfuse project.

    Args:
        settings: Validated demo settings.
        reporter: Result collector.
        offline: Whether network checks must be skipped.
    """
    values = (
        settings.langfuse_base_url.strip(),
        settings.langfuse_public_key.get_secret_value().strip(),
        settings.langfuse_secret_key.get_secret_value().strip(),
    )
    if not any(values):
        reporter.result(
            "⚠️",
            "Langfuse: traces will not be exported",
            "Configure Langfuse values; see Quickstart.md.",
        )
        return
    if "/api/public" in values[0]:
        reporter.result(
            "❌",
            "Langfuse: use only the base URL",
            "Remove /api/public from LANGFUSE_BASE_URL.",
        )
        return
    try:
        trace_endpoints(settings)
    except ValueError:
        reporter.result(
            "❌",
            "Langfuse: configuration is incomplete or conflicts with OTLP",
            "Set all Langfuse values together and clear the generic OTLP endpoint.",
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
    except RequestException:
        reporter.result(
            "❌",
            "Langfuse: network request failed",
            "Check the URL and region (EU cloud.langfuse.com; US us.cloud.langfuse.com).",
        )
        return
    if response.status_code == 200:
        data = response.json().get("data", [])
        name = (
            data[0].get("name", "configured project") if data else "configured project"
        )
        reporter.result("✅", f"Langfuse: connected to {name}")
    elif response.status_code in {401, 403}:
        reporter.result(
            "❌",
            "Langfuse: credentials are invalid for this project or region",
            "Check the project keys and region.",
        )
    else:
        reporter.result(
            "❌",
            f"Langfuse: unexpected status {response.status_code}",
            "Check the URL and region.",
        )


def check_pricing(settings: Settings, reporter: Reporter) -> None:
    """Report user-configured pricing availability without validating defaults.

    Args:
        settings: Validated demo settings.
        reporter: Result collector.
    """
    configured = settings.model_pricing_file.strip()
    if not configured:
        reporter.result(
            "⚠️",
            "Pricing: no cost estimates",
            "Set MODEL_PRICING_FILE to a pricing catalog.",
        )
        return
    path = Path(configured).expanduser()
    if path.resolve() != DEFAULT_PRICING_FILE.resolve():
        try:
            pricing_component(settings)
        except ValueError:
            reporter.result(
                "❌",
                "Pricing: custom catalog is invalid",
                "Correct MODEL_PRICING_FILE and its catalog.",
            )
            return
    try:
        entries = json.loads(path.read_text(encoding="utf-8")).get("entries", [])
    except (OSError, json.JSONDecodeError):
        reporter.result(
            "❌", "Pricing: catalog cannot be read", "Correct MODEL_PRICING_FILE."
        )
        return
    matched = any(
        entry.get("provider") == "oci"
        and settings.model_id in {entry.get("model_id"), *entry.get("aliases", [])}
        for entry in entries
    )
    if matched:
        reporter.result("✅", "Pricing: catalog includes the configured model")
    else:
        reporter.result(
            "⚠️",
            "Pricing: cost will not be shown for this model",
            "Add an OCI entry for MODEL_ID or one of its aliases.",
        )


def check_pii(settings: Settings, reporter: Reporter) -> None:
    """Report the active phone-number telemetry policy.

    Args:
        settings: Validated demo settings.
        reporter: Result collector.
    """
    pii_component(settings)
    if settings.pii_redaction == "off":
        reporter.result("ℹ️", "PII redaction: off; phone numbers remain in telemetry")
    else:
        reporter.result(
            "ℹ️",
            "PII redaction: "
            f"{settings.pii_redaction}; detected phone numbers are sanitized in telemetry",
        )


def run_doctor(
    arguments: argparse.Namespace, write: Callable[[str], None] = print
) -> int:
    """Run all safe setup checks and return the command exit code.

    Args:
        arguments: Parsed command-line options.
        write: Output function for command-line use and tests.

    Returns:
        Process exit status following the doctor contract.
    """
    reporter = Reporter(write)
    check_platform(reporter)
    check_python_and_conda(reporter)
    check_dependencies(reporter)
    settings = check_settings(reporter)
    if settings is not None:
        check_oci_authentication(settings, reporter)
        check_model(settings, reporter, arguments.skip_model_call or arguments.offline)
        check_langfuse(settings, reporter, arguments.offline)
        check_pricing(settings, reporter)
        check_pii(settings, reporter)
    return reporter.summary()


def parse_arguments() -> argparse.Namespace:
    """Parse doctor command-line options.

    Returns:
        Parsed options.
    """
    parser = argparse.ArgumentParser(description="Diagnose order-fulfillment setup.")
    parser.add_argument(
        "--skip-model-call", action="store_true", help="Skip the OCI model call."
    )
    parser.add_argument(
        "--offline", action="store_true", help="Skip OCI and Langfuse network calls."
    )
    return parser.parse_args()


def main() -> int:
    """Run the doctor command-line interface.

    Returns:
        Doctor exit status.
    """
    return run_doctor(parse_arguments())


if __name__ == "__main__":
    raise SystemExit(main())
