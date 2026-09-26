# Specification 006: macOS setup and diagnostic doctor

Status: Planned; implementation requires maintainer-verified OCI defaults.

## Objective

Make `demos/order_fulfillment` straightforward to install and diagnose for
non-developer EMEA Cloud Engineer Account colleagues on macOS Apple Silicon.
The deliverables are an idempotent setup script, a `doctor` diagnostic command,
documented local Docker execution using `API_KEY` authentication, and a root
`TODO.md` for deferred work.

## Supported platform and exclusions

The only supported and tested platform is macOS Apple Silicon (`arm64`) with
Python 3.11 and Conda. Do not add effective support for Windows, Linux, or
macOS Intel; record those items in `TODO.md` instead.

NeMo Relay 0.9.2 publishes wheels for macOS arm64, Linux x86_64/aarch64, and
Windows amd64/arm64, but not macOS x86_64. On an Intel Mac, pip would attempt a
Rust source build. macOS Intel is therefore unsupported until Relay publishes a
macOS x86_64 wheel.

This change must not alter demo behavior. In particular, do not change
`nodes.py`, `graph.py`, `api.py`, or `telemetry.py`; do not update dependencies;
and do not change graph flow, tracing, PII redaction, or pricing. `doctor` must
reuse `load_settings`, `create_extractor`, `trace_endpoints`,
`pricing_component`, and `pii_component` rather than duplicating their logic.
It must not validate repository-owned artifacts such as documentation, example
files, the default pricing catalog, or the deployment manifest: automated tests
own their validation.

## Architecture and deliverables

### Setup script

Add executable POSIX shell script `scripts/setup.sh`, runnable from the
repository root. It must:

1. Check that `conda` is available; otherwise exit with a message pointing to
   the Conda installation guide.
2. Create the `nemo-relay-on-oci` environment with Python 3.11 only if it does
   not already exist. Re-running the script must be safe.
3. Install only runtime dependencies from `requirements.txt` using the existing
   constraints, then run `pip check`. Development dependencies remain a
   separately documented contributor step.
4. Copy `demos/order_fulfillment/.env.example` to `.env` only when `.env` is
   absent; never overwrite an existing local `.env`.
5. Print next steps: edit `.env`, run `doctor`, then start the demo.
6. Require neither `sudo` nor system-package installation, and never activate
   Conda in the caller's shell; use `conda run` instead.
7. Print `untested platform, see TODO.md` and continue on platforms other than
   macOS arm64.

### Doctor command

Add `python -m demos.order_fulfillment.doctor`. It checks only user-dependent
setup: platform, Python environment, installed packages, `.env`, OCI and
Langfuse credentials, and reachability of external services. It prints one line
per check using `✅` (success), `⚠️` (warning), `❌` (error), or `ℹ️`
(information). Every warning or error adds a concrete corrective-action line
prefixed with `→`. It ends with a summary such as `1 error, 1 warning`, exits
1 when at least one error occurred, and exits 0 otherwise.

It supports:

- `--skip-model-call`, which skips only the OCI model call and reports it as
  information;
- `--offline`, which skips both the OCI model call and the Langfuse HTTP call.

Doctor output must never expose Langfuse keys, Authorization headers,
compartment/tenancy/user OCIDs, OCI key fingerprints, private-key paths, or
private-key contents. It may print region, model ID, OCI profile name,
authentication mode, and Langfuse project name.

### Diagnostic checks

Run checks in this order:

1. **Platform:** macOS arm64 is success; any other platform is an untested
   warning referring to `TODO.md`.
2. **Python and Conda:** Python must be 3.11 or newer or report an error. A
   `CONDA_DEFAULT_ENV` other than `nemo-relay-on-oci` is a warning.
3. **Dependencies:** compare packages pinned in `requirements.txt` with installed
   distributions using `importlib.metadata`. Errors identify the package and
   tell the user to rerun `scripts/setup.sh`. `requirements.txt` supplies
   expected versions only; doctor checks the environment, not the file.
4. **Environment file:** require the agent-local `.env` and validate it with
   `load_settings()`. Values beginning with `replace-with` are errors that name
   the variable, never its value. Validation errors name the invalid variable
   without exposing its value.
5. **OCI authentication:** for `API_KEY`, verify the config file, selected
   profile, OCI configuration (`oci.config.from_file` and
   `oci.config.validate_config`), and readability of the referenced private
   key. Each failure identifies its cause safely. For `RESOURCE_PRINCIPAL`,
   print `credentials provided by the OCI runtime; skipped locally`.
6. **OCI model call:** unless skipped, create the extractor through
   `create_extractor(settings)` and invoke the same structured-output path as
   the demo with `I would like 1 keyboard`. A successful extraction is success
   and includes token counts when `usage_metadata` is present. A
   `oci.exceptions.ServiceError` reports status and code, not provider text:
   status 400 suggests checking `OCI_STRUCTURED_OUTPUT_METHOD` and trying
   `OCI_REASONING_EFFORT=NONE`; 401/403 suggests IAM policy and compartment;
   404 suggests model availability in the selected region; all others suggest
   configuration review. Network and timeout errors report a region/connectivity
   action.
7. **Langfuse:** absent configuration is a warning, `traces will not be
   exported`, with a Quickstart reference. Partial configuration or conflict
   with `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` is an error through
   `trace_endpoints()`. A base URL containing `/api/public` is an error saying
   `use only the base URL`. Unless offline, issue a short-timeout authenticated
   GET to `{LANGFUSE_BASE_URL}/api/public/projects`: 200 is success and prints
   the returned project name; 401/403 indicates invalid keys, project, or
   region; another status or a network error identifies the URL/region and
   gives the EU (`https://cloud.langfuse.com`) and US
   (`https://us.cloud.langfuse.com`) URLs.
8. **Pricing catalog:** an empty `MODEL_PRICING_FILE` warns `no cost estimates`.
   A non-default catalog is validated with `pricing_component()`; errors fail
   the check. Do not validate the repository default
   `demos/order_fulfillment/pricing.example.json`. For either catalog case,
   warn if no `oci` entry has a matching `model_id` or alias for `MODEL_ID`, and
   tell the user to add one.
9. **PII redaction:** print informational active mode (`mask`, `redact`, or
   `off`) and what it sanitizes.

### Default verified configuration

Set `.env.example` to the maintainer-verified `OCI_REGION`, `MODEL_ID`, and
`OCI_REASONING_EFFORT` values; only `OCI_COMPARTMENT_ID` and Langfuse keys stay
as placeholders. Add a **Tested configurations** table to the demo README with
exactly one row: region, model, structured-output method, reasoning effort,
date, and verifier. Do not add unverified models.

The concrete region, model ID, and reasoning-effort values are intentionally
not invented by this specification; the maintainer must provide or verify them
before implementation can complete.

### Local Docker execution with API keys

Document and, if necessary, enable local execution of the existing image using
`--env-file demos/order_fulfillment/.env`, `OCI_AUTH_TYPE=API_KEY`, a read-only
mount of the host OCI configuration directory, and port 8080. Secrets and the
local `.env` must remain outside the image through `.dockerignore`. Keep
`agent.yaml` unchanged because Enterprise AI deployment remains
`RESOURCE_PRINCIPAL`-based.

The image uses `HOME=/tmp` and UID 10001. Host OCI `key_file` values often use
absolute `/Users/...` paths that do not exist in the container. Choose and
document a simple, verifiable solution that needs no edits to user files—for
example, mount `~/.oci` read-only at `/tmp/.oci` and require a `~/.oci/...`
key-file reference. When doctor runs inside the container, it must recognize a
missing absolute key-file target and explain this specific problem clearly.

### Documentation and TODO

Rewrite `Quickstart.md` as this linear journey:

1. Clone the repository.
2. Run `./scripts/setup.sh`.
3. Edit `.env` only for compartment and Langfuse keys.
4. Run `conda activate nemo-relay-on-oci && python -m demos.order_fulfillment.doctor`.
5. Run `./demos/order_fulfillment/start.sh`.
6. Submit the normal-order and phone-number `curl` examples.

Include **Run with Docker**, **Troubleshooting** (pointing to doctor), and
**Supported platforms** sections. State that macOS Apple Silicon is tested,
other platforms are untested and deferred to `TODO.md`, and macOS Intel is
unsupported because no NeMo Relay wheel exists. Keep development-dependency
installation in the contributor section of the root README rather than the
demo-run path.

Add English root `TODO.md`, linked from the root README, containing:

- **Platform support:** planned Windows setup equivalent, non-`start.sh`
  startup, PowerShell curl, `cp -n`, Docker and doctor tests; planned Linux
  setup and doctor tests; and the macOS Intel wheel limitation.
- **Planned demo improvements:** Relay prompt-injection guardrail;
  documentation restructuring with Langfuse screenshots and an ACE
  `DEMO-SCRIPT.md`; OCI model comparison with per-order cost (requiring pricing
  entries per model); and full OCI Enterprise AI deployment with Langfuse keys
  from OCI Vault, because the current `agent.yaml` exports no traces.

Each TODO item must be marked **Planned** or **Needs maintainer environment**.

## Error handling

All diagnostic failures must be actionable, safe, and non-secret. A failure in
one check should not prevent independent later checks when their inputs can be
evaluated safely. `doctor` must reserve error exit status for actual failures;
unsupported platforms, missing optional Langfuse export, missing cost estimates,
and skipped network checks are warnings or information as specified above.

## Acceptance criteria and offline tests

Add `tests/test_doctor.py`, with no OCI credentials or network access. Mock
platform, Python versions, `.env` files, OCI configuration, `create_extractor`,
and Langfuse requests. Cover every doctor check and outcome, including:

- extractor success with and without usage metadata; ServiceError 400, 401,
  and 404; and transport failure;
- Langfuse success with project name, 401, and network failure;
- exit 0 for warnings only and exit 1 for at least one error;
- no model/Langfuse call for `--skip-model-call` and `--offline`;
- placeholder detection that names its variable;
- output that never reveals recognizable test secrets, Authorization headers,
  OCIDs, or private-key paths;
- skipping `pricing_component()` for the default catalog; invalid custom
  catalog; matching pricing by model ID and alias; and missing pricing entry;
- container detection of a nonexistent absolute `key_file` path;
- `sh -n scripts/setup.sh` as an automated setup-script syntax check.

All existing tests, Black, Pylint, pytest-cov at 80% or higher, README updates,
and dated `Unreleased` changelog entry must pass before completion.

## Manual verification

The maintainer performs the following on macOS Apple Silicon:

1. In a new clean clone, run setup, configure `.env`, run doctor with all
   successes, start the demo, and inspect the Langfuse trace.
2. Intentionally use invalid Langfuse credentials and an unavailable model ID;
   verify doctor reports the prescribed corrective actions.
3. Run doctor and `/orders` inside Docker with `API_KEY` authentication.

Expected mocked doctor output is structurally similar to:

```text
✅ Platform: macOS arm64
✅ Python: 3.11.0
✅ Dependencies: installed versions match requirements.txt
✅ Environment: configuration is valid
ℹ️ OCI model call: skipped by --offline
⚠️ Langfuse: traces will not be exported
→ Configure LANGFUSE_BASE_URL, LANGFUSE_PUBLIC_KEY, and LANGFUSE_SECRET_KEY; see Quickstart.md.
ℹ️ PII redaction: mask mode sanitizes detected phone numbers in exported telemetry.
0 errors, 1 warning
```

## Traceability

- Extends [Specification 002](002-order-fulfillment.md) without changing the
  order workflow.
- Reuses pricing behavior from [Specification 003](003-llm-token-usage-and-cost.md)
  and PII configuration from [Specification 005](005-pii-redaction.md).
- Builds on the container contract in
  [Specification 004](004-order-fulfillment-container.md).
