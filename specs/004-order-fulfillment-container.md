# Specification 004: OCI Enterprise AI container contract

## Objective

Package the order-fulfillment FastAPI agent as a `linux/amd64` container and
provide a versioned `agent.yaml` compatible with the manifest schema used by
the parallel `codex-4-oci-enterprise-ai-deployment` repository.

## Requirements

- Add `demos/order_fulfillment/Dockerfile`, built from the repository root.
- Use `python:3.11-slim`, install only root runtime dependencies with binary
  wheels, copy the `demos` package, and run as a non-root user.
- Start Uvicorn on `0.0.0.0:8080` with the existing application factory.
- Add `GET /ready`, returning `200 {"status": "ready"}` after the graph is
  initialized and `503` before initialization is complete.
- Add a root `.dockerignore` that excludes credentials, tests, development
  artifacts, and documentation from the Docker build context.
- Add `demos/order_fulfillment/agent.yaml` using manifest schema version 1.
  It must identify the root build context and Dockerfile, a local image name,
  OCIR repository path, public unauthenticated deployment profile, and OCI
  runtime configuration.
- The manifest must select `RESOURCE_PRINCIPAL` and resolve `OCI_REGION`,
  `MODEL_ID`, and `OCI_COMPARTMENT_ID` from the deployer environment. It must
  not contain credentials, OCIDs, Langfuse keys, or literal model settings that
  could be secret.

## Scope and exclusions

- This change provides container and manifest artifacts only. It does not
  build, push, deploy, or provision OCI resources.
- It does not add deployment scripts to this repository. The manifest format
  is compatible with the external deployment repository's tooling.
- The functional `/orders` check is excluded from the manifest because it
  requires live OCI inference and a resource principal. `/health` and `/ready`
  remain platform probes.

## Architecture and configuration

The Docker image uses the repository root as its context because its pinned
runtime dependencies live in `requirements.txt` and imports begin with the
`demos` package. `CMD` invokes `demos.order_fulfillment.api:create_app` in
factory mode. The application initializes its graph during FastAPI lifespan;
the readiness endpoint reads that initialized graph state.

At deployment, OCI supplies the resource principal. The deployment operator
supplies non-secret deployment-specific values through `OCI_REGION`,
`MODEL_ID`, and `OCI_COMPARTMENT_ID`; the manifest's `from_env` sources make
that explicit without committing values. Optional Langfuse configuration is
intentionally absent and can be configured separately by the deployment
operator.

## Error handling

- Missing OCI runtime values fail application startup through existing settings
  validation.
- A malformed manifest, missing Dockerfile, or escaped build path is rejected
  by compatible manifest tooling before building.
- An unavailable graph yields HTTP 503 from `/ready`; `/health` continues to
  report the local liveness state.

## Acceptance criteria and tests

1. The Dockerfile uses Python 3.11, a non-root user, port 8080, and the
   existing Uvicorn factory command.
2. The Docker context excludes `.env` files and common development artifacts.
3. `agent.yaml` has the documented schema-v1 build, publish, deploy, runtime,
   and verify sections and contains no secret values.
4. The API returns `200 {"status": "ready"}` after normal startup.
5. Existing offline tests, formatting, Pylint, and coverage checks pass without
   OCI credentials, Docker, network access, or paid API calls.

## Manual verification

From the repository root, an operator with Docker buildx can build for the
target architecture with:

```bash
docker buildx build --platform linux/amd64 --load --provenance=false --sbom=false \
  -f demos/order_fulfillment/Dockerfile -t order-fulfillment:0.1.0 .
```

Run the image with a read-only root filesystem, writable `/tmp`, the three
required OCI variables, and OCI resource-principal runtime support. Then verify
`GET /health` and `GET /ready`. A live `POST /orders` is a separate OCI
integration test.
