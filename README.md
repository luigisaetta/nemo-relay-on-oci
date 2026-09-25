# nemo-relay-on-oci

[![Code style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://black.readthedocs.io/)
[![Lint: Pylint](https://img.shields.io/badge/lint-pylint-blue.svg)](https://pylint.readthedocs.io/)
[![Tests: pytest](https://img.shields.io/badge/tests-pytest-blue.svg)](https://docs.pytest.org/)
[![Python: 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/)

A collection of AI agent demos built with **NVIDIA NeMo Relay**,
**OCI Generative AI**, **`langchain_oci`**, and **LangGraph**.

The repository is in its initial stage: it contains development rules and
documentation, but no runnable demos or Python code yet.

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
Python work. Tool and dependency setup instructions will be added with the
first demo.

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

At this documentation-only stage, Python checks are not applicable because
there is no code. Dependencies, configuration, and exact commands for Black,
Pylint, and pytest will be introduced with the first demo. From that point
on, checks will also apply to documentation-only changes.

## Running demos and tests

Each demo will include a link to its specification, prerequisites, dependency
versions, required OCI configuration, and execution commands. Regular tests
will mock external services and will not require credentials or paid API
calls; any integration tests will have separate instructions.

Do not store credentials or secrets in the repository.
