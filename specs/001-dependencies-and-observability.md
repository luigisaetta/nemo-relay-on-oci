# Specification 001: Dependencies and observability baseline

## Objective

Prepare the `nemo-relay-on-oci` Conda environment for Python 3.11+ demos
using LangGraph, NVIDIA NeMo Relay, and OCI Generative AI through
`langchain_oci`, with traces exported to an OpenTelemetry Collector.

## Scope and requirements

- Install only into the existing `nemo-relay-on-oci` Conda environment.
- Record exact direct runtime and development dependencies in separate
  requirements files. Record the resolved dependency versions as constraints.
- Use the published `nemo-relay[langgraph]` integration and `langchain-oci`.
  Relay 0.9.2 does not publish an `oci` extra. OCI integration is composed
  through LangChain; a dedicated Relay OCI adapter is not assumed.
- Use Relay's built-in OTLP exporter for Relay events. No separate Python
  OpenTelemetry SDK or exporter is required for this path. Revisit this
  decision if a future demo requires custom Python OpenTelemetry spans.
- Install Black, Pylint, pytest, and pytest-cov for the mandatory checks.
- Do not call OCI, require credentials, or start a collector during setup.

## Architecture and configuration

Intended model path: LangGraph -> Relay LangChain instrumentation ->
`langchain_oci.ChatOCIGenAI` -> OCI Generative AI.

Intended trace path: Relay scopes and call events -> built-in OTLP exporter
-> OpenTelemetry Collector -> a backend selected later.

The collector runs as a separate service, not a Python package in Conda.
Use OTLP HTTP/protobuf for the initial configuration, with the collector's
trace endpoint (typically `http://localhost:4318/v1/traces` for local use).
The first demo must define a service name, configure export before creating
Relay scopes, and flush queued traces during shutdown. Use the configuration
schema shipped with the pinned Relay version rather than assuming that the
latest development documentation applies unchanged.

OCI endpoint, model ID, compartment, and authentication profile belong in
runtime configuration. Keep credentials and collector authentication secrets
out of version control. Collector deployment and a live OCI demo are outside
this dependency baseline.

## Inputs, outputs, and failures

Inputs: the named Conda environment and public package metadata.
Outputs: pinned requirements, resolved constraints, setup documentation,
and an installed environment with consistent dependency metadata.

Missing environments, dependency conflicts, incompatible native wheels,
or failing integration imports block successful setup. Report the cause;
do not switch environments or bypass dependency resolution.

## Acceptance criteria and validation

1. The selected environment runs Python 3.11 or newer.
2. Installation from the development requirements succeeds and `pip check`
   reports no broken requirements.
3. Offline smoke checks import LangGraph, Relay's LangChain/LangGraph
   integration, `ChatOCIGenAI`, and the OCI SDK without creating cloud clients.
4. Inspect the installed Relay package to confirm the observability surface
   used by subsequent demos; distinguish installation from live integration
   validation in the report.
5. All direct and resolved package versions are recorded. The initial
   resolution is validated on macOS ARM64 / Python 3.11; other platforms
   require their own installation checks.
6. README and changelog describe setup, tracing architecture, and limitations.

This change adds dependency manifests and documentation, not application
Python code. Application test coverage is not yet measurable. The first
implementation must add meaningful pytest tests and enforce at least 80%
application coverage, as required by AGENTS.md. End-to-end OCI calls and
collector delivery remain acceptance criteria for that future demo.

## Baseline validation results

- Installation from `requirements-dev.txt` succeeded in the named Conda
  environment using Python 3.11.0 on macOS ARM64.
- `python -m pip check` reported no broken requirements.
- Offline imports of LangGraph, `ChatOCIGenAI`, OCI SDK, and Relay's
  LangChain/LangGraph integrations succeeded.
- Installed Relay source exposes `NemoRelayCallbackHandler` and
  `NemoRelayMiddleware`, plus `OpenTelemetryEndpointConfig` with `endpoint`,
  `service_name`, and `transport="http_binary"` fields.
- No cloud inference or collector delivery was attempted.

## Sources

- [NVIDIA Relay installation](https://docs.nvidia.com/nemo/relay/getting-started/installation)
- [NVIDIA Relay OpenTelemetry configuration](https://docs.nvidia.com/nemo/relay/configure-plugins/observability/opentelemetry)
- [NeMo Relay 0.9.2 package metadata](https://pypi.org/project/nemo-relay/0.9.2/)
- [LangChain OCI package and examples](https://pypi.org/project/langchain-oci/0.3.2/)

Published package metadata and installed source take precedence over newer
web documentation when determining the capabilities of the pinned release.
