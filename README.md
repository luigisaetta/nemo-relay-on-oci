# nemo-relay-on-oci

[![Code style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://black.readthedocs.io/)
[![Lint: Pylint](https://img.shields.io/badge/lint-pylint-blue.svg)](https://pylint.readthedocs.io/)
[![Tests: pytest](https://img.shields.io/badge/tests-pytest-blue.svg)](https://docs.pytest.org/)
[![Python: 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

A collection of AI agent demos built with **NVIDIA NeMo Relay**,
**OCI Generative AI**, **`langchain_oci`**, and **LangGraph**.

The repository contains a runnable order fulfillment demo, specifications,
pinned dependencies, and offline acceptance tests.

## Demos

This table is updated as demos are added or developed. It lists the functional
capabilities demonstrated by each demo.

| Demo | Functionality |
| --- | --- |
| [Order fulfillment](demos/order_fulfillment/README.md) | OCI LLM extraction, JSON inventory, and simulated order registration through a tool in an explicit LangGraph workflow. NeMo Relay emits one nested trace per order, including graph callbacks, LLM prompts and outputs, and tool inputs and results, exported directly to Langfuse through OTLP. |

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
Set `LANGFUSE_BASE_URL`, `LANGFUSE_PUBLIC_KEY`, and `LANGFUSE_SECRET_KEY` in
`demos/order_fulfillment/.env`. Leave them all empty to disable export. Set
Set `LANGFUSE_INGESTION_VERSION=4` for Langfuse Cloud v4 real-time ingestion.
Keep `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` empty
when using Langfuse.

The agent builds the OTLP trace URL and endpoint-specific Basic authentication
header automatically. Each order is exported as a single hierarchy with its
request/response, complete LLM prompt/message history, and tool input/output.
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

Each demo will include a link to its specification, prerequisites, dependency
versions, required OCI configuration, and execution commands. Regular tests
will mock external services and will not require credentials or paid API
calls; any integration tests will have separate instructions.

Do not store credentials or secrets in the repository.
