# Instructions for agents and contributors

These rules apply to the entire `nemo-relay-on-oci` repository.

## Purpose and technologies

This repository contains AI agent demos built with:

- NeMo Relay, the NVIDIA library;
- OCI Generative AI;
- `langchain_oci`;
- LangGraph.

Each demo must explain its purpose, integrations, and execution steps.
Do not invent APIs or compatibility claims: verify them against official
documentation and state the dependency versions used.

## Documentation language

All repository documentation must be written in English. This includes
README files, specifications, guides, instructions for agents, changelog
entries, and code documentation such as docstrings and explanatory comments.
Write new documentation in English and keep existing documentation in English
when updating it.

## Code readability and documentation

Prioritize readable, straightforward code. Do not overengineer: use the
simplest design that satisfies the specification and avoid unnecessary
abstractions. Always document modules, classes, and functions with English
Google-style docstrings, including Args, Returns, and Raises sections where
applicable. Add comments where they clarify intent, non-obvious behavior,
or important constraints; do not merely repeat the code.

Every Python source file, including tests and package initializers, must begin
with this English module header:

```python
"""
Author: L. Saetta (Luigi Saetta)
Last modified: YYYY-MM-DD
License: MIT

Description:
    Brief English description of the source file's purpose.
"""
```

Set `Last modified` to the current date whenever the file is changed. Keep the
description concise, accurate, and specific to that source file.

When adding an entry under `Unreleased` in `CHANGELOG.md`, prefix that entry
with the current date in `YYYY-MM-DD` format. Do not retroactively date
existing changelog entries unless they are being updated as part of the current
change.

## Required Conda environment

Use the Conda environment named `nemo-relay-on-oci` for all Python work,
including running demos, installing dependencies, formatting, linting,
and testing. The project requires Python 3.11 or later.

Activate it before running project commands:

```bash
conda activate nemo-relay-on-oci
```

For non-interactive shells, explicitly select the environment on each command:

```bash
conda run -n nemo-relay-on-oci python --version
conda run -n nemo-relay-on-oci python -m black .
conda run -n nemo-relay-on-oci python -m black --check .
```

Run Pylint, pytest, and package installation through the same environment's
Python (`python -m pylint`, `python -m pytest`, and `python -m pip`).
Do not fall back to Conda `base`, system Python, or another environment.
If the required environment is missing or unusable, report the blocker.

## Spec-driven approach

Each agent must have its own dedicated folder under `demos/`. Every agent
must be runnable from the repository root; document the exact startup command
without requiring users to change into the demo folder.
Keep the demo table in the root README up to date when adding or changing
a demo. Include its link, implementation status, and notes explaining the
agent's purpose and the NeMo Relay capabilities demonstrated. Clearly label
planned capabilities until they are implemented and verified.

1. Before implementing or changing behavior, create or update the matching
   specification in `specs/`.
2. Describe the objective, requirements, scope and exclusions, architecture
   and integrations, inputs/outputs, configuration, error handling, and
   verifiable acceptance criteria.
3. Define test cases from the acceptance criteria, including error paths
   and edge cases.
4. Implement the specification and maintain traceable links between the
   specification, demo, and tests.
5. When the required behavior changes, update the specification first,
   followed by implementation, tests, and documentation.

For documentation-only changes, keep the affected documents consistent;
a specification for a nonexistent feature is not required.

## Mandatory checks before every commit and completion

Before committing, releasing changes, or declaring the work done, complete
all of the following steps in the required Conda environment:

1. **Formatting:** apply Black to all Python code, including tests, and
   verify that a subsequent run in check mode passes.
2. **Static analysis:** run Pylint on all Python code, including tests, and
   fix **every** reported issue. A syntax-only check does not replace Pylint.
   The command must succeed with no unresolved findings.
3. **Tests and coverage:** prepare or update tests and run them with pytest
   and pytest-cov. All tests must pass, and overall application code coverage
   must be **at least 80%**, enforced with `--cov-fail-under=80`. Include
   application modules that tests do not import in the measurement; do not
   include tests in the coverage denominator.
4. **Documentation:** update the README and affected documentation with
   relevant behavior, configuration, prerequisites, and execution steps.
5. **Changelog:** update `CHANGELOG.md`, describing changes under `Unreleased`
   until a release is prepared.
6. **Final verification:** review the diff and report the commands executed,
   their outcomes, and the actual measured coverage percentage.

Do not lower the coverage threshold, exclude code to bypass it, disable
Pylint checks, or skip tests to make checks pass. If a check fails, fix the
cause and rerun it before committing or declaring completion. If the
environment blocks a check, report the blocker without claiming that the
requirements have been met.

While the repository contains only documentation and no Python files,
Black, Pylint, pytest, and coverage have no code to operate on: explicitly
report this condition without inventing results or creating dummy tests.
When the first Python code is introduced, configure and run all checks
above. Documentation-only changes in a repository that already contains
Python code are not exempt from these checks.

## Configuration and reproducibility

- With the first demo, introduce tool configuration and development
  dependencies, including `black`, `pylint`, `pytest`, and `pytest-cov`,
  and document the exact commands in the README.
- Configure coverage for all application directories. Example to adapt
  to the actual layout:
  `conda run -n nemo-relay-on-oci python -m pytest --cov=src --cov-report=term-missing --cov-fail-under=80`.
- Regular automated tests must be reproducible without OCI credentials,
  network access, or paid API calls: mock external services.
- Separately document prerequisites and commands for any integration
  tests that use real services.
- Never commit credentials, keys, tokens, or other secrets. Document
  configuration using examples without sensitive values.
