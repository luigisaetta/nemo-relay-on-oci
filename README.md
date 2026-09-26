# nemo-relay-on-oci

[![Code style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://black.readthedocs.io/)
[![Lint: Pylint](https://img.shields.io/badge/lint-pylint-blue.svg)](https://pylint.readthedocs.io/)
[![Tests: pytest](https://img.shields.io/badge/tests-pytest-blue.svg)](https://docs.pytest.org/)
[![Python: 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

A practical reference for using **NVIDIA NeMo Relay** with **OCI Enterprise AI**
and OCI Generative AI to develop and deploy robust, secure, controllable AI
agents with end-to-end observability. The demos combine NeMo Relay,
**`langchain_oci`**, and **LangGraph**.

This repository will grow as a series of demos that progressively cover the
capabilities available through the OCI and NeMo Relay integration. Each demo
documents its purpose, configuration, integrations, and root-level execution
command. The current first demo is runnable; later capabilities are added only
when implemented and verified.

The repository also includes specifications, pinned dependencies, and offline
acceptance tests.

Deferred platform support and future demo work are tracked in [TODO.md](TODO.md).

## Quick start

The first demo shows how NeMo Relay traces an agent workflow and exports its
observability data to Langfuse through OpenTelemetry. It records:

- LLM prompts and responses.
- Agent and tool steps in a nested trace.
- Input, output, and total token counts when OCI returns usage metadata.
- An estimated cost for each LLM invocation when the local pricing catalog is
  configured.

Before running it:

- Create a Langfuse Cloud account and project, then obtain its public and
  secret API keys. A free Cloud plan is available.
- Configure the Langfuse URL and both keys, together with OCI credentials and
  model settings, in the demo `.env` file.
- Create or activate the required Conda environment and install the development
  dependencies.
- Start the service from the repository root.

```bash
conda activate nemo-relay-on-oci
python -m pip install -r requirements-dev.txt
cp -n demos/order_fulfillment/.env.example demos/order_fulfillment/.env
./demos/order_fulfillment/start.sh
```

The `.env` must contain `LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY`, and
`LANGFUSE_SECRET_KEY` to demonstrate the trace export. The service can start
without them, but no observability data is sent and the demo's main outcome is
missing. The complete environment setup, Langfuse and OCI prerequisites,
configuration reference, launch, and verification steps are in
[Quickstart.md](Quickstart.md).

## Demos

This table is updated as demos are added or developed. It lists the functional
capabilities demonstrated by each demo.

| Demo | Functionality |
| --- | --- |
| [Order fulfillment](demos/order_fulfillment/README.md) | **Implemented.** Demonstrates:<ul><li>OCI LLM extraction, JSON inventory, and simulated order registration in an explicit LangGraph workflow.</li><li>NeMo Relay tracing of named agent steps, prompts, responses, token usage, and estimated per-invocation cost.</li><li>Configurable phone-number PII redaction in exported Relay telemetry, without changing the OCI prompt or HTTP response.</li><li>Layered local and OCI prompt-injection guardrails before model invocation.</li><li>Direct OpenTelemetry export of those traces to Langfuse.</li><li>A `linux/amd64` Dockerfile and OCI Enterprise AI-compatible manifest.</li></ul> |
| [Order fulfillment — Responses API](demos/order_fulfillment_responses/README.md) | **Implemented; live IAM verification pending.** Independent copy of the order workflow using the official OpenAI SDK against OCI Responses API, `oci-genai-auth`, and Relay-managed `llm.execute` with native token, pricing, PII-redaction, and guardrail behavior. |

## Development environment

Use Python **3.11 or later** in the Conda environment **`nemo-relay-on-oci`**
for all Python commands, dependency installation, demos, and quality checks.

```bash
conda activate nemo-relay-on-oci
python --version
```

In non-interactive shells, select the environment explicitly:

```bash
conda run -n nemo-relay-on-oci python --version
```

Do not use Conda `base`, system Python, or another environment for project
Python work. Install the runtime and development dependencies with:

```bash
conda run -n nemo-relay-on-oci python -m pip install -r requirements-dev.txt
conda run -n nemo-relay-on-oci python -m pip check
```

For runtime dependencies only, install `requirements.txt` instead.
Both use [constraints.txt](constraints.txt) to pin resolved dependencies.
The initial resolution targets macOS ARM64 with Python 3.11.0; installation
on other platforms or Python versions must be verified separately.

| Dependency | Version | Purpose |
| --- | --- | --- |
| `nemo-relay[langgraph]` | 0.9.2 | Relay runtime, framework instrumentation, and native OTLP export |
| `langgraph` | 1.2.12 | Agent workflow orchestration |
| `langchain-oci` | 0.3.2 | OCI Generative AI models through `ChatOCIGenAI` |
| `oci` | 2.187.0 | OCI SDK and authentication |
| `openai` / `oci-genai-auth` | 3.19.2 / 1.1.1 | OCI OpenAI-compatible Responses API client and IAM HTTPX authentication |
| `black` | 26.5.1 | Formatting |
| `pylint` | 4.0.9 | Static analysis |
| `fastapi` / `uvicorn` | 0.141.1 / 0.54.0 | HTTP API and server |
| `python-dotenv` | 1.2.3 | Agent-local configuration |
| `pytest` / `pytest-cov` | 9.1.1 / 7.1.0 | Tests and coverage |

The published Relay 0.9.2 extras do not include `oci`: the planned OCI
integration uses Relay's LangChain instrumentation with `langchain_oci`.
See [specification 001](specs/001-dependencies-and-observability.md) for
requirements, acceptance criteria, and upstream sources.

An offline import check (no OCI client or collector connection) is:

```bash
conda run -n nemo-relay-on-oci python -c 'from langgraph.graph import StateGraph; from langchain_oci import ChatOCIGenAI; from nemo_relay.integrations.langgraph import NemoRelayCallbackHandler; from nemo_relay.observability import OpenTelemetryEndpointConfig; import oci; print("Imports OK")'
```

## Observability

The trace pipeline uses the exporter built into NeMo Relay:

```text
LangGraph + ChatOCIGenAI -> NeMo Relay native OTLP exporter -> remote Langfuse
```

No separate collector process, Docker container, or Langfuse SDK is required.
To run the first demo as intended:

- Create a Langfuse Cloud project and use its public and secret API keys.
- Set `LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY`, and `LANGFUSE_SECRET_KEY` in
  `demos/order_fulfillment/.env`.
- Set `LANGFUSE_INGESTION_VERSION=4` for Langfuse Cloud v4 real-time ingestion.
- Keep `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` empty when using Langfuse.
- Set `PII_REDACTION` to `mask` (default), `redact`, or `off` to control
  phone-number sanitization in telemetry.

The agent builds the OTLP trace URL and endpoint-specific Basic authentication
header automatically. Each order is exported as a single hierarchy with its
request/response, LLM prompt/message history, and tool input/output. When
enabled, Relay sanitizes recognized phone numbers in exported telemetry only;
the OCI prompt and client-facing HTTP response remain unchanged.
The UUID-safe policy masks international, parenthesized, and space-separated
phone numbers, but deliberately leaves dashed-only `333-123-4567` unchanged to
avoid corrupting UUID order IDs in traces.
The extraction generation exports OCI token usage and uses the configured Relay
pricing catalog to calculate an estimated cost per invocation; see the demo
README for catalog and manual-verification instructions.
See the [demo setup](demos/order_fulfillment/README.md) for data-handling
considerations. Native exporter configuration and remote Langfuse delivery have
been exercised with configured project credentials.

## Spec-driven development

Each demo starts with a specification in `specs/`, written before the code.
The specification describes the objective, requirements, architecture,
integrations, inputs/outputs, configuration, expected errors, and acceptance
criteria. Tests verify these criteria; implementation and documentation
follow the specification and are updated together when behavior changes.

All repository documentation must be written in **English**, including
specifications, guides, changelog entries, and code documentation.
The binding rules for agents and contributors are in [AGENTS.md](AGENTS.md).

## Requirements before every commit and completion

Run Python checks in the required Conda environment:

- Apply **Black** to all Python code, including tests, and verify formatting.
- Run **Pylint** on Python code and fix **every** reported issue.
- Prepare and run tests with **pytest** and **pytest-cov**: all tests must
  pass, with application code coverage of **at least 80%**, enforced with
  `--cov-fail-under=80`.
- Update affected documentation and the [changelog](CHANGELOG.md).
- Review the diff and report actual check results and coverage.

These steps are mandatory before a commit, release, or declaration that the
work is done. Do not bypass failures by disabling checks or lowering the
coverage threshold.

Run all checks from the repository root:

```bash
conda run -n nemo-relay-on-oci python -m black demos tests
conda run -n nemo-relay-on-oci python -m black --check demos tests
conda run -n nemo-relay-on-oci python -m pylint --persistent=no demos tests
conda run -n nemo-relay-on-oci python -m pytest
conda run -n nemo-relay-on-oci python -m pip check
```

`pyproject.toml` includes all application modules under `demos/` in coverage
and enforces the 80% minimum. Tests substitute the LLM and cloud services.

## Running demos and tests

Each agent has its own folder under `demos/` and starts from the repository
root. See the [order fulfillment README](demos/order_fulfillment/README.md)
for configuration, sample requests, and limitations.

```bash
./demos/order_fulfillment/start.sh
```

Activate `nemo-relay-on-oci` in your shell before running this command.
The script uses the active environment's Python and starts the server on
`127.0.0.1:8000`.

Each agent loads configuration from a `.env` file in its own folder.
For order fulfillment, `OCI_REGION` and `MODEL_ID` select the region and model;
the code derives the OCI inference endpoint from the region. Authentication
supports the local user's OCI API signing key (`API_KEY`) and
`RESOURCE_PRINCIPAL`. The specification describes confirmed supporting
variables for the compartment, authentication selector, and local profile.
Start with the demo's [.env.example](demos/order_fulfillment/.env.example);
its [README](demos/order_fulfillment/README.md) explains configuration setup.
Real `.env` files must remain untracked; private keys stay in the local OCI
configuration or credentials are supplied by the OCI resource principal runtime.

Each demo will include:

- A link to its specification.
- Prerequisites, dependency versions, required OCI configuration, and execution
  commands.
- Regular tests that mock external services and require neither credentials nor
  paid API calls.
- Separate instructions for integration tests.

Do not store credentials or secrets in the repository.
