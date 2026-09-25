# Specification 003: LLM token usage and estimated cost

## Objective

Export the OCI extraction call's token usage and optional Relay-estimated cost
to Langfuse for the `demos/order_fulfillment` demo, using the pinned NeMo Relay
0.9.2 runtime.

## Requirements

- Configure the OCI structured-output runnable with `include_raw=True`.
- Read `input_tokens`, `output_tokens`, and `total_tokens` from the returned
  raw `AIMessage.usage_metadata` when it is present.
- Replace the generic extraction LLM scope with one manual Relay LLM lifecycle
  named `extract_order`. Its request uses OpenAI Chat-compatible messages and its end
  response uses `OpenAIChatCodec` with model and token usage data.
- Keep the extractor injectable and pass the configured model ID explicitly to
  the extraction node.
- Treat a non-null `parsing_error`, a null `parsed` value, or invalid parsed
  data as `invalid_request`, without changing the HTTP contract.
- Add optional `MODEL_PRICING_FILE`. When set, load it through Relay's pricing
  file source; when unset, export token usage without estimated cost.
- Reject a missing, unreadable, malformed, or Relay-invalid pricing catalog at
  startup with a clear error that contains no credentials.
- Keep OpenInference projection and preserve one LLM span per extraction.
- Map Relay's USD OpenInference cost attribute to `gen_ai.usage.cost` so
  Langfuse records the estimated cost on the generation.
- Request an OTLP JSON response from Langfuse with `Accept: application/json`.
  This avoids the Relay 0.9.2 HTTP/protobuf exporter treating Langfuse's JSON
  acknowledgement as a failed batch during shutdown.

## Exclusions

- No managed `llm.execute` lifecycle, streaming, guardrails, PII redaction,
  dependency upgrade, graph-flow change, or HTTP response change.
- The bundled price is an OpenAI published-rate estimate for the configured
  model, not an OCI invoice rate. It must be reviewed when OCI billing or the
  model route changes.

## Architecture and integrations

`ExtractRequestNode` converts LangChain messages to OpenAI Chat message
objects, opens `nemo_relay.llm.call("extract_order", ...)`, invokes the injected
extractor, and always calls `call_end`. A successful end response uses the
validated order JSON and optional OCI usage metadata. An invocation exception
requests `otel.status_code=ERROR` and records `error.type` before it
propagates to the existing API error handler. Relay 0.9.2 normalizes the
exported OpenTelemetry status to `OK` at `call_end`; `error.type` is the
reliable exported error marker for this pinned version.

`relay_lifespan` continues to activate OpenInference OTLP observability. If
`MODEL_PRICING_FILE` is configured, it also activates Relay's pricing component
with a `FileSource`. Relay resolves the configured model ID against the OCI
catalog, then attaches estimated cost to the LLM response annotation.

The OpenInference projection exports this USD estimate as `llm.cost.total`.
The endpoint aliases that attribute to `gen_ai.usage.cost`, the OpenTelemetry
attribute Langfuse recognizes as an ingested total generation cost.

Langfuse supports OTLP HTTP/JSON and HTTP/protobuf. The Relay endpoint sends
protobuf request bodies but requests a JSON acknowledgement explicitly. This
is required for the pinned Relay exporter to close a successful batch without
misclassifying Langfuse's JSON acknowledgement as an internal failure.

## Configuration

- `MODEL_PRICING_FILE` is optional and points to a Relay pricing-catalog JSON
  file. Relative paths are resolved from the process working directory.
- `demos/order_fulfillment/pricing.example.json` is a structurally valid
  initial catalog for `openai.gpt-5.6-sol`. It uses OpenAI published token
  rates as an explicit provisional estimate because the demo invokes that
  model through OCI. Users must replace these values with their applicable OCI
  billing rates and update `pricing_as_of` and `pricing_source`.
- The catalog entry uses `provider: "oci"`, `currency: "USD"`,
  `unit: "per_token"`, explicit input/output/cache per-million-token rates,
  and `prompt_cache.read_accounting: "separate"`.

## Error handling

- Missing usage metadata does not fail extraction and produces an LLM span
  without token usage or cost.
- Parsing failures return `invalid_request` and close the LLM span normally.
- Extractor exceptions close the LLM span with requested error metadata and
  preserve the API's existing sanitized HTTP 502 behavior. With Relay 0.9.2,
  the emitted span can still have OpenTelemetry status `OK`; `error.type`
  identifies the failure.
- Invalid pricing configuration prevents startup before serving requests.

## Acceptance criteria and tests

Offline tests, with no OCI credentials, network, or paid calls, must verify:

1. A fake raw `AIMessage` with usage metadata produces one completed LLM event
   with matching prompt, completion, and total token counts.
2. A test pricing file with input rate 1.0 and output rate 2.0 USD per million
   tokens produces cost `0.002` for 1,000 input and 500 output tokens, with
   pricing provider `oci`.
3. With no pricing file, token usage is exported but cost is absent.
4. Missing usage metadata succeeds without token usage.
5. A parsing error produces `invalid_request` and closes the LLM span.
6. An extractor exception closes the LLM span, exports its `error.type`, and
   preserves HTTP 502 behavior.
7. Each extraction produces exactly one LLM span.
8. Missing or invalid pricing files fail startup clearly.
9. The Langfuse endpoint configuration aliases `llm.cost.total` to
   `gen_ai.usage.cost`.
10. The bundled pricing catalog validates and has documented provisional rates
    for the configured model.
11. The Langfuse endpoint requests an OTLP JSON response.

## Manual verification

With real OCI and Langfuse credentials, submit a synthetic order and inspect
the extraction generation for prompt, completion, and total token counts. Then
inspect the Relay-estimated cost. If Langfuse does not surface that field,
configure the model's price in Langfuse Models so it can calculate cost from
the exported token counts. This repository documents manual verification steps
but does not claim the cost display is verified until a real configured catalog
has been exercised.
