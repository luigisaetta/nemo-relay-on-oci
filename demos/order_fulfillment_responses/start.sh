#!/bin/sh
# Start the Responses API demo using Python from the already active environment.
set -eu

cd "$(dirname "$0")/../.."
exec python -m uvicorn demos.order_fulfillment_responses.api:create_app \
    --factory --host 127.0.0.1 --port 8000
