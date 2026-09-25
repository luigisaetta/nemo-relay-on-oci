# Order fulfillment agent

Status: specification and configuration template only; not runnable yet.

This demo will accept a natural-language product order through FastAPI,
extract the product and quantity with OCI Generative AI, check a JSON catalog,
and simulate order registration through a tool. A LangGraph workflow with
one dedicated Python class per node will control the execution sequence.

See [specification 002](../../specs/002-order-fulfillment.md) for the confirmed
requirements, proposed graph, acceptance criteria, and remaining decisions.

## Planned NeMo Relay capabilities

- Observe graph node execution, OCI model calls through the LangChain
  integration, and the order-registration tool.
- Export traces through Relay's native OTLP exporter to an OpenTelemetry
  Collector.
- Inspect the execution paths for confirmed orders, unmatched products, and
  unavailable stock.

These capabilities are planned; instrumentation and trace delivery have not
been implemented or verified for this demo.

## Prepare configuration

Run from the repository root. Create your local configuration if it does not
already exist:

```bash
cp -n demos/order_fulfillment/.env.example demos/order_fulfillment/.env
```

Edit `demos/order_fulfillment/.env`:

| Variable | Required | Meaning |
| --- | --- | --- |
| `OCI_REGION` | Yes | Inference region; the sample is `us-chicago-1` |
| `MODEL_ID` | Yes | Model available in that region; replace the placeholder |
| `OCI_COMPARTMENT_ID` | Yes | Compartment OCID for inference; replace the placeholder |
| `OCI_AUTH_TYPE` | Defaults to `API_KEY` | `API_KEY` or `RESOURCE_PRINCIPAL` |
| `OCI_CONFIG_FILE` | API_KEY only; has a default | Local OCI SDK configuration, default `~/.oci/config` |
| `OCI_CONFIG_PROFILE` | API_KEY only; has a default | OCI SDK profile, default `DEFAULT` |

The code will derive the commercial-realm inference endpoint as
`https://inference.generativeai.<OCI_REGION>.oci.oraclecloud.com`.
Process environment variables will override the agent's `.env` values.

For local `API_KEY` authentication, the OCI SDK configuration references the
user's private signing key. Keep key material outside this repository.

For `RESOURCE_PRINCIPAL`, change `OCI_AUTH_TYPE` and omit `OCI_CONFIG_FILE`
and `OCI_CONFIG_PROFILE`. The OCI runtime must provide resource principal
credentials and the necessary permissions to call inference in the selected
compartment.

Only `.env.example` is versioned; `.env` is ignored by Git. Collector variables
will be added when the tracing configuration contract is defined.

## Execution and validation

All Python commands will use Conda `nemo-relay-on-oci`. A Uvicorn startup
command runnable from the repository root will be added with the implementation.
There is no application code, API server, or test suite for this demo yet.

Return to the [demo index](../../README.md#demos).
