"""
Author: L. Saetta (Luigi Saetta)
Last modified: 2026-09-26
License: MIT

Description:
    Tests narrowly scoped suppression of a known OCI warning.
"""

import warnings

from fastapi.testclient import TestClient
from langchain_core.runnables import RunnableLambda

from demos.order_fulfillment.api import create_app
from demos.order_fulfillment.config import Settings

MESSAGE = (
    "GenericProvider could not extract text and returned an empty string. "
    "Ensure the selected provider matches the response payload format, "
    "otherwise content extraction will return an empty string."
)
MODULE = "langchain_oci.chat_models.oci_generative_ai"


def test_only_known_warning_is_hidden():
    """Startup hides the exact warning while preserving neighboring cases."""
    settings = Settings(region="us-chicago-1", model_id="test", compartment_id="test")
    app = create_app(settings, RunnableLambda(lambda _: {"items": []}))
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        with TestClient(app):
            cases = [
                (MESSAGE, UserWarning, MODULE),
                ("Different warning", UserWarning, MODULE),
                (MESSAGE, RuntimeWarning, MODULE),
                (MESSAGE, UserWarning, "another_module"),
                (MESSAGE + " Additional details.", UserWarning, MODULE),
                (MESSAGE, UserWarning, MODULE + ".other"),
            ]
            for message, category, module in cases:
                warnings.warn_explicit(
                    message, category, filename="provider.py", lineno=510, module=module
                )
    assert [(str(item.message), item.category) for item in captured] == [
        (message, category) for message, category, _ in cases[1:]
    ]


def test_json_mode_keeps_empty_text_warning():
    """A text-based output mode must retain the empty-text diagnostic."""
    settings = Settings(
        region="us-chicago-1",
        model_id="test",
        compartment_id="test",
        output_method="json_mode",
        prompt_guard="off",
    )
    app = create_app(settings, RunnableLambda(lambda _: {"items": []}))
    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always")
        with TestClient(app):
            warnings.warn_explicit(
                MESSAGE, UserWarning, filename="provider.py", lineno=510, module=MODULE
            )
    assert len(captured) == 1
    assert str(captured[0].message) == MESSAGE
