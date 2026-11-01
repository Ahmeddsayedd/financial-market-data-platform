# Release candidate build verification and manual promotion (#77)

This guide describes **local development release readiness**, not deployment to an
external host. No image is published, no registry credentials are used, and no
production environment is configured. Builds require access to package/image
registries; the runtime smoke checks do not require external network access.

## Runtime artifacts and boundaries

| Component | Build / verification | Notes |
| --- | --- | --- |
| Dashboard | `Dockerfile.dashboard`; `release-dashboard-image` CI job | Python 3.11 slim, `.[dashboard]`, non-root `dashboard` user, local Streamlit HTTP health check |
| Airflow task runtime | `Dockerfile.airflow`; existing `airflow-smoke` CI job | Airflow 3.1.7 and Psycopg 3; validated using the seven-task DAG in a network-isolated container |
| Gold and Airflow metadata PostgreSQL | Existing Compose files | PostgreSQL 17 local services, not release artifacts built by this issue |

The dashboard build uses `.dockerignore` with a **default-deny allowlist**:
`pyproject.toml`, `README.md`, `src/`, and the offline dashboard verification
script. It excludes local `.env`, source exports, `data/`, database dumps,
Airflow authentication/logs and Git history. `Dockerfile.dashboard` uses explicit
`COPY` paths; it never executes `COPY . .`. Review new files inside `src/`
prior to building; an allowlist is not a substitute for secret scanning.

The Airflow runtime Dockerfile does not copy project files into its image. The
existing CI mounts DAGs/source/scripts read-only for DAG import validation.
The operational Compose scheduler mounts source, DAGs and data directories at
runtime. Consequently, the Airflow image **alone** is not a self-contained
production deployable artifact and local Compose deployment depends on matching
host files and volumes.

## Run locally (non-production)

The following build commands contact package/image registries and may require
Docker Desktop and network access. Do not add build arguments containing secrets.

```bash
docker build --pull -f Dockerfile.dashboard -t financial-market-dashboard:local .
docker build --pull -f Dockerfile.airflow -t financial-market-airflow-runtime:local .
```

Run the dashboard image HTTP startup check with *no external network*:

```bash
docker run --rm --network none --entrypoint python \
  financial-market-dashboard:local scripts/verify_dashboard_image.py
```

The smoke uses non-sensitive placeholder DB settings, starts the real Streamlit
server inside the container, polls the loopback `/_stcore/health` endpoint,
and terminates it. HTTP 200 proves startup, not successful SQL reads, browser
rendering, production health, or network connectivity. The existing CI
`dashboard-smoke` job separately exercises four pages with AppTest and verifies
host HTTP startup. The existing `airflow-smoke` job builds and validates Airflow
without metadata DB initialization or a live API request.

Review local image metadata without disclosing resolved environment variables:

```bash
docker image inspect financial-market-dashboard:local --format '{{.Id}} {{.Config.User}}'
docker image inspect financial-market-airflow-runtime:local --format '{{.Id}}'
```

## Reproducibility and provenance limits

- Record the full Git commit SHA (`git rev-parse HEAD`), build UTC date, source
  branch, Dockerfile revision, and resulting **image digest/ID** in the manual
  release record. The local image ID is not a registry digest. Capture a
  registry manifest digest only after an approved push by an authorized operator.
- `python:3.11-slim`, `apache/airflow:3.1.7`, and `postgres:17` are tag-based
  references, **not digest-pinned**. `docker build --pull` may resolve a newer
  upstream tag. Airflow's Psycopg requirement and Python project dependencies
  use version ranges. Builds can change as indexes/base tags change.
- A fully reproducible bit-identical build is **not claimed**. Future release
  engineering should pin image digests, generate a reviewed dependency lock,
  track SBOM/provenance, and rebuild in a clean environment for comparison.
- CI checks code and startup health, but does not run vulnerability scanning,
  sign artifacts, verify SBOMs, publish images, or deploy production services.

## Manual pre-release gate

1. Confirm the exact commit/reviewed PR, no `.env` or sensitive artifacts staged,
   and six legacy CI jobs **plus** the new dashboard image job are green.
2. Confirm `python -m ruff check .`, `python -m ruff format --check .`, and
   `python scripts/run_tests.py` pass against isolated test databases.
3. Confirm dashboard HTTP smoke and seven-task Airflow DAG smoke pass; record
   which tests actually ran Docker versus mocks.
4. Record reviewed image IDs, resolved base versions, dependency versions,
   build timestamps, and any expected runtime mounts/dependencies.
5. Have an authorized operator explicitly approve destination, credentials,
   target database, and rollback image before any manual promotion.

## Manual promotion and rollback (procedure only)

No automated deployment or registry push is configured. A future operator can
approve promoting an *exact, previously verified* image digest to a controlled
environment. Keep the prior digest, configuration, volume identifiers, and
release metadata for rollback. Verify target connectivity and read-only DB
permissions separately. For Airflow, keep DAGs/source mounts and metadata DB
schema compatible with the selected image and disable ingestion/loading until
explicitly authorized.

For rollback, stop the application in a controlled maintenance window and
manually select the previously verified image and matching configuration;
restart and re-check component health and task status. **An image rollback does
not undo database migrations, executions, file outputs or credential rotation.**
Database restore, migration reversal, destructive changes, and secret rotation
require a distinct reviewed plan and operator approval. Do not use Compose
`down --volumes` to roll back code.

Related guides: [operations runbook](operations-runbook.md),
[backup/recovery](backup-and-recovery.md), and
[secrets/least privilege](secrets-and-least-privilege.md).
