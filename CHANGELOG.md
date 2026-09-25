# Changelog

Changes are recorded under `Unreleased` and assigned a version and date
when released.

## Unreleased

### Added

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

- Confirmed the order fulfillment authentication selector, compartment setting,
  local OCI profile defaults, and process-environment precedence in the spec.
- Specified per-agent `.env` configuration with `OCI_REGION` and `MODEL_ID`,
  a derived regional inference endpoint, and support for OCI API signing keys
  and resource principals. Documented proposed supporting configuration and
  corresponding acceptance criteria without implementing the demo.
- README describing the project purpose, development workflow, quality
  requirements, and initial state without Python code.
- Translated AGENTS.md, README, and changelog into English.
