# Quickstart: run the order fulfillment demo

This guide sets up the local environment and runs the first repository demo:
the order fulfillment agent. It uses OCI Generative AI for structured order
extraction, LangGraph for its workflow, and NeMo Relay to trace every agent
step and export observability data to Langfuse through OpenTelemetry. OCI
Enterprise AI deployment artifacts are included in the demo, but this
quickstart runs the service locally.

The demo exports:

- Agent and tool steps as one nested trace per order.
- LLM prompts and responses.
- Input, output, and total token counts when OCI supplies usage metadata.
- An estimated cost for each LLM invocation, calculated from the local Relay
  pricing catalog.

## Prerequisites

Before continuing, ensure that you have:

- Conda installed.
- Access to an OCI tenancy, a compartment, and an OCI Generative AI model
  available in your selected region.
- Permission to invoke that model in the selected compartment.
- Either an OCI API signing-key profile on your machine or a supported OCI
  resource-principal runtime.
- A Langfuse Cloud account, a project, and that project's public and secret API
  keys. Langfuse Cloud offers a free plan. Create the project and keys as
  described in the [Langfuse tracing quickstart](https://langfuse.com/docs/observability/get-started).
- Git and a shell capable of running the commands below.

Langfuse configuration is required to observe the outcome that this demo is
designed to show. Without it, the local API can start, but it does not export
traces, prompts, responses, token usage, or estimated invocation costs.

## 1. Get the source

Clone the repository and change to its root directory:

```bash
git clone <repository-url>
cd nemo-relay-on-oci
```

If you already have a checkout, use its root directory for every remaining
command.

## 2. Create the required Conda environment

The project requires Python 3.11 or later and uses an environment named
`nemo-relay-on-oci`. Create it if it does not already exist:

```bash
conda create -n nemo-relay-on-oci python=3.11
```

Activate the environment and confirm the interpreter version:

```bash
conda activate nemo-relay-on-oci
python --version
```

Install the runtime and development dependencies, then verify that their
resolved versions are compatible:

```bash
python -m pip install -r requirements-dev.txt
python -m pip check
```

For non-interactive shells, replace `python` above with
`conda run -n nemo-relay-on-oci python`.

## 3. Configure OCI access and the demo

Create a local configuration file without overwriting an existing one:

```bash
cp -n demos/order_fulfillment/.env.example demos/order_fulfillment/.env
```

Open `demos/order_fulfillment/.env` and set the OCI and Langfuse values:

```dotenv
OCI_REGION=<oci-region>
MODEL_ID=<oci-model-id>
OCI_COMPARTMENT_ID=<compartment-ocid>
OCI_AUTH_TYPE=API_KEY
LANGFUSE_BASE_URL=https://cloud.langfuse.com
LANGFUSE_PUBLIC_KEY=pk-lf-your-project-key
LANGFUSE_SECRET_KEY=sk-lf-your-project-key
LANGFUSE_INGESTION_VERSION=4
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=
PII_REDACTION=mask
```

For `API_KEY` authentication, configure the OCI SDK profile and signing key on
your machine. By default, the demo reads `~/.oci/config` and its `DEFAULT`
profile. Set `OCI_CONFIG_FILE` or `OCI_CONFIG_PROFILE` in `.env` if you use a
different path or profile. The OCI configuration must refer to a valid private
signing key, and the selected user must be authorized to invoke the model.

To run inside an OCI resource-principal environment, use:

```dotenv
OCI_AUTH_TYPE=RESOURCE_PRINCIPAL
```

Do not set local signing-key path or profile values in that mode. The runtime
provides the credentials.

Never commit `.env`, private keys, OCIDs that should remain private, or trace
service keys. The `.env.example` file is a template only.

`LANGFUSE_BASE_URL` is the Cloud instance base URL for the selected region;
use `https://cloud.langfuse.com` for the EU Cloud shown above. Do not append
`/api/public/otel` or `/v1/traces`. Obtain the public and secret keys from the
project settings in Langfuse. Set all three Langfuse values together. Do not
configure `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` at the same time as Langfuse.

The included pricing catalog enables estimated costs, but its initial rates are
explicitly provisional and are not OCI invoice rates. Review and replace the
catalog with applicable OCI billing values before using the estimate for
financial reporting.

## 4. Start the agent

From the repository root, with `nemo-relay-on-oci` active, run:

```bash
./demos/order_fulfillment/start.sh
```

The FastAPI service starts at `http://127.0.0.1:8000`. Keep this terminal open
while using the demo; stop it with `Ctrl+C`.

## 5. Verify the service and submit an order

In a second terminal, activate the same environment if necessary and call the
health endpoint:

```bash
curl http://127.0.0.1:8000/health
```

Then submit a synthetic order:

```bash
curl -X POST http://127.0.0.1:8000/orders \
  -H 'Content-Type: application/json' \
  -d '{"request":"I would like 2 keyboards"}'
```

A successful request returns `status: "confirmed"`, an order ID, and the
remaining inventory. API documentation is available at
`http://127.0.0.1:8000/docs`.

To verify phone-number redaction in exported telemetry, use the default
`PII_REDACTION=mask` setting and submit a second synthetic request:

```bash
curl -X POST http://127.0.0.1:8000/orders \
  -H 'Content-Type: application/json' \
  -d '{"request":"I would like 2 keyboards, call me at +39 333 123 4567"}'
```

The model and HTTP response retain the original request. Langfuse shows the
phone number as `+** *** *** 4567` in the exported trace. Set
`PII_REDACTION=redact` for `[REDACTED]`, or `off` to disable this phone-only
sanitization. It does not protect email addresses or other sensitive data, so
continue using synthetic inputs.

Look for the `order_fulfillment` trace in the configured Langfuse project after
submitting an order. It contains the agent steps, prompts, responses, token
usage, and estimated invocation cost. When enabled, phone-number redaction is
applied before export. Trace export is batched, so it may take a short time to
appear.

## Next steps

See the [order fulfillment demo README](demos/order_fulfillment/README.md)
for the complete configuration reference, response behavior, observability
data handling, OCI Enterprise AI container instructions, troubleshooting, and
verification commands.
