# Specification 005: Phone-number PII redaction in exported traces

Status: Implemented with offline verification on NeMo Relay 0.9.2; updated to
avoid UUID corruption.

## Objective

Add configurable phone-number PII redaction to the
`demos/order_fulfillment` demo's NeMo Relay 0.9.2 telemetry pipeline. Phone
numbers must remain in the request delivered to the OCI LLM and in the HTTP
response sent to the client, while being sanitized in telemetry events exported
to Langfuse.

For example, for the request `I would like 2 keyboards, call me at +39 333 123
4567`, the model receives the original request, but Langfuse receives the
configured masked or redacted form.

## UUID-safe pattern correction

Use the explicit `PHONE_NUMBER_PATTERN`
`r"\+\d[\d ().\\-]{6,}\d|\(\d{2,4}\)[ ]?\d{2,4}(?:[ ]\d{2,4}){1,3}|\b\d{2,4}(?:[ ]\d{2,4}){2,3}\b"`
instead of Relay's built-in `phone` detector. The built-in detector can mask
digit groups in UUID order IDs; the explicit pattern preserves UUIDs while
covering international, parenthesized, and space-separated phone numbers.
With `mask`, retain four digits and render `+39 333 123 4567` as
`************4567`; `redact` renders `[REDACTED]`. Dashed-only
`333-123-4567` intentionally remains unmasked because it is indistinguishable
from a UUID fragment for this safety objective.

## Scope and requirements

- Add `PII_REDACTION`, read from the agent-local `.env` file with process
  environment variables taking precedence, like the existing settings.
- Its allowed values are `mask`, `redact`, and `off`; its default is `mask`.
  An invalid value must prevent startup with a clear validation error.
- Add `Settings.pii_redaction` as a
  `Literal["mask", "redact", "off"]` setting in `config.py`.
- Add `pii_component(settings)` to `telemetry.py`, with an English Google-style
  docstring:
  - `off` returns `None`;
  - `mask` and `redact` return a `pii_redaction.ComponentSpec` built with
    `pii_redaction.PiiRedactionConfig` and
    `pii_redaction.BuiltinConfig(action=<setting>, pattern=PHONE_NUMBER_PATTERN)`;
    `mask` also sets `unmasked_suffix=4`;
  - validate the configuration with `pii_redaction.validate_config`; fail
    startup if any diagnostic has error severity.
- `relay_lifespan()` must add this component to Relay's components only when it
  is not `None`.
- Use the NeMo Relay 0.9.2 single-policy Python API. In this pinned version,
  `PiiRedactionConfig` does not expose `profiles`; do not use that field.
- Do not configure a codec. Relay 0.9.2 produces the same result with and
  without `codec="openai_chat"` for this demo.
- With the explicit phone pattern, `mask` retains the final four digits (for
  example, `+39 333 123 4567` becomes `************4567`); `redact` produces
  `[REDACTED]`.
- Update `.env.example` with `PII_REDACTION=mask` and an English comment that
  describes the three values and states that redaction affects telemetry only,
  not the model prompt.
- Update the order-fulfillment README with a **PII redaction** subsection under
  **NeMo Relay behavior**, including the phone-number `curl` example, expected
  Langfuse behavior for `order_fulfillment`, `extract_order`, and
  `build_order_response`, the unchanged LLM prompt and HTTP response, and the
  covered formats and dashed-number limitation. Email addresses and other PII
  remain visible.
- Add `PII_REDACTION` to the configuration-variable table. Update the root
  README and `Quickstart.md` with a second `curl` example. Replace statements
  claiming that traces always retain complete payloads with accurate guidance:
  phone numbers are sanitized when enabled, but synthetic data remains advised
  for all other sensitive data.
- Add an English `Unreleased` entry to `CHANGELOG.md`.

## Exclusions

- Do not add email, payment-card, or any other PII detector.
- Do not add blocking guardrails.
- Do not change graph control flow, the LLM prompt, or the HTTP response. The
  original request remains in the client-facing response.
- Do not update dependencies.
- Do not modify `nodes.py`, `api.py`, or `graph.py`.
- Do not reintroduce `NemoRelayCallbackHandler` or switch to `llm.execute`.
  Existing manual `llm.call` / `llm.call_end` lifecycles and `trace_scope`
  instrumentation remain unchanged to preserve token usage and cost telemetry.

## Architecture and integrations

The configured `pii_redaction` component installs a sanitize guardrail on
Relay events, rather than modifying real model calls. Therefore the original
request reaches `langchain_oci` and OCI unchanged, while Relay sanitizes the
events delivered to subscribers and OTLP exporters.

The explicit pattern avoids the built-in detector's UUID false positives. It
covers numbers beginning with `+`, parenthesized numbers, and space-separated
numbers without matching UUID fragments.

The guardrail covers the demo's manual Relay API usage: `llm.call`,
`llm.call_end`, and `nemo_relay.scope.push` / `pop`. In the current flow, it
sanitizes phone values that would otherwise be exported in the
`order_fulfillment` span input and output, the `extract_order` inputs
(`input.value` and `llm.input_messages.1.message.content`), and the
`build_order_response` output request.

The architecture is:

```text
HTTP request with original phone number
    -> LangGraph and OCI LLM receive original text
    -> Relay events from trace scopes and manual LLM lifecycle
    -> pii_redaction event guardrail when enabled
    -> subscribers and OTLP exporter receive sanitized events
    -> Langfuse stores sanitized telemetry
```

The component is initialized with the existing observability and optional
pricing components during the FastAPI lifespan, before requests are served.
Redaction must retain `llm.token_count.prompt`, `llm.token_count.completion`,
`llm.token_count.total`, and optional `usage.cost` attributes.

## Configuration

| Variable | Allowed values | Default | Behavior |
| --- | --- | --- | --- |
| `PII_REDACTION` | `mask`, `redact`, `off` | `mask` | Sanitizes phone numbers in Relay telemetry events only. |

`mask` preserves the final four detected digits; `redact` replaces a detected
phone number with `[REDACTED]`; `off` retains the current unmodified event
payloads. The setting affects the agent-local `.env` file and may be overridden
by the process environment.

## Error handling

- Pydantic rejects an unsupported `PII_REDACTION` value while loading settings,
  before the server begins serving requests.
- Relay configuration validation runs at startup. Error-level diagnostics from
  `pii_redaction.validate_config` fail startup with a clear, non-secret error.
- `off` intentionally does not install a PII component and leaves telemetry
  unmodified.
- Redaction is not a data-loss prevention guarantee. Data not recognized by the
  selected phone detector, including all non-phone PII, can still appear in
  telemetry. Documentation must retain the recommendation to use synthetic
  customer data.

## Acceptance criteria and offline tests

All tests use fake extractors and captured Relay subscriber events; they require
neither OCI credentials nor network access.

1. With `mask`, no serialized event contains `+39 333 123 4567`, and sanitized
   events contain `************4567`.
2. The fake extractor receives the original, unmasked phone number.
3. The HTTP response remains unchanged: it confirms the order and returns the
   original request.
4. With `redact`, serialized events contain `[REDACTED]` and not the original
   phone number.
5. With `off`, serialized events contain the original phone number.
6. With redaction and a test price catalog enabled, the completed LLM event
   retains prompt, completion, and total token counts and `usage.cost`.
7. Redaction does not alter product name, quantity, `product_id`, or UUID
   `order_id` in captured events. Test at least 1,000 random UUIDs plus the two
   reported UUID regressions using real Relay subscriber events.
8. With a full application request containing a phone number, the confirmed
   order ID is identical in root, `register_order`, and `build_order_response`
   events while the phone is masked in input and output data.
9. Verify `+39 333 123 4567`, `+393331234567`, `(333) 123 4567`, and
   `333 123 4567` as masked. Document and test `333-123-4567` as intentionally
   unmasked.
10. An invalid `PII_REDACTION` value fails settings loading with a clear error.
11. `pii_component` returns `None` for `off` and a component configured with
    the corresponding action for `mask` and `redact`.

## Offline pattern characterization

The implementation's offline subscriber tests verify that the explicit pattern
sanitizes `+39 333 123 4567`, `+393331234567`, `(333) 123 4567`, and
`333 123 4567`. `333-123-4567` is deliberately not covered to preserve UUID
order IDs. Recheck this behavior after a Relay upgrade.

## Manual verification

This verification requires real OCI and Langfuse credentials and is not part of
the offline test suite. Set `PII_REDACTION=mask`, start the demo, and submit:

```bash
curl -X POST http://127.0.0.1:8000/orders \
  -H 'Content-Type: application/json' \
  -d '{"request":"I would like 2 keyboards, call me at +39 333 123 4567"}'
```

Confirm that the order succeeds, demonstrating that the OCI LLM received the
complete request. In Langfuse, confirm that the `order_fulfillment` trace and
`extract_order` generation display `************4567`, and verify the same
sanitization on the `build_order_response` span. Also confirm that the phone
digits are not interpreted as an order quantity. If they are, report the result
without changing the extraction prompt in this work.

## Traceability

- Extends [Specification 002](002-order-fulfillment.md), which defines the
  order-fulfillment HTTP agent and its trace hierarchy.
- Preserves the token-usage and pricing lifecycle defined by
  [Specification 003](003-llm-token-usage-and-cost.md).
