#!/bin/sh
# Start the API with Python from the already active Conda environment.
set -eu

# Resolve the repository root relative to this script.
cd "$(dirname "$0")/../.."
exec python -m uvicorn demos.order_fulfillment.api:create_app \
    --factory --host 127.0.0.1 --port 8000
