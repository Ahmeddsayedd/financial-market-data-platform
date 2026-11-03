# M11 — Controlled offline real-data Airflow execution

This is an **opt-in local test**. It runs the actual seven-task Airflow DAG on an
already captured Twelve Data AAPL response, then persists market facts and
advanced financial indicators to **`financial_market_test` only**. No new
Twelve Data HTTP request is needed. This is not a production deploy or a
throughput benchmark.

## Preconditions and scope

- Work from a clean, reviewed issue branch and make a test-database backup if
  the historical test data matters. The run **writes** Silver files, Gold facts,
  indicators, and execution-tracking records. No deletion or volume reset is
  authorized. Existing AAPL facts may be updated or left unchanged.
- Confirm `financial_market_test` is disposable/approved. The scheduler is the
  Airflow LocalExecutor task host. Verify `SELECT current_database()` there,
  and verify a reachable main PostgreSQL connection before proceeding.
- Start from the AAPL Raw capture produced during Issue #103. Check its SHA-256
  against the original capture record. The captured response and `.env` stay
  outside Git. Avoid screenshots showing credentials or raw JSON.
- **Do not enable live ingestion.** The run config explicitly sets
  `allow_live_ingestion=false`; the scheduler environment keeps
  `ENABLE_TWELVE_DATA_INGESTION=false`. Verify these both before triggering.
- The DAG stays **paused** for scheduled runs (`catchup=False`). Only one
  deliberately triggered manual run is approved.

## A. Stage the exact Raw input (no API or DB operations)

From the project root:

```bash
python scripts/prepare_airflow_replay.py \
  --source-raw data/experiments/issue103-live/raw/twelve_data/AAPL/2026/11/02/20261102T230104258952Z.json \
  --symbol AAPL
```

The command copies the captured JSON into the scheduler's existing bind-mounted
`data/raw/twelve_data/AAPL/...` directory, refuses overwrite if contents differ,
and reports the SHA-256, observation count, and safe DAG-run configuration.
Verify the digest matches the previously recorded value:
`c4fa032937e26b093c509dd7f5fc73d9a19fc76d1376426b86ff1bf2e58ed928`.
It must display `api_requests: 0`.

## B. Verify container safety before enabling Gold

```bash
docker compose -f compose.airflow.yaml ps
docker compose -f compose.airflow.yaml exec airflow-scheduler \
  python -c "import os; print('DB:',os.getenv('POSTGRES_DB')); print('Live:',os.getenv('ENABLE_TWELVE_DATA_INGESTION')); print('Gold:',os.getenv('ENABLE_GOLD_LOADING'))"
```

Confirm scheduler PostgreSQL host/port/username and actual `current_database()`
using the **read-only** query from the release runbook; do not paste secrets.
The expected database is exactly `financial_market_test`.

**Temporary permission change:** `ENABLE_GOLD_LOADING=true` must be passed
through Compose to the scheduler for this manually authorized run. This
recreates **only** the scheduler service, so do it only when no other Airflow
runs are active. Do not touch PostgreSQL volumes or change `.env` permanently.
In Git Bash, from the project root:

```bash
ENABLE_GOLD_LOADING=true ENABLE_TWELVE_DATA_INGESTION=false \
  docker compose -f compose.airflow.yaml up -d --no-deps airflow-scheduler
```

**Stop here if Compose reports an error, if the scheduler becomes unhealthy,
or if the newly started container does not show `Gold: true`, `Live: false`,
`DB: financial_market_test`.** Confirm the actual DB identity again. The
Gold loader independently queries the database identity before the atomic
facts-plus-indicators transaction.

## C. Manual Airflow run

In `http://localhost:8080`, keep the DAG `financial_market_pipeline` paused,
click **Trigger** for exactly one run, and use this configuration (the Raw path
must match the verified output from Step A):

```json
{
  "allow_live_ingestion": false,
  "allow_gold_loading": true,
  "raw_relative_path": "twelve_data/AAPL/2026/11/02/20261102T230104258952Z.json"
}
```

Observe the seven actual task-instance states. Check task results, not only
`success` bubbles: ingestion is expected to report `disabled`, Raw-to-Silver
and Gold to report `success`. Record exact Airflow run ID, task durations,
Raw and Silver paths, quality counters, Gold counts, and the SQL transaction
outcome. If a task fails, **do not retry or trigger another run** until its
sanitized log and the database state have been inspected.

The existing Gold adapter now supports an opt-in **atomic market-plus-indicator**
load for this DAG. A replay on already-persisted identical data may legitimately
report zero inserted/updated market rows. Such a run demonstrates processing
and idempotency, not fresh ingestion.

## D. Immediately restore the disabled default

After the run ends (success or failure), restore the scheduler to the normal
configuration and verify both flags are false:

```bash
ENABLE_GOLD_LOADING=false ENABLE_TWELVE_DATA_INGESTION=false \
  docker compose -f compose.airflow.yaml up -d --no-deps airflow-scheduler
```

Check the service is healthy and the DAG remains paused. Do not leave the
scheduler with `ENABLE_GOLD_LOADING=true`.

## E. Verify and preserve evidence

Use the existing read-only collector with the *exact run ID* and a fresh output
filename (it will not overwrite a prior report):

```bash
pt scripts/collect_orchestration_evidence.py \
  --airflow-run-id 'PASTE_EXACT_RUN_ID' \
  --symbol AAPL \
  --confirm-test-db financial_market_test \
  --output data/experiments/airflow-full-run-01.json
```

Confirm tracking counters, current Gold/indicator coverage, and the Airflow UI
task outputs independently. Save the evidence JSON and redacted screenshots
outside Git, recording source SHA, local environment, date, and whether any
facts actually changed. A tracking row and current Gold snapshot alone do not
prove which DAG task wrote the Gold rows: the task logs and outputs are
necessary for that claim.

## Limits

This run reuses previously obtained real-market data. It measures local
orchestration, replay, transformation, and persistence behavior, **not** live
provider latency, sustained throughput, or production execution. Repeatability
requires separate manual authorization per run. No destructive rollback or
clean-database insertion benchmark is implied.
