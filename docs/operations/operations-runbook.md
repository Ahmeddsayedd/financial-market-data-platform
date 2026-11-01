# Local operations and incident triage (#75)

All commands below are **manual, non-destructive** checks unless clearly
marked otherwise. Run from the repository root with Docker Desktop / Linux
containers available. Never paste raw credential-bearing log lines publicly.
Use [secrets guidance](secrets-and-least-privilege.md) for identities and
[backup guidance](backup-and-recovery.md) before recovery operations.

## Prerequisites and safe startup

1. Ensure private `.env` has distinct Gold and Airflow metadata credentials,
   JWT signing value and disabled ingestion/loading flags. Do not print it.
2. Check Docker availability using `docker info` without pasting sensitive
   fields. The Compose files share external network `financial-market-shared`;
   create it once if missing using `docker network create financial-market-shared`.
3. Validate Compose **without displaying resolved secrets**:

   ```bash
   python scripts/validate_compose_health.py
   ```

4. Start Gold PostgreSQL (separate database and persistent volume):

   ```bash
   docker compose up -d --wait postgres
   ```

5. Bring up the Airflow metadata DB, then run the initialization/migrations
   only in this intentionally configured local Airflow metadata database:

   ```bash
   docker compose -f compose.airflow.yaml up -d --wait airflow-postgres
   docker compose -f compose.airflow.yaml up airflow-init
   ```

   Confirm `airflow-init` exits `0` before continuing. The init command runs
   Airflow metadata migrations; it is not a Gold warehouse migration.

6. Start the API, scheduler and DAG processor:

   ```bash
   docker compose -f compose.airflow.yaml up -d airflow-api-server airflow-scheduler airflow-dag-processor
   docker compose -f compose.airflow.yaml ps -a
   docker compose ps -a
   ```

The API server is bound to `127.0.0.1:${AIRFLOW_PORT:-8080}` and Gold DB to
`127.0.0.1:${POSTGRES_PORT:-5432}`. Running/healthy containers alone do not
prove that Airflow tasks have executed successfully or migrations are current.
Keep `financial_market_pipeline` paused unless an operator intentionally
approves a specific run. Do not trigger a DAG to test connectivity.

## Safe shutdown and restart

```bash
docker compose -f compose.airflow.yaml down
docker compose down
```

These `down` commands preserve named database and Airflow authentication
volumes when used **without** `--volumes` or `-v`. Avoid `docker compose down --volumes`, `down -v`, `docker
volume prune`, and manual volume removal during ordinary operations.
Stop producers/consumers in a planned maintenance window before taking an
application-consistent backup.

## Non-secret diagnostics and incident checklist

1. Record UTC time, affected service, symptoms and relevant run identifiers.
2. Inspect `docker compose -f compose.airflow.yaml ps -a` and `docker compose
   ps -a`; note `unhealthy`, `starting`, `Exited (0)` or crash loops. A finished
   `airflow-init` should show `Exited (0)`.
3. Consult [Compose probe meanings](airflow-compose-health.md). API HTTP 200
   does **not** guarantee its JSON component statuses are healthy. Scheduler
   and DAG processor checks examine heartbeats, not successful DAG runs.
4. Check bounded logs locally, redact secrets before copying snippets:

   ```bash
   docker compose -f compose.airflow.yaml logs --tail=40 airflow-scheduler
   docker compose -f compose.airflow.yaml logs --tail=40 airflow-dag-processor
   docker compose -f compose.airflow.yaml logs --tail=40 airflow-api-server
   docker compose -f compose.airflow.yaml logs --tail=40 airflow-postgres
   docker compose logs --tail=40 postgres
   ```

5. Check DAG import failures without running tasks:

   ```bash
   docker compose -f compose.airflow.yaml exec airflow-dag-processor airflow dags list-import-errors
   ```

6. Correlate incidents using `dag_id`, `airflow_run_id`, `pipeline_run_id` and
   structured events. See [logging](structured-pipeline-logging.md). Check
   [pipeline health](pipeline-health-assessment.md): `degraded` means recent
   failures or stale running runs; `unknown` is not proof of a healthy pipeline.
7. For a database connectivity problem, check the correct database/service,
   the configured host and network, and matching stored password vs `.env`.
   Changing `.env` does not rotate an existing PostgreSQL role password.
8. For tracking callback failures, investigate DAG processor/task logs and
   test-database connectivity. Do not manually rewrite `pipeline_run` rows as
   a first response. Do not treat nonzero rejected records as a failed DAG.
9. For failed/queued/stale DAG runs, inspect task states and scheduler health,
   then decide whether to authorize a manual retry. Retries can repeat external
   requests or writes when explicitly authorized. Keep ingestion and Gold
   loading disabled until a reviewed action requires them.
10. If data integrity or credential exposure is suspected, stop authorized
    writers, preserve evidence, seek operator approval for recovery/rotation,
    and use the [backup runbook](backup-and-recovery.md).

## Routine verification

```bash
python -m ruff check .
python -m ruff format --check .
python scripts/run_tests.py
python scripts/smoke_dashboard.py
```

`run_tests.py` requires a correctly configured isolated test database to run
integration tests; it must not point at the primary Gold database. Offline
smoke checks are not proof of a healthy production deployment.
