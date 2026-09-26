"""
Author: L. Saetta (Luigi Saetta)
Last modified: 2026-09-26
License: MIT

Description:
    Implements layered injection detection for Responses API request input.
"""

import logging
import re
from collections.abc import Callable

import nemo_relay
from oci.generative_ai_inference import models

from demos.order_fulfillment_responses.config import Settings

LOGGER = logging.getLogger(__name__)
PATTERNS = (
    r"\bignore (?:(?:all|the|previous|your) )*(?:rules|instructions)\b",
    r"\bdisregard .*?(?:instructions|system prompt)\b",
    r"\byou are now\b|\bsystem prompt\b",
    r"\bignora (?:le |tutte le )?(?:regole|istruzioni)\b",
    r"\bdimentica le istruzioni\b",
)


def user_text(request: nemo_relay.LLMRequest) -> str:
    """Extract user text from a Responses request without reading instructions.

    Args:
        request: Relay request whose content uses the Responses API shape.

    Returns:
        Concatenated user-controlled input text.
    """
    input_value = request.content.get("input", "")
    if isinstance(input_value, str):
        return input_value
    if not isinstance(input_value, list):
        return ""
    texts: list[str] = []
    for item in input_value:
        if not isinstance(item, dict) or item.get("role") != "user":
            continue
        content = item.get("content", "")
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            texts.extend(
                str(part.get("text", ""))
                for part in content
                if isinstance(part, dict) and part.get("type") == "input_text"
            )
    return "\n".join(texts)


def pattern_flagged(text: str) -> bool:
    """Return whether a conservative documented injection pattern matches.

    Args:
        text: User-controlled text.

    Returns:
        Whether a pattern matched.
    """
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in PATTERNS)


def oci_flagged(client: object, settings: Settings, text: str) -> bool:
    """Classify input with OCI ApplyGuardrails.

    Args:
        client: OCI inference client.
        settings: Guardrail configuration.
        text: User-controlled input text.

    Returns:
        Whether OCI reports prompt-injection score at least one.
    """
    guardrails_input = models.GuardrailsTextInput()
    guardrails_input.type = "TEXT"
    guardrails_input.content = text
    configs = models.GuardrailConfigs()
    configs.prompt_injection_config = models.PromptInjectionConfiguration()
    details = models.ApplyGuardrailsDetails()
    details.input = guardrails_input
    details.guardrail_configs = configs
    details.compartment_id = settings.compartment_id
    if settings.oci_guardrail_version:
        details.guardrail_version_config = models.GuardrailVersionConfig(
            guardrail_version=settings.oci_guardrail_version
        )
    return client.apply_guardrails(details).data.results.prompt_injection.score >= 1.0


def build_prompt_guard(settings: Settings, client: object | None) -> Callable:
    """Build the managed-pipeline conditional-execution guard callback.

    Args:
        settings: Selected layers and OCI failure policy.
        client: OCI client, or none for pattern-only operation.

    Returns:
        Callback returning a fixed rejection reason or none.
    """

    def guard(request: nemo_relay.LLMRequest) -> str | None:
        text = user_text(request)
        if settings.prompt_guard in {"pattern", "combined"} and pattern_flagged(text):
            return "prompt injection detected by pattern rule"
        if settings.prompt_guard in {"oci", "combined"}:
            try:
                if client is not None and oci_flagged(client, settings, text):
                    return "prompt injection detected by OCI Guardrails"
            except Exception as error:  # pylint: disable=broad-exception-caught
                if settings.prompt_guard_on_error == "block":
                    return "OCI Guardrails unavailable"
                LOGGER.warning("OCI Guardrails unavailable: %s", type(error).__name__)
                nemo_relay.scope.event(
                    "prompt_guard.oci_unavailable",
                    data={"error_type": type(error).__name__},
                    severity=nemo_relay.LogSeverity.Warn,
                )
        return None

    return guard
