# TODO

## Platform support

- **Planned — Windows:** Provide a `setup.sh` equivalent, startup independent of
  `start.sh`, PowerShell `curl` examples, Windows-safe replacement for `cp -n`,
  and doctor tests. Evaluate a separate local container option; it must not
  modify the Enterprise AI Dockerfile.
- **Planned — Linux:** Test setup and doctor on supported Linux platforms.
- **Planned — macOS Intel:** Support remains unavailable until NeMo Relay
  publishes a macOS x86_64 wheel.

## Planned demo improvements

- **Planned — Prompt-injection guardrail:** Add a NeMo Relay guardrail for
  malicious instructions embedded in order text.
- **Planned — Demo material:** Restructure documentation with Langfuse
  screenshots and add an ACE-oriented `DEMO-SCRIPT.md`.
- **Needs maintainer environment — OCI model comparison:** Compare models and
  per-order costs after adding pricing entries for every tested model.
- **Needs maintainer environment — Enterprise AI deployment:** Complete OCI
  Enterprise AI deployment with Langfuse keys from OCI Vault; the current
  `agent.yaml` does not export traces.
