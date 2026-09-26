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

- **Planned — OCI Enterprise AI deployment for order_fulfillment_responses:**
  Add a Dockerfile and `agent.yaml` after the separate deployment design work.
- **Planned — Responses API streaming:** Add streaming through
  `llm.stream_execute` to the Responses API demo.
- **Needs maintainer environment — Responses resource principal:** Verify
  `RESOURCE_PRINCIPAL` authentication for the Responses client.

- **Needs maintainer review — OCI guardrail version:** Re-evaluate the pinned
  `OCI_GUARDRAIL_VERSION` against OCI service changes and known bypasses.
- **Planned — Relay LLM error-status export:** Investigate why selected LLM
  failures may not be exported with the expected error status.
- **Planned — Demo material:** Restructure documentation with Langfuse
  screenshots and add an ACE-oriented `DEMO-SCRIPT.md`.
- **Needs maintainer environment — OCI model comparison:** Compare models and
  per-order costs after adding pricing entries for every tested model.
- **Needs maintainer environment — Enterprise AI deployment:** Complete OCI
  Enterprise AI deployment with Langfuse keys from OCI Vault; the current
  `agent.yaml` does not export traces.
