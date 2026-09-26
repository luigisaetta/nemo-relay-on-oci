# Specification 008: Order fulfillment through OCI Responses API

Status: Implemented offline; live OCI/IAM verification remains pending with the
maintainer's credentials.

Related specifications: [Specification 001](001-dependencies-and-observability.md)
defines shared dependencies and observability; [Specifications 003](003-llm-token-usage-and-cost.md),
[005](005-pii-redaction.md), [006](006-setup-and-doctor.md), and
[007](007-prompt-guardrail.md) define the shared telemetry, PII, diagnostics,
and guardrail requirements. This demo is intentionally independent of
[Specification 002](002-order-fulfillment.md).

## Objective

Build `demos/order_fulfillment_responses/`, a second order-fulfillment demo
with the same business behavior and HTTP API as `demos/order_fulfillment`.
It extracts an order with an LLM, matches a simulated catalog, checks stock,
and simulates order registration. Unlike the first demo, it invokes OCI's
Responses API through the official OpenAI SDK and `oci-genai-auth`, rather
than `langchain_oci.ChatOCIGenAI`.

The LLM request must pass through NeMo Relay's managed
`nemo_relay.llm.execute` pipeline with `OpenAIResponsesCodec`. This makes
tokens, pricing, PII redaction, and conditional execution guardrails native
Relay behaviors.

## Review corrections (2026-09-26)

- The Responses variant's `EXTRACTION_PROMPT` must be byte-for-byte identical
  to the prompt in demo 002, except that it omits only demo 002's final
  schema-interpolation line. A source-text test, which does not import demo
  002, enforces this deliberate alignment without weakening package
  independence.
- The managed Relay call is named `extract_order`, matching demo 002's LLM
  span. There is no enclosing `extract_order` agent scope and the raw Responses
  payload is not saved as an agent-scope output. Pricing remains provider `oci`
  and must be tested with the local pricing catalog.
- The complete demo-002 test coverage is mirrored and adapted for a mocked
  OpenAI Responses client. It covers every HTTP business branch, inventory
  concurrency, real Relay fail-open warning events, PII modes, telemetry,
  configuration, guardrail cleanup, and doctor checks. The Responses package
  itself must maintain at least 80% coverage.
- Pylint R0801 is the only disabled check because independent full copies are a
  maintainer-approved repository design. All other Pylint findings remain
  mandatory fixes.
- OCI Guardrails 1.1.3 has a verified Italian false positive for imperative
  `chiamami al <number>` phrasing. Documentation must recommend `il mio numero
  è <number>` in Italian presentations; no guardrail code change is allowed.

## Observability correction: complete response projection

The root HTTP scope and `build_order_response` scope export their result as
`{"response": <serialized OrderResponse>}`. A bare response object has a
top-level `message`, which Relay's OpenInference projection presents to
Langfuse as text-only output. The wrapper retains the whole response JSON in
Langfuse while leaving the HTTP API unchanged. Subscriber tests verify root
`output.response.status` and `output.response.order_id`.

## Scope and exclusions

- The new demo is a complete, deliberately duplicated copy of the first demo;
  future changes in either package must not affect the other.
- Neither package may import from the other. Tests must inspect imports (for
  example with `ast`) to enforce this rule.
- Do not change `demos/order_fulfillment` or its tests, except for the shared
  `tests/conftest.py` when essential to add a new test fixture.
- Do not add a Dockerfile or `agent.yaml` for this demo. OCI Enterprise AI
  deployment is separate work.
- The demos use port 8000 and must not run concurrently.
- They may export at different times to the same Langfuse project, but their
  root trace and service names must differ.
- Streaming, API-key authentication, and live OCI calls in ordinary tests are
  excluded.

## Dependencies and verified integration facts

Add pinned, compatible `openai` and `oci-genai-auth` versions to both
`requirements.txt` and `constraints.txt`, and run `pip check`. Update the
dependency table in Specification 001 and the root README. The shared
requirements mean the first demo's environment receives these packages even
though it does not use them.

The reviewer verified the following against `openai 3.19.2`,
`oci-genai-auth 1.1.1`, `nemo-relay 0.9.2`, model `openai.gpt-5.6-sol`, and
regions `eu-frankfurt-1` and `us-chicago-1`:

- OCI requires both `opc-compartment-id` and `CompartmentId` request headers.
- The endpoint is
  `https://inference.generativeai.<region>.oci.oraclecloud.com/openai/v1`.
- `responses.create` supports strict `json_schema` output; its output text is
  validated by `ExtractedOrder.model_validate_json`.
- Relay invocation uses provider name `oci`, `LLMRequest` containing only JSON,
  `OpenAIResponsesCodec` for both codecs, and a callback that returns
  `client.responses.create(**req.content).model_dump(mode="json")`.
- This pipeline reports input, output, and total tokens; supports OCI pricing;
  redacts phone numbers in exported request and model-output telemetry while
  preserving the original text passed to the model; and rejects guardrailed
  requests before calling the model.

Do not use `openai.lib._pydantic.to_strict_json_schema`, because it is an
internal API.

## Architecture and package contents

Create `demos/order_fulfillment_responses/` with independent `api`, `config`,
`graph`, `inventory`, `models`, `nodes`, `telemetry`, `prompt_guard`, and
`doctor` modules, plus `catalog.json`, `pricing.example.json`, `.env.example`,
`start.sh`, and `README.md`. Update all copied module headers and docstrings
to identify this Responses API demo. Retain the first demo's child Relay scope
names: `extract_order`, `match_catalog_product`,
`check_inventory_availability`, `register_order`, and `build_order_response`.

| Concern | Demo 002: order fulfillment | Demo 008: Responses API variant |
| --- | --- | --- |
| Client library | `langchain_oci` | Official `openai` SDK |
| OCI API | Chat/Generative AI path | OCI OpenAI-compatible Responses API |
| Authentication | OCI SDK through `ChatOCIGenAI` | `oci-genai-auth` HTTPX authentication |
| Relay LLM integration | Manual `llm.call` | Managed `llm.execute` with `OpenAIResponsesCodec` |
| Guardrail execution | Conditional-execution implementation | Native managed-pipeline execution |
| Root trace scope | `order_fulfillment` | `order_fulfillment_responses` |
| Default OTEL service name | `order-fulfillment` | `order-fulfillment-responses` |

## Configuration and authentication

Retain the first demo's region, model, compartment, Langfuse/OTLP, pricing,
PII, and prompt-guard configuration. Remove `OCI_STRUCTURED_OUTPUT_METHOD`:
the Responses API always uses `json_schema`. `OCI_REASONING_EFFORT` is
optional; omit it when blank, otherwise pass
`reasoning={"effort": <lowercase value>}`. The chosen value must be verified
for the selected model.

`OTEL_SERVICE_NAME` defaults to `order-fulfillment-responses` and applies to
every exported span. `create_responses_client(settings)` creates `OpenAI` with
the OCI base URL, `api_key="not-used"`, the two required compartment headers,
and a reasonable-timeout `httpx.Client`:

- `API_KEY` uses `OciUserPrincipalAuth(config_file=..., profile_name=...)`.
- `RESOURCE_PRINCIPAL` uses `OciResourcePrincipalAuth()`; document this mode
  as not yet verified live.

Retain `create_guardrails_client` using OCI ApplyGuardrails. The example
environment must set `OCI_REGION=eu-frankfurt-1`,
`MODEL_ID=openai.gpt-5.6-sol`, blank `OCI_REASONING_EFFORT`, and
`OTEL_SERVICE_NAME=order-fulfillment-responses`. The README's tested-
configuration table remains empty and says "to be verified by the maintainer".

## LLM request, schema, and processing

Provide an explicit, tested function that derives a strict JSON schema from
`ExtractedOrder`, without OpenAI internal APIs. Every object, including those
under `$defs`, must have `additionalProperties: false`, and every property
must be listed in `required`. A hand-written schema is acceptable only if a
test validates its consistency with the Pydantic model.

`ExtractRequestNode` must build JSON-only Responses arguments:

- `model`, `instructions=EXTRACTION_PROMPT`, original user `input`, and
  `text.format` using named, strict `json_schema` output;
- optional normalized `reasoning`;
- `nemo_relay.llm.execute("extract_order", ..., model_name=MODEL, codec=OpenAIResponsesCodec(),
  response_codec=OpenAIResponsesCodec())`, invoked from the synchronous node
  with `nemo_relay.utils.run_sync`.

It extracts an `output_text` part from a message response and validates it as
`ExtractedOrder`. A `RuntimeError` beginning `guardrail rejected` returns
`{"status": "blocked"}`; other exceptions propagate. Invalid JSON or model
validation, refusal output, non-`completed` status, or a count other than one
requested item return `{"status": "invalid_request"}`. Do not copy the first
demo's `usage_payload`, `openai_response`, `run_conditional_execution`, or
`execute_conditional_execution` helpers.

The prompt guard must inspect only user text in a Responses request: `input`
as a string, or user-role list entries whose `content` is a string or
`input_text` parts. It must never inspect `instructions`.

## HTTP API, telemetry, and diagnostics

Keep the same `/health`, `/ready`, and `/orders` API and business results, but
use a distinct FastAPI title such as "Order fulfillment agent (Responses API)".
Each request's root scope is `order_fulfillment_responses`. Map
`openai.APIStatusError` to HTTP 502 with the upstream status but no provider
message; map `openai.APIConnectionError` and `openai.APITimeoutError` to HTTP
502, `model service unavailable`.

`telemetry.py` retains the first demo's OTLP, Langfuse, pricing, PII, and
guardrail lifecycle behavior. Its `relay_lifespan` registers and deregisters
the guardrail.

`python -m demos.order_fulfillment_responses.doctor` must make the same
structured request as the application through `create_responses_client`, using
`I would like 1 keyboard`. Preserve the first demo's output-safety rules and
map SDK errors as follows: 400 to model/parameter (including reasoning)
guidance; 401/403 to IAM-policy or compartment guidance; 404 to regional or
Responses-API availability; and network failures to region/connectivity
guidance.

`start.sh` starts `demos.order_fulfillment_responses.api:create_app` from the
repository root on port 8000. Update `scripts/setup.sh` to copy the new
`.env.example` to `.env` only when it is absent.

## Documentation and manual verification

Document the purpose, comparison table above, configuration, startup, and
examples for a normal order, a phone number, a local injection pattern, and an
OCI injection. Explain that Langfuse should show trace
`order_fulfillment_responses`, service `order-fulfillment-responses`, token
and cost data, masked phone number, and the prompt-guard span. Add the second
demo row to the root README, a "Run the Responses API variant" Quickstart
section that warns about shared port 8000, and TODO entries for OCI Enterprise
AI deployment artifacts, `llm.stream_execute`, and verification of resource
principal authentication.

The maintainer's live verification uses IAM profile `DEFAULT`: doctor succeeds;
the start script and four documented curls have the first demo's results; and
Langfuse displays the specified trace, LLM token/cost data, masked phone
number, prompt-guard span, and service name. Only after that verification may
the maintainer populate the tested-configurations table.

## Acceptance criteria and offline tests

All regular tests mock the OpenAI client and OCI Guardrails, require neither
OCI credentials nor network access, and cover the following:

1. The new package is a full independent copy, with no cross-package imports.
2. Relay receives JSON-serializable Responses arguments containing the strict
   schema; that schema enforces complete `required` fields and
   `additionalProperties: false`, including `$defs`.
3. Extraction handles valid output, malformed JSON, refusal, incomplete
   response status, and multiple items correctly.
4. A realistic mocked Responses payload supplies usage data; the full app
   exports tokens and a cost using the test pricing catalog.
5. Relay events redact a phone number in input and echoed output, while the
   mock client receives the original text.
6. The prompt guard reads both supported `input` forms, ignores instructions,
   and blocks an injection before the mock client is called while recording a
   rejected guardrail event.
7. OpenAI error types map to the specified HTTP 502 responses.
8. Doctor covers successful model validation and simulated 400, 401, 404, and
   network failures.
9. The root scope and default service name are the distinct Responses values.
10. Black, Pylint, pytest with coverage, and `pip check` pass in the required
    Conda environment, with total application coverage and coverage of the new
    package both at least 80%.

## Traceability

Implementation is in `demos/order_fulfillment_responses/`; offline tests use
the recognizable `tests/test_order_fulfillment_responses.py` prefix. The
implementation, tests, root README, Quickstart, TODO, dependency records, and
changelog have been updated together. The remaining acceptance activity is the
documented live OCI, IAM, and Langfuse verification by the maintainer.
