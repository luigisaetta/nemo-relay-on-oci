# nemo-relay-on-oci

[![Code style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://black.readthedocs.io/)
[![Lint: Pylint](https://img.shields.io/badge/lint-pylint-blue.svg)](https://pylint.readthedocs.io/)
[![Tests: pytest](https://img.shields.io/badge/tests-pytest-blue.svg)](https://docs.pytest.org/)
[![Python: 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

A collection of AI agent demos built with **NVIDIA NeMo Relay**,
**OCI Generative AI**, **`langchain_oci`**, and **LangGraph**.

The repository contains development rules, dependency manifests, and an
initial environment specification, but no runnable demos or Python code yet.

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

The intended trace pipeline is:

```text
LangGraph + ChatOCIGenAI -> NeMo Relay -> OTLP -> OpenTelemetry Collector -> backend
```

Relay includes native OTLP export, so this baseline does not require a
separate Python OpenTelemetry SDK or exporter. The collector is a separate
service. The initial transport will be OTLP HTTP/protobuf, typically using
`http://localhost:4318/v1/traces` locally. Configure the service name,
endpoint, and exporter shutdown using the pinned Relay release's schema.
In Relay 0.9.2, `OpenTelemetryEndpointConfig` exposes `endpoint`,
`service_name`, and `transport="http_binary"` for this transport.

Installing packages does not enable instrumentation or start a collector.
The first demo will wire the model and graph instrumentation, configure the
exporter, and verify trace delivery. Live OCI inference and collector delivery
are not validated by dependency installation or offline import checks.

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

At this dependency-and-documentation stage, Python code checks and coverage
are not applicable because there is no application or test code. The tools
are installed; their configuration and exact source/test targets will be
introduced with the first demo. From that point on, checks will also apply
to documentation-only changes.

## Running demos and tests

Each agent will have its own folder under `demos/` and must be runnable from
the repository root.

The first planned demo is an order fulfillment agent exposed through FastAPI
and Uvicorn, using a LangGraph workflow to extract a product and quantity,
check a JSON catalog, and simulate order registration through a tool.
See the [draft specification](specs/002-order-fulfillment.md) for confirmed
requirements, the proposed graph, and decisions to discuss before implementation.
This demo is not implemented yet.

Each demo will include a link to its specification, prerequisites, dependency
versions, required OCI configuration, and execution commands. Regular tests
will mock external services and will not require credentials or paid API
calls; any integration tests will have separate instructions.

Do not store credentials or secrets in the repository.
