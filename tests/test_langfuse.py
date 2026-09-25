"""Direct Langfuse export configuration tests without remote connections."""

from base64 import b64decode
from unittest.mock import patch

import pytest
from nemo_relay import plugin
from pydantic import ValidationError

from demos.order_fulfillment.config import Settings, load_settings
from demos.order_fulfillment.telemetry import trace_endpoints


def settings_for_langfuse(**overrides) -> Settings:
    """Create settings with synthetic project credentials.

    Args:
        **overrides: Individual settings to replace for a test.

    Returns:
        Settings that never refer to a real Langfuse instance.
    """
    values = {
        "region": "us-chicago-1",
        "model_id": "test",
        "compartment_id": "test",
        "langfuse_base_url": "https://langfuse.example.com/",
        "langfuse_public_key": "pk-test",
        "langfuse_secret_key": "sk-test",
    }
    return Settings(**(values | overrides))


@pytest.mark.parametrize("version", ["", "4"])
def test_direct_langfuse_endpoint(version):
    """Check path, Basic auth, optional ingestion header, and native schema.

    Args:
        version: Requested Langfuse ingestion version.
    """
    settings = settings_for_langfuse(langfuse_ingestion_version=version)
    endpoints = trace_endpoints(settings)
    assert len(endpoints) == 1
    endpoint = endpoints[0]
    assert endpoint.endpoint == "https://langfuse.example.com/api/public/otel/v1/traces"
    assert endpoint.type == "openinference"
    assert endpoint.transport == "http_binary"
    scheme, token = endpoint.headers["Authorization"].split()
    assert scheme == "Basic"
    assert b64decode(token).decode() == "pk-test:sk-test"
    assert endpoint.headers.get("x-langfuse-ingestion-version", "") == version
    assert "sk-test" not in repr(settings)
    assert "pk-test" not in repr(settings)
    configuration = {
        "version": 1,
        "components": [
            {
                "kind": "observability",
                "config": {
                    "version": 4,
                    "opentelemetry": {
                        "enabled": True,
                        "endpoints": [endpoint.to_dict()],
                    },
                },
            }
        ],
    }
    report = plugin.validate_exact(configuration)
    assert not [
        item for item in report["config"]["diagnostics"] if item["level"] == "error"
    ]


@pytest.mark.parametrize(
    "overrides",
    [
        {"langfuse_base_url": ""},
        {"langfuse_public_key": ""},
        {"langfuse_secret_key": " "},
        {"traces_endpoint": "http://localhost:4318/v1/traces"},
        {"langfuse_base_url": "file:///tmp/collector"},
        {"langfuse_base_url": "https://user:password@example.com"},
        {"langfuse_base_url": "https://example.com?key=secret"},
        {"langfuse_base_url": "https://example.com#fragment"},
    ],
)
def test_invalid_langfuse_configuration(overrides):
    """Reject partial or conflicting settings without exposing credentials.

    Args:
        overrides: Invalid configuration changes.
    """
    with pytest.raises(ValueError) as failure:
        trace_endpoints(settings_for_langfuse(**overrides))
    assert "sk-test" not in str(failure.value)
    assert "password" not in str(failure.value)


def test_disabled_langfuse():
    """Empty connection values leave export disabled."""
    settings = settings_for_langfuse(
        langfuse_base_url="", langfuse_public_key="", langfuse_secret_key=""
    )
    assert not trace_endpoints(settings)


def test_langfuse_dotenv_and_precedence(tmp_path):
    """Load project keys from the agent file and honor process overrides.

    Args:
        tmp_path: Temporary configuration directory.
    """
    path = tmp_path / ".env"
    path.write_text(
        "OCI_REGION=us-chicago-1\nMODEL_ID=test\nOCI_COMPARTMENT_ID=test\n"
        "LANGFUSE_BASE_URL=https://file.example.com\nLANGFUSE_PUBLIC_KEY=pk-test\n"
        "LANGFUSE_SECRET_KEY=sk-test\nLANGFUSE_INGESTION_VERSION=4\n"
    )
    with patch.dict(
        "os.environ", {"LANGFUSE_BASE_URL": "https://process.example.com"}, clear=True
    ):
        endpoint = trace_endpoints(load_settings(path))[0]
    assert endpoint.endpoint.startswith("https://process.example.com/")
    assert endpoint.headers["x-langfuse-ingestion-version"] == "4"
    with pytest.raises(ValidationError):
        settings_for_langfuse(langfuse_ingestion_version="5")
