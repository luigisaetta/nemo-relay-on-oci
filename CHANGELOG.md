# Changelog

Changes are recorded under `Unreleased` and assigned a version and date
when released.

## Unreleased

### Changed

- Added standard author, last-modified, license, and English description
  headers to every Python source file. Documented the required header format
  and date-maintenance rule for contributors.
- Clarified the repository objective as developing and deploying robust,
  secure, controllable, observable agents with NeMo Relay and OCI Enterprise
  AI. Added a concise root quick start and a detailed `Quickstart.md` for
  local setup and execution of the first demo.
- Made Langfuse Cloud project credentials a prerequisite for demonstrating the
  first demo's OpenTelemetry export of agent steps, prompts, responses, token
  usage, and estimated per-invocation cost.

### Fixed

- Replace automatic LangGraph callback spans with explicit, domain-named Relay
  scopes so Langfuse traces show readable order-processing operations rather
  than framework internals.
- Export OCI extraction token usage and optional Relay-estimated model cost to
  Langfuse through a validated local pricing catalog, using Langfuse's
  `gen_ai.usage.cost` attribute for the displayed generation cost.
- Seed the local catalog for `openai.gpt-5.6-sol` with explicitly provisional
  OpenAI published rates and enable it in the demo environment templates.
- Name the manual OCI extraction generation `extract_order` rather than the
  provider-generic `oci`.
- Request JSON acknowledgements from Langfuse to avoid false Relay OTLP
  batch-export failures during shutdown.
- Export each order as one nested Langfuse trace and retain the root, LLM, and
  tool input/output payloads, including complete LLM prompt history.
- Default the Langfuse Cloud template to v4 real-time ingestion.
- Record successful direct Langfuse Cloud delivery verification in the demo
  documentation.
- Distinguish the HTTP trace root from its LangGraph child with
  `order_fulfillment` and `order_fulfillment_graph` names.
- Improved extraction instructions to remove subjective adjectives, normalize
  plurals and clear typos, and preserve meaningful product features without
  providing the catalog to the LLM.
- Suppressed only the exact GenericProvider empty-text UserWarning from the
  OCI chat-model module when starting the API in function-calling mode.
  Other warning messages, categories, and modules remain visible.
- Added optional `OCI_REASONING_EFFORT` configuration to resolve model rejection
  of function calling with active reasoning; normalize values to OCI SDK enums.
- Replaced generic service-unavailable messages for OCI rejections with an
  upstream status and configuration hint. Added sanitized server diagnostics
  and regression tests for parameter forwarding and error handling.

### Added

- OCI Enterprise AI container artifacts for order fulfillment: a non-root
  `linux/amd64` Dockerfile, a schema-v1 deployment manifest, build-context
  secret exclusions, and a readiness endpoint.

- Direct remote Langfuse export through NeMo Relay's built-in HTTP/protobuf
  exporter, with automatic trace URL and endpoint-local Basic authentication.
- Matching local/example Langfuse settings, optional v4 ingestion header,
  configuration validation, and masked credentials.
- Tests for direct-export configuration, native schema compatibility, disabled
  export, invalid settings, and environment precedence.

- Executable `demos/order_fulfillment/start.sh` for root-level server startup
  using the already active Conda environment.
- First order fulfillment implementation: five class-based LangGraph nodes,
  structured OCI LLM extraction, JSON catalog, and atomic in-memory registration tool.
- FastAPI `/orders` and `/health` endpoints with Uvicorn startup from the root.
- Agent-local configuration with API_KEY and RESOURCE_PRINCIPAL authentication.
- Relay graph callbacks, typed LLM/tool scopes, optional native OTLP export,
  and exporter lifecycle cleanup.
- Offline tests and automatic 80% minimum application coverage enforcement.
- FastAPI, Uvicorn, python-dotenv, and explicit directly imported dependencies.

- `demos/order_fulfillment/` with an English README and `.env.example` for
  OCI model, region, compartment, and authentication configuration.
- Root README demo index with links, implementation status, and notes on
  agent behavior and planned NeMo Relay capabilities; maintenance rule in AGENTS.md.
- Draft specification for the order fulfillment demo, including confirmed
  requirements, a proposed class-based LangGraph workflow, HTTP interface,
  acceptance criteria, and open implementation decisions.
- Repository rule requiring a dedicated folder per agent under `demos/`
  and startup commands runnable from the repository root.
- Dependency and observability specification with offline acceptance checks.
- Pinned runtime and development requirements and resolved constraints for
  the `nemo-relay-on-oci` Conda environment.
- LangGraph, NeMo Relay with the LangGraph extra, LangChain OCI, OCI SDK,
  and the required formatting, linting, and testing tools.
- Documented native Relay OTLP export to a separate OpenTelemetry Collector
  and the distinction between dependency checks and live integration tests.
- README badges for Black, Pylint, pytest, and Python 3.11+.
- `AGENTS.md` defining demo objectives and technologies, the spec-driven
  workflow, and mandatory checks before commits, releases, and completion.
- Requirements for Black formatting, Pylint with no unresolved findings,
  and pytest tests with at least 80% coverage through pytest-cov.
- Requirements to update documentation and the changelog and report actual
  verification results.
- Requirement to write all repository documentation in English.
- Requirement to use the `nemo-relay-on-oci` Conda environment for all Python
  work, with activation and non-interactive execution instructions.

### Changed

- Required readable code, simple designs, Google-style docstrings, and explanatory
  comments in AGENTS.md.
- Finalized first-version behavior and updated demo documentation and index.

- Confirmed the order fulfillment authentication selector, compartment setting,
  local OCI profile defaults, and process-environment precedence in the spec.
- Specified per-agent `.env` configuration with `OCI_REGION` and `MODEL_ID`,
  a derived regional inference endpoint, and support for OCI API signing keys
  and resource principals. Documented proposed supporting configuration and
  corresponding acceptance criteria without implementing the demo.
- README describing the project purpose, development workflow, quality
  requirements, and initial state without Python code.
- Translated AGENTS.md, README, and changelog into English.
