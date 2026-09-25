# Changelog

Changes are recorded under `Unreleased` and assigned a version and date
when released.

## Unreleased

### Added

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

- README describing the project purpose, development workflow, quality
  requirements, and initial state without Python code.
- Translated AGENTS.md, README, and changelog into English.
