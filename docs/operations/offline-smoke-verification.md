# M9 — Offline Airflow and dashboard smoke verification (#67)

## Purpose and scope

GitHub Actions retains the existing `lint`, `unit-tests`, and
`integration-tests` jobs. Issue #67 adds two independent, pull-request-triggered
jobs: `airflow-smoke` and `dashboard-smoke`. Both also run on pushes to `main`.
These smoke checks are not production deployment tests.

## Airflow runtime smoke

`airflow-smoke` builds the existing `Dockerfile.airflow` (Airflow 3.1.7 with
Psycopg 3) and launches `scripts/validate_airflow_dag.py` using **that runtime**.
The verification container has `--network none`, uses read-only bind mounts for
DAGs/source/scripts, and overrides the image entrypoint with Python. No
scheduler, API server, DAG run or database is started. The validator uses
Airflow's `DagBag` to check the real DAG import, task IDs, dependencies,
paused/catchup defaults, UTC start date, and zero ingestion retries.

Image construction can access package indexes to install the pinned dependency
ranges; **runtime verification itself is offline**. This is a DAG-import smoke
check, not proof of scheduler readiness or successful task execution.

To run locally from a Bash-compatible shell with Docker installed:

```bash
docker build -f Dockerfile.airflow -t financial-market-airflow-smoke:local .
docker run --rm --network none \
  --entrypoint python \
  -e PYTHONPATH=/opt/financial-data/src \
  -e AIRFLOW__CORE__LOAD_EXAMPLES=False \
  -e ENABLE_TWELVE_DATA_INGESTION=false \
  -e ENABLE_GOLD_LOADING=false \
  -v "$PWD/airflow/dags:/opt/airflow/dags:ro" \
  -v "$PWD/src:/opt/financial-data/src:ro" \
  -v "$PWD/scripts:/opt/financial-data/scripts:ro" \
  financial-market-airflow-smoke:local \
  /opt/financial-data/scripts/validate_airflow_dag.py
```

For Windows Git Bash, Docker path conversion may need `MSYS_NO_PATHCONV=1`
before `docker run`; if mount resolution fails, check the bind-mount paths.

## Dashboard page-execution smoke

`scripts/smoke_dashboard.py` runs the actual Streamlit entry-point using
`streamlit.testing.v1.AppTest`. It selects **Overview**, **Market charts**,
**Indicators**, and **Pipeline monitoring** and checks the expected heading,
the safe missing-database message, and absence of uncaught exceptions.

The script temporarily overrides PostgreSQL settings to `127.0.0.1:1`, which
is deliberately unreachable, and disables both live ingestion and Gold loading.
The values override any local `.env` in the smoke process. The test is safe to
run without PostgreSQL and never supplies a real provider API key.

Run locally:

```bash
python -m pip install -e ".[dashboard,dev]"
python scripts/smoke_dashboard.py
python -m pytest -q tests/unit/test_smoke_dashboard.py
```

The `dashboard-smoke` GitHub Actions job additionally starts a **headless
Streamlit HTTP server** on the runner's loopback interface, polls
`/_stcore/health` with a bounded timeout, and terminates the server. This
health endpoint alone does not guarantee page code executed; the AppTest
step provides the separate page-execution check.

## Safety and limitations

- No Twelve Data requests, Airflow task executions, Gold mutations, or
  database migrations are part of either smoke job.
- No production database is configured. Dashboard queries are exercised
  against a deliberately unreachable local TCP endpoint and must display
  their existing generic error rather than leaked connection details.
- The Airflow runtime is network-isolated while importing the DAG. The image
  build is **not** a network-isolated operation.
- Existing PostgreSQL integration tests continue separately and remain the
  source of confidence for warehouse SQL/data behavior.
- No browser automation or deployed service verification is claimed.
- These checks should remain required alongside the existing quality gates
  before merging M9 changes.

## Verification checklist

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest -q -m "not integration"
python scripts/run_tests.py
```

Also confirm that all **five** jobs succeed on the GitHub pull request.
CI is required to establish actual Airflow and Streamlit runtime compatibility.
