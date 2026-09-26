"""
Author: L. Saetta (Luigi Saetta)
Last modified: 2026-09-26
License: MIT

Description:
    Provides offline defaults for tests that activate the Relay application.
"""

from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def disable_oci_guardrails_for_existing_offline_tests(monkeypatch):
    """Prevent application tests from making OCI calls through the default guard.

    Args:
        monkeypatch: Pytest fixture used to replace the startup client factory.

    Yields:
        None.
    """

    def client(_settings):
        """Return an offline OCI response that permits an ordinary request."""
        return SimpleNamespace(
            apply_guardrails=lambda _details: SimpleNamespace(
                data=SimpleNamespace(
                    results=SimpleNamespace(prompt_injection=SimpleNamespace(score=0.0))
                )
            )
        )

    monkeypatch.setattr(
        "demos.order_fulfillment.telemetry.create_guardrails_client", client
    )
