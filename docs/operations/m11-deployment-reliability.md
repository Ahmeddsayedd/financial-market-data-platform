# M11 / #97 — Local deployment and startup reliability

## Scope and safety boundary

This is a **local/portfolio** deployment verification procedure, not a hosted
service, production-grade availability guarantee, or automatic disaster recovery.
The checker is read-only: it will not run migrations, start/stop containers, run
DAGs, or contact market-data providers. Airflow live ingestion and Gold loading
remain disabled by default. The dashboard image is verified separately in CI.

## Prerequisites

- A reviewed checkout of the target commit, Python 3.11+, Docker Engine/Desktop
  with Docker Compose V2, and Docker daemon access.
- Private, valid environment values in a local `.env` (use `.env.example` as a
  reference; **never commit, paste, or publish `.env`**).
- Enough local resources for PostgreSQL and Airflow; required host ports free.
- An operator-approved isolated `financial_market_test` database. Never point
  startup or migration commands at production or primary warehouse databases.
- The shared Docker network `financial-market-shared` is expected to exist before
  starting either Compose project. Check with:
  `docker network inspect financial-market-shared`.

## 1. Safe static preflight (does not start services)

```bash
python scripts/validate_compose_health.py
python -m pytest -q tests/unit/test_compose_health_validation.py tests/unit/test_deployment_runtime.py
```

The Compose validator substitutes synthetic environment values, parses resolved
configuration privately, and checks health probes, localhost-only host ports,
initialization ordering, the shared network, and disabled ingestion/loading.
It does **not** prove the containers start or remain reliable. Do not paste
`docker compose config` output into issues: it can expand credentials.

## 2. Optional local startup — only after checking the target environment

The following commands **change local container and persistent volume state**;
run them only in a disposable/approved development environment. Do not execute
as part of offline CI verification. Inspect `.env` privately first.

```bash
docker network inspect financial-market-shared
# Only when the network is missing and you have approved creating it:
docker network create financial-market-shared

docker compose -f compose.yaml up -d --wait postgres
docker compose -f compose.airflow.yaml up -d --build --wait
```

Airflow initialization (`airflow-init`) is expected to finish successfully
(exit code 0); other Airflow services should become **running/healthy**.
`--wait` depends on the installed Docker Compose V2 version. Starting Airflow
may initialize or migrate its own metadata database; verify that the isolated
volumes/credentials are correct before proceeding. The DAG remains paused.

## 3. Read-only snapshot verification (does not start services)

```bash
python scripts/verify_deployment_runtime.py --stack all
# Or isolate one stack:
python scripts/verify_deployment_runtime.py --stack airflow
python scripts/verify_deployment_runtime.py --stack gold
```

Exit codes: `0` all named containers in the expected states, `1` any missing,
starting, exited or unhealthy service, `2` Docker unavailable/timed out.
Results are a **point-in-time observation**, not long-running uptime evidence.
An Airflow API `/api/v2/monitor/health` HTTP 200 can still contain unhealthy
component statuses; examine each component privately when troubleshooting.
The checker intentionally does not show secrets, container environment, logs,
HTTP response bodies or resolved Compose configuration.

Dashboard verification is separate from the two Compose stacks:

```bash
python scripts/smoke_dashboard.py
# Optional image build and offline container smoke (requires Docker):
docker build -f Dockerfile.dashboard -t financial-market-dashboard:local .
docker run --rm --network none --entrypoint python \
  financial-market-dashboard:local scripts/verify_dashboard_image.py
```

The local image build may need internet access for base images/packages. The
`--network none` smoke does not contact PostgreSQL or any provider and does not
prove a browser-accessible deployed dashboard.

## Troubleshooting without destructive resets

| Symptom | Safe investigation | Recovery boundary |
| --- | --- | --- |
| Docker command fails | Check Docker daemon, Compose version, permissions | Do not change data volumes |
| Shared network missing | `docker network inspect financial-market-shared` | Create only with operator approval |
| PostgreSQL starting/unhealthy | `docker compose -f compose.yaml ps -a` and private `logs --tail=40 postgres` | Verify configuration and filesystem capacity; no blind volume deletion |
| Airflow init did not exit 0 | `docker compose -f compose.airflow.yaml ps -a` and private `logs --tail=40 airflow-init` | Check metadata DB health/credentials before considering migration repair |
| Scheduler/DAG processor unhealthy | Inspect container health and private service logs | Check metadata DB and heartbeats; do not auto-enable DAGs |
| API server healthy but DAG fails | Examine per-component API health status, scheduler/processor state and DAG import errors | HTTP reachability alone is insufficient |
| Dashboard smoke fails | Check isolated offline smoke environment and dependencies | Do not add live secrets to images or CI |

Never use `docker compose down --volumes`, `docker volume prune`, `docker system
prune --volumes`, or `docker compose rm -v` as a casual troubleshooting step.
To stop containers while retaining named volumes:

```bash
docker compose -f compose.airflow.yaml down
docker compose -f compose.yaml down
```

## Evidence and sign-off

For #97, capture the reviewed commit SHA, Compose/Python/Docker versions,
static validator result, unit test result, **whether runtime inspection was
actually executed**, sanitized per-service PASS/FAIL summaries, dashboard
smoke outcome, and the seven CI job links for that commit. Record unavailable
Docker execution as **NOT RUN**, never PASS. CI runs the static Compose contract
and unit tests; it does not start a real Airflow stack. Do not claim deployment
verification, container uptime, seven green jobs, or release approval without
actual corresponding evidence. Publication remains gated by the M11 checklist.
