# Quickstart: run the order fulfillment demo

This guide sets up the local environment and runs the first repository demo:
the order fulfillment agent. It uses OCI Generative AI for structured order
extraction, LangGraph for its workflow, and NeMo Relay for trace generation.
OCI Enterprise AI deployment artifacts are included in the demo, but this
quickstart runs the service locally.

## Prerequisites

Before continuing, ensure that you have:

- Conda installed.
- Access to an OCI tenancy, a compartment, and an OCI Generative AI model
  available in your selected region.
- Permission to invoke that model in the selected compartment.
- Either an OCI API signing-key profile on your machine or a supported OCI
  resource-principal runtime.
- Git and a shell capable of running the commands below.

Langfuse is optional. Configure it only if you want remote trace export.

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

Open `demos/order_fulfillment/.env` and set the required values:

```dotenv
OCI_REGION=<oci-region>
MODEL_ID=<oci-model-id>
OCI_COMPARTMENT_ID=<compartment-ocid>
OCI_AUTH_TYPE=API_KEY
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

### Optional: enable remote traces in Langfuse

NeMo Relay can export the demo's traces directly to Langfuse through OTLP.
Add these values to the same `.env` file when you have a Langfuse project:

```dotenv
LANGFUSE_BASE_URL=https://your-langfuse.example.com
LANGFUSE_PUBLIC_KEY=pk-lf-your-project-key
LANGFUSE_SECRET_KEY=sk-lf-your-project-key
LANGFUSE_INGESTION_VERSION=4
OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=
```

Leave all Langfuse values empty to run without remote export. Do not configure
`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` at the same time as Langfuse.

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

If Langfuse is configured, look for the `order_fulfillment` trace in the
configured project after submitting an order. Trace export is batched, so it
may take a short time to appear.

## Next steps

See the [order fulfillment demo README](demos/order_fulfillment/README.md)
for the complete configuration reference, response behavior, observability
data handling, OCI Enterprise AI container instructions, troubleshooting, and
verification commands.
