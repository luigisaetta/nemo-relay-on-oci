"""
Author: L. Saetta (Luigi Saetta)
Last modified: 2026-09-26
License: MIT

Description:
    Implements layered local and OCI prompt-injection detection for Relay.
"""

import logging
import re
from collections.abc import Callable

import nemo_relay
from oci.generative_ai_inference import models

from demos.order_fulfillment.config import Settings

LOGGER = logging.getLogger(__name__)
PATTERNS = (
    r"\bignore (?:(?:all|the|previous|your) )*(?:rules|instructions)\b",
    r"\bdisregard .*?(?:instructions|system prompt)\b",
    r"\byou are now\b|\bsystem prompt\b",
    r"\bignora (?:le |tutte le )?(?:regole|istruzioni)\b",
    r"\bdimentica le istruzioni\b",
)


def user_text(request: nemo_relay.LLMRequest) -> str:
    """Return concatenated user messages without scanning system instructions.

    Args:
        request: Relay representation of the outgoing chat completion.

    Returns:
        Text from messages whose role is ``user``.
    """
    messages = request.content.get("messages", [])
    return "\n".join(
        str(message.get("content", ""))
        for message in messages
        if message.get("role") == "user"
    )


def pattern_flagged(text: str) -> bool:
    """Return whether a documented deterministic injection pattern matches.

    Args:
        text: User-controlled text to inspect.

    Returns:
        Whether one of the conservative prompt-injection patterns matched.
    """
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in PATTERNS)


def oci_flagged(client: object, settings: Settings, text: str) -> bool:
    """Classify text with OCI ApplyGuardrails and the pinned version when set.

    Args:
        client: OCI Generative AI inference client.
        settings: Guardrail configuration and OCI compartment.
        text: User-controlled text to classify.

    Returns:
        Whether OCI assigned a prompt-injection score of at least one.
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
    response = client.apply_guardrails(details)
    return response.data.results.prompt_injection.score >= 1.0


def build_prompt_guard(settings: Settings, client: object | None) -> Callable:
    """Build layered Relay guardrail callback; detection is not exhaustive.

    Args:
        settings: Selected layers and safe OCI-failure behavior.
        client: Reusable OCI client, or ``None`` for pattern-only operation.

    Returns:
        Relay conditional-execution callback with a fixed safe rejection reason.
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
