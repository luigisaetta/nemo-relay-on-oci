#!/bin/sh
# Set up the supported runtime environment without changing the caller's shell.
set -eu

cd "$(dirname "$0")/.."

if ! command -v conda >/dev/null 2>&1; then
    echo "Conda is required. Install it from https://docs.conda.io/projects/conda/en/latest/user-guide/install/"
    exit 1
fi

if [ "$(uname -s)" != "Darwin" ] || [ "$(uname -m)" != "arm64" ]; then
    echo "Warning: untested platform, see TODO.md"
fi

if ! conda env list | awk '{print $1}' | grep -Fx "nemo-relay-on-oci" >/dev/null 2>&1; then
    conda create -y -n nemo-relay-on-oci python=3.11
fi

conda run -n nemo-relay-on-oci python -m pip install -r requirements.txt
conda run -n nemo-relay-on-oci python -m pip check

if [ ! -f demos/order_fulfillment/.env ]; then
    cp demos/order_fulfillment/.env.example demos/order_fulfillment/.env
fi

if [ ! -f demos/order_fulfillment_responses/.env ]; then
    cp demos/order_fulfillment_responses/.env.example demos/order_fulfillment_responses/.env
fi

echo "Next steps: configure one demo .env, run its doctor, then start that demo from the repository root."
