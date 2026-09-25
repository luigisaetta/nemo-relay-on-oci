# Specification 002: Order fulfillment HTTP agent

Status: First implementation authorized; baseline decisions recorded below.

## Objective

Build a simple order fulfillment agent that receives a natural-language
request, extracts a product and quantity using an LLM, checks a simulated
product catalog, and registers an order through a tool when stock permits.

## Confirmed requirements

- Every agent has a dedicated folder under `demos/`.
- Every agent can be started from the repository root.
- This demo uses LangGraph with explicit nodes, transitions, and execution
  order. Each node is implemented as its own dedicated Python class.
- An LLM extracts the product name and requested quantity from the user's
  natural-language input.
- The product catalog and available quantities are simulated in a JSON file,
  loaded when the agent starts.
- The agent determines whether the requested product matches the catalog.
- If there is no match, the response states that no product was matched and
  asks the user to submit a clearer request.
- If a product matches but available quantity is zero, the response states
  that it is unavailable.
- If a product matches and sufficient stock is available, the agent calls a
  tool that simulates registering the order.
- A successful response includes the original request and a complete
  confirmation that the order was registered.
- The agent is exposed through an HTTP API using FastAPI, started by Uvicorn.
- The project stack remains OCI Generative AI, `langchain_oci`, LangGraph,
  and NeMo Relay, with traces sent directly to remote Langfuse through the
  native OTLP exporter (superseding the original collector deployment).
- Each HTTP order attempt produces one root agent trace. Graph, LLM, and tool
  spans are descendants of that root so that Langfuse renders one hierarchy.
- Langfuse traces retain the order request, final response, LLM prompt and
  response history, and tool arguments and result. This is an explicit
  observability choice: deployments must not send production secrets or other
  sensitive customer data in order requests.
- Each agent uses a `.env` file in its own folder, with `OCI_REGION` and
  `MODEL_ID`. The OCI inference endpoint is derived from `OCI_REGION`.
- OCI authentication supports the local user's API signing key (`API_KEY`)
  and `RESOURCE_PRINCIPAL`.
- All documentation is in English. All Python work uses the Conda environment
  `nemo-relay-on-oci` and follows the quality gates in `AGENTS.md`.

## Graph

Each node is a dedicated callable class returning partial state updates.
Model and tool invocations receive the graph RunnableConfig for callback propagation.

| Node | Class | Responsibility |
| --- | --- | --- |
| Extract | `ExtractRequestNode` | Use the LLM to extract product and quantity and validate the result |
| Match | `MatchProductNode` | Find a catalog match for the extracted product |
| Availability | `CheckAvailabilityNode` | Compare requested quantity with available stock |
| Register | `RegisterOrderNode` | Invoke the simulated order-registration tool |
| Respond | `BuildResponseNode` | Produce a business response from the graph outcome |

```mermaid
flowchart TD
    START --> extract
    extract -->|valid product and quantity| match
    extract -->|clarification needed| respond
    match -->|match found| availability
    match -->|no match| respond
    availability -->|sufficient stock| register
    availability -->|unavailable| respond
    register -->|registration result| respond
    respond --> END
```

The extraction and registration failure paths must never produce a successful
order confirmation. Invalid extraction requests clarification; insufficient stock rejects the order;
operational failures never confirm registration.

## Data contracts

Pydantic models validate HTTP inputs, catalog entries, and extracted data;
a TypedDict carries per-request graph state.

- Input: original natural-language request.
- Extraction result: product name and requested quantity.
- Catalog entry: product identifier, product name, available quantity;
  optional aliases depend on the matching strategy.
- Graph state: original request, extracted fields, matched product,
  availability result, registration result, and final response.
- Order confirmation: original request, canonical product, ordered quantity,
  order identifier, and explicit registration confirmation.

The catalog is loaded once at startup from `catalog.json` beside the agent.
Entries have `product_id`, `name`, `aliases`, and nonnegative integer `available`.
The catalog must be nonempty and product IDs must be unique.

## HTTP interface and startup

- Demo folder: `demos/order_fulfillment/`.
- A POST endpoint accepts a natural-language request and returns the outcome.
- Route: `POST /orders` with `{"request": "I would like 2 keyboards"}`.
- FastAPI provides interactive API documentation.
- The README will provide a Uvicorn command runnable from the repository root.

Start from the repository root after activating `nemo-relay-on-oci` in the
calling shell. The executable script uses that shell's `python`, runs Uvicorn
on `127.0.0.1:8000`, and replaces itself with the server using `exec` so that
interrupt and termination signals reach Uvicorn directly. It does not activate
Conda or invoke `conda run`.

```bash
./demos/order_fulfillment/start.sh
```

Responses include `status`, `request`, `message`, `product`, `quantity`,
`order_id`, and `available`; fields without a value are null. Business statuses
are `confirmed`, `invalid_request`, `no_match`, `out_of_stock`, and
`insufficient_stock`.

## Agent configuration and OCI authentication

The order fulfillment configuration file is
`demos/order_fulfillment/.env`. Resolve its location relative to the agent's
module, not the current working directory, so root-level startup works.
Do not search other demo folders or load another agent's `.env` implicitly.

`OCI_REGION` and `MODEL_ID` are required, nonblank configuration values.
Construct the native OCI Generative AI inference endpoint from `OCI_REGION`:

```text
https://inference.generativeai.<OCI_REGION>.oci.oraclecloud.com
```

This URL pattern applies to OCI's commercial realm. Other realms require
realm-aware endpoint resolution and are outside the initial demo scope.
Pass the derived endpoint as `service_endpoint` and `MODEL_ID` as `model_id`
to `ChatOCIGenAI`. Do not require a separate endpoint variable. `OCI_REGION`
selects the inference region even when the local OCI profile uses a different
region. The selected model must be available in the selected region.

The supported authentication modes are:

- **API_KEY:** use the local OCI SDK configuration and the user's API signing
  key referenced by that configuration. The private key stays outside `.env`
  and the repository. Defaults: `~/.oci/config`, profile `DEFAULT`.
- **RESOURCE_PRINCIPAL:** use the resource principal credentials provided by
  the OCI runtime through the OCI SDK. This mode must not require a local
  user configuration file or private key.

Pass the selected mode through `ChatOCIGenAI.auth_type`. Do not silently
fall back to a different authentication mode if credentials are unavailable.
Here, local key authentication means OCI request signing with `API_KEY`;
`SECURITY_TOKEN` is a separate SDK mode and is not part of this requirement.

Confirmed supporting variables:

| Variable | Purpose | Default |
| --- | --- | --- |
| `OCI_AUTH_TYPE` | `API_KEY` or `RESOURCE_PRINCIPAL` | `API_KEY` |
| `OCI_CONFIG_FILE` | Local SDK configuration path, API_KEY only | `~/.oci/config` |
| `OCI_CONFIG_PROFILE` | Local SDK configuration profile, API_KEY only | `DEFAULT` |
| `OCI_COMPARTMENT_ID` | Target compartment OCID for inference requests | Required; no default |

The compartment is an inference request parameter, independent of the
authentication mode; do not infer it from the tenancy or resource identity.

Configuration template (placeholders only):

```dotenv
OCI_REGION=us-chicago-1
MODEL_ID=<model-id>
OCI_AUTH_TYPE=API_KEY
OCI_COMPARTMENT_ID=<compartment-ocid>
OCI_CONFIG_FILE=~/.oci/config
OCI_CONFIG_PROFILE=DEFAULT
```

For resource principal authentication, set `OCI_AUTH_TYPE=RESOURCE_PRINCIPAL`
and omit the local configuration path and profile.

Existing process environment variables override `.env`
values, allowing OCI deployments to inject configuration. Validate required
values and the authentication mode at startup. The tracked template is
[`demos/order_fulfillment/.env.example`](../demos/order_fulfillment/.env.example);
real `.env` files must remain untracked. The demo folder and its
[README](../demos/order_fulfillment/README.md) provide configuration preparation
instructions from the repository root. The template uses a sample region and
placeholder model and compartment IDs, which must be replaced for deployment.

## Observability

### Direct Langfuse export

The default deployment path is now agent -> NeMo Relay native OTLP exporter
-> remote Langfuse. No collector, Langfuse SDK, or additional Python exporter
is required. Configure these variables in the agent's `.env`:

- `LANGFUSE_BASE_URL`: instance base URL, without the API suffix.
- `LANGFUSE_PUBLIC_KEY` and `LANGFUSE_SECRET_KEY`: project credentials.
- `LANGFUSE_INGESTION_VERSION`: set `4` for Langfuse Cloud v4 real-time
  ingestion; leave it empty only for an older compatible self-hosted instance.
- `OTEL_SERVICE_NAME`: existing trace service identity.

All three connection values empty disables Langfuse. Partially filled values
fail startup clearly. Append `/api/public/otel/v1/traces` to the base URL and
send HTTP/protobuf with endpoint-local `Authorization: Basic base64(pk:sk)`.
For Langfuse Cloud v4, add `x-langfuse-ingestion-version: 4`. Credentials must
not appear in settings representations, logs, or tracked files.

The existing generic `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` remains optional for
other backends. It must be empty when Langfuse is configured; reject simultaneous
destinations instead of duplicating traces. Do not configure process-global
OTLP headers; this integration supplies authentication only on its own endpoint.
The local `.env` and `.env.example` must expose the same Langfuse settings.

Tests cover disabled export, missing credentials, invalid URLs, conflicting
destinations, Basic authentication, optional v4 header, and lifecycle cleanup.
Remote delivery can only be verified after the user supplies connection values.
See [Langfuse OTLP documentation](https://langfuse.com/integrations/native/opentelemetry).

The intended trace path is:

```text
HTTP order request root -> LangGraph nodes, LLM calls, and registration tool
    -> NeMo Relay native OTLP exporter -> remote Langfuse
```

The application must create the root `Agent` scope before invoking the graph
and close it with the serialized API response. The LLM scope must retain the
complete prompt/messages and validated extraction output; the tool scope must
retain its arguments and result. The observability component enables full
payload retention. Langfuse v4 Cloud uses ingestion version `4` so new traces
appear in real time.

Trace configuration will follow the pinned Relay version described in
[specification 001](001-dependencies-and-observability.md). Collector endpoint, service naming, payload capture, and shutdown behavior
follow the first implementation decisions below. Credentials must not be stored in the repository.

## First implementation decisions

- In `function_calling` mode, install a process-wide warning filter at server
  startup for only the exact empty-text `GenericProvider` message, category
  `UserWarning`, attributed to `langchain_oci.chat_models.oci_generative_ai`.
  This accommodates tool-call-only responses without mutating filters per
  concurrent request. Other messages, categories, and modules remain visible;
  JSON output modes do not install the filter. Extraction validation is unchanged.
  Tests verify suppression and the unaffected warning cases.
- Optional `OCI_REASONING_EFFORT` is passed to the OCI SDK as `reasoning_effort`
  using its uppercase values (`NONE`, `MINIMAL`, `LOW`, `MEDIUM`, `HIGH`).
  Empty means omitted. Models rejecting function calling with active reasoning
  can use `NONE` when supported, without changing defaults for other models.
- Upstream failures remain HTTP 502, but OCI service rejections report the
  upstream status and a configuration hint. Server logs record exception type
  or OCI status/code without raw exception text, prompts, or credentials.
  Regression tests must verify parameter forwarding and sanitized failures.
- Match normalized product names and explicit aliases, ignoring case and repeated
  whitespace. Reject unknown or ambiguous matches without fuzzy guessing.
- Extraction receives no catalog, inventory, or candidate product list. The
  LLM removes politeness and subjective modifiers such as "nice", normalizes
  common plurals to singular, and corrects only unambiguous spelling errors.
  Preserve meaningful qualifiers (wireless, size, material, brand, model, color)
  and the user's language. Do not replace an unknown item with a familiar one.
  Examples: "2 nice keyboards" -> `keyboard`, 2; "2 keybordas" -> `keyboard`, 2;
  "2 nice wireless keyboards" -> `wireless keyboard`, 2. The last example must
  not match the generic Keyboard entry. Live prompt checks must distinguish
  model behavior from offline tests that substitute the model.
- Extract a list of order items with the LLM, then require exactly one item
  with a nonblank product and a strictly positive integer quantity. Do not
  default missing quantities or accept fractional quantities.
- Reject insufficient stock without partial fulfillment.
- Store orders and mutable stock in memory; reset both on restart. Recheck and
  decrement stock under a lock in the registration tool. Run one Uvicorn worker.
  Every POST is a new attempt; persistent storage and idempotency are out of scope.
- Return English messages and structured outcomes including the original request,
  product, quantity, order ID, and remaining stock when applicable. Confirmation
  is deterministic and never generated by the LLM.
- POST `/orders` returns 200 for business outcomes, 422 for invalid HTTP input,
  and 502 for model service failures. Unexpected tool failures return 500 without
  confirmation. Invalid catalog/configuration fails startup. GET `/health`
  reports readiness without making inference calls.
- Optional `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` enables Relay's native HTTP/protobuf
  exporter. `OTEL_SERVICE_NAME` defaults to `order-fulfillment`. No generic endpoint or Langfuse configuration means
  export is disabled. Close the Relay activation on shutdown to drain exports.
  Relay callbacks may capture request/response content: use synthetic order data.
- Use the LLM's structured output with a configurable `OCI_STRUCTURED_OUTPUT_METHOD`
  (`function_calling` by default; `json_schema` and `json_mode` also supported).
  Actual model support must be checked in live validation.
- Relay's LangGraph callback observes chains and nodes. An explicit root agent
  scope wraps every request, with explicit LLM and tool child scopes retaining
  their semantic payloads. This instrumentation does not claim token usage or
  native provider payload metrics.

## Acceptance criteria

The implementation must include tests derived from the following criteria:

- A valid request for a matching product with sufficient stock follows
  extraction, matching, availability, registration, and confirmation in order.
- The product and quantity used downstream come from the validated LLM result.
- An unmatched product requests clarification and never calls registration.
- A matching product with zero stock returns unavailability and never calls
  registration.
- Registration is performed through a tool, and confirmation contains the
  original request, product, quantity, and successful registration result.
- Catalog data is read at startup, rather than reloaded for every request.
- Every graph node has a dedicated Python class.
- The API can be started from the repository root using Uvicorn.
- Configuration loads the agent's own `.env` when started from the root;
  the endpoint is derived from `OCI_REGION` and the configured model ID is
  passed to the OCI model integration.
- Offline authentication tests cover both `API_KEY` and `RESOURCE_PRINCIPAL`,
  including missing credentials and unsupported modes without silent fallback.
- Resource principal initialization does not read local user credentials.
- Configuration tests cover missing/blank required values and
  precedence between process environment and `.env` values.
- Offline tests substitute the LLM and external services and do not require
  OCI credentials, paid inference, or an external collector.
- One offline trace test verifies a root agent span, descendant LLM/tool spans,
  and populated request, prompt/history, extraction, tool, and final-response
  payloads.
- Additional tests cover the edge cases agreed in the decisions above.
- Black formatting and Pylint pass with no unresolved findings; pytest passes
  with at least 80% application coverage, including all application modules.
- Documentation and changelog are updated with execution and verification
  instructions. Live OCI and collector checks are reported separately from
  offline tests.

## Implementation scope

Implement the graph, JSON catalog, simulated registration tool, FastAPI API,
configuration loading, Relay lifecycle, offline tests, and root-level Uvicorn
startup. Live OCI calls and external collector delivery are separate checks.

## Configuration references

- [OCI SDK configuration and API signing keys](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/sdkconfig.htm)
- [OCI Generative AI inference client](https://docs.oracle.com/en-us/iaas/tools/python/latest/api/generative_ai_inference/client/oci.generative_ai_inference.GenerativeAiInferenceClient.html)
- Authentication parameter names were checked against the installed
  `langchain-oci` 0.3.2 source (`OCIGenAIBase`).

## Implementation and validation mapping

- `models.py`, `nodes.py`, and `graph.py`: validated extraction and explicit flow.
- `inventory.py` and `catalog.json`: startup catalog, matching, and atomic tool.
- `config.py`, `telemetry.py`, and `api.py`: configuration, Relay lifecycle, API.
- `tests/test_order_fulfillment.py`: business branches, HTTP behavior, concurrency,
  actual LangChain parsing, and Relay scope emission.
- `tests/test_configuration.py`: configuration precedence, authentication wiring,
  catalog validation, and exporter cleanup.

Offline tests do not establish extraction accuracy for the deployed OCI model.
Live inference and external collector delivery must be validated separately.

A live OCI request for two keyboards reproduced an upstream 400 rejecting
function tools with active reasoning. With `OCI_REASONING_EFFORT=NONE`, the
complete API workflow returned HTTP 200 and `confirmed`. External collector
delivery remains unverified.

Live normalization checks passed for seven synthetic requests with the configured
OCI model: "2 nice keyboards", "2 keybordas", "Could I get two lovely mice please?",
and "Vorrei due belle tastiere" confirmed the intended item and quantity.
"2 nice wireless keyboards" and "2 lovely bicycles" returned `no_match`;
"Some nice keyboards" returned `invalid_request`. No catalog was sent to the
LLM. These sample checks do not guarantee behavior for every possible phrasing.
