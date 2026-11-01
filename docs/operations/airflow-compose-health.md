# M9 — Airflow service health and Compose validation (#69)

## Scope and baseline

The existing Gold and Airflow PostgreSQL services already use `pg_isready`.
Issue #69 adds health checks for **Airflow 3.1.7** API server, scheduler, and
DAG processor, together with a secret-safe Compose configuration contract check.
The checks do **not** trigger DAG runs, start live ingestion, or write Gold data.

## Probes and interpretation

| Service | Probe | Interpretation |
| --- | --- | --- |
| Gold PostgreSQL | Existing `pg_isready` | PostgreSQL responds; not proof that Gold migrations are current |
| Airflow metadata PostgreSQL | Existing `pg_isready` | Database responds; not proof that Airflow migrations completed |
| API server | `curl --fail --silent http://localhost:8080/api/v2/monitor/health` | HTTP endpoint is reachable; its HTTP 200 **does not** establish that scheduler/processor/database JSON statuses are healthy |
| Scheduler | `airflow jobs check --job-type SchedulerJob --hostname "$HOSTNAME"` | The local scheduler has a recent metadata DB heartbeat |
| DAG processor | `airflow jobs check --job-type DagProcessorJob --hostname "$HOSTNAME"` | The local DAG processor has a recent metadata DB heartbeat |

Airflow service probes run every 30 seconds with a 10-second timeout, five
retries, and a startup grace period (60 seconds API, 90 seconds workers).
They are container health checks, not a production readiness certification;
notably the API health response may contain unhealthy component statuses while
returning HTTP 200. The scheduler/DAG processor checks depend on the metadata DB.

These commands follow Apache Airflow's published Docker Compose health-check
patterns for the supported 3.x runtime:
<https://airflow.apache.org/docs/apache-airflow/3.1.7/howto/docker-compose/index.html>.

## Secret-safe configuration validation

With Docker Compose installed, from the repository root:

```bash
python scripts/validate_compose_health.py
```

The validator runs `docker compose -f <file> config --format json` for each
Compose file in a subprocess, supplies **dummy** environment placeholders,
and parses JSON privately. It never prints the fully resolved Compose output,
which would otherwise expose the interpolated database passwords and JWT
secret. It verifies health checks, an external shared network, localhost port
bindings, initialization dependencies, and disabled ingestion/Gold flags.

**This is a configuration check only:** it does not require the external Docker
network to exist, start a service, run migrations, or connect to a database.
It deliberately overrides relevant local variables with test placeholders;
keep `.env` private. On failure, the script reports a generic error without
printing Docker Compose stderr, which can contain secrets. Examine a failed
configuration locally and privately, not in public CI logs.

The independent **Docker Compose configuration validation** GitHub Actions
job runs this script on pull requests and pushes to `main` alongside the
existing five jobs. Docker Compose must be installed on the CI runner.

## Local runtime checks (explicit, opt-in)

The following checks are for an **already configured local development stack**.
Do not execute them as part of CI and do not create/alter any data volumes merely
to test configuration syntax.

1. Ensure Docker Desktop is running and the existing shared network is present:
   `docker network inspect financial-market-shared`.
2. Check services: `docker compose -f compose.airflow.yaml ps -a`.
3. Inspect status of individual services using the output's **State/Health**
   column; startup may need time after initialization.
4. Inspect relevant logs privately with
   `docker compose -f compose.airflow.yaml logs --tail=40 airflow-scheduler`
   or replace the service name with `airflow-api-server` / `airflow-dag-processor`.
5. Optionally inspect the overall API health JSON at
   `http://127.0.0.1:8080/api/v2/monitor/health` without publishing details.
   Check **each relevant component's `status`**, not merely HTTP 200.

Do not issue `docker compose down --volumes` to troubleshoot probe failures.
To stop the Airflow stack while preserving persisted metadata, use the
existing documented `docker compose -f compose.airflow.yaml down` procedure.
No automated startup/restart of the user's local Airflow stack is performed
by Issue #69.

## Validation

```bash
python -m pytest -q tests/unit/test_compose_health_validation.py
python -m ruff check .
python -m ruff format --check .
python scripts/run_tests.py
python scripts/validate_compose_health.py
```

The Python test suite cannot replace a real Docker Compose parse or running
Airflow health observation. CI validates Compose syntax; local runtime checks
must be separately reported, including any unavailable services.
