# Apache Airflow — Local Development Setup

## Overview

The Financial Market Data Platform uses Apache Airflow 3.1.7 for local workflow orchestration.

Airflow runs through Docker Compose with LocalExecutor and a dedicated PostgreSQL metadata database. This database is separate from the financial Gold warehouse.

The configuration is defined in `compose.airflow.yaml`.

## Prerequisites

- Docker Desktop running with Linux containers enabled
- Docker Compose
- Python 3.11 for the existing project test environment
- A local `.env` file created from `.env.example`
- At least 4 GB of memory available to Docker; approximately 8 GB is recommended

## Configure the Environment

Create or update `.env` with the Airflow-specific variables documented in `.env.example`:

- `AIRFLOW_POSTGRES_DB`
- `AIRFLOW_POSTGRES_USER`
- `AIRFLOW_POSTGRES_PASSWORD`
- `AIRFLOW_PORT`
- `AIRFLOW_JWT_SECRET`

Use unique values for passwords and signing secrets. Never commit `.env` to Git.

The Airflow metadata database credentials are independent of the Gold warehouse's `POSTGRES_*` configuration.

## Initialize Airflow

From the repository root:

```bash
docker compose -f compose.airflow.yaml up -d airflow-postgres
docker compose -f compose.airflow.yaml up airflow-init
```

The initialization service must finish with exit code `0`.

For an existing Airflow metadata database, `airflow-init` can apply pending schema migrations when required.

## Start Airflow

```bash
docker compose -f compose.airflow.yaml up -d airflow-api-server airflow-scheduler airflow-dag-processor
```

Check all services:

```bash
docker compose -f compose.airflow.yaml ps -a
```

The PostgreSQL database, API server, scheduler, and DAG processor should be running. The initialization container should have exited successfully.

## Access the Web Interface

Open:

http://localhost:8080

The local development administrator username is `admin`.

The default Simple Auth Manager generates an administrator password in the configured persistent authentication volume. Do not commit or publish this password.

For Windows Git Bash, the password file can be read using:

```bash
MSYS_NO_PATHCONV=1 docker compose -f compose.airflow.yaml exec airflow-api-server cat /opt/airflow/auth/passwords.json.generated
```

Keep the generated credentials private.

## DAG Directory

Airflow DAG definitions belong in:

```text
airflow/dags/
```

The DAG processor and scheduler mount this directory at:

```text
/opt/airflow/dags/
```

To inspect discovered DAGs:

```bash
docker compose -f compose.airflow.yaml exec airflow-dag-processor airflow dags list
```

No custom financial ETL DAGs are included in the initial infrastructure setup.

## Stop Airflow

```bash
docker compose -f compose.airflow.yaml down
```

This stops and removes Airflow containers and its network but preserves named Docker volumes.

**Do not use `down -v` unless you explicitly intend to delete Airflow's persistent metadata and authentication data.**

Stopping Airflow does not stop the separately configured Gold PostgreSQL environment.

## Troubleshooting

### Docker Engine Is Not Running

Start Docker Desktop and verify:

```bash
docker info
```

### PostgreSQL Authentication Fails

Check that the password in `.env` matches the password stored in the Airflow metadata database. Changing `.env` does not automatically update an existing PostgreSQL user's password.

### API Server Reports Permission Denied

Inspect:

```bash
docker compose -f compose.airflow.yaml logs --tail=40 airflow-api-server
```

A permissions error involving `/opt/airflow/auth/` may indicate that the Airflow user cannot write its authentication password file.

### Airflow Services Fail to Start

Inspect service status and logs:

```bash
docker compose -f compose.airflow.yaml ps -a
docker compose -f compose.airflow.yaml logs --tail=40 airflow-scheduler
```

## Run Project Tests

The repository includes a test runner that reads the local `.env` file and provides its settings to pytest:

```bash
python scripts/run_tests.py
```

To run an individual test file:

```bash
python scripts/run_tests.py tests/unit/test_run_tests_script.py
```

The integration tests require the separate Gold PostgreSQL container and its test databases to be available.

## Scope

This setup establishes local Airflow infrastructure only. Financial ingestion, Silver processing, Gold loading, and indicator calculation will be connected to Airflow DAGs in subsequent issues.

## First Financial Market DAG

Issue #31 introduces the first demonstration workflow:

`airflow/dags/financial_market_pipeline.py`

**DAG ID:** `financial_market_pipeline`

The workflow demonstrates Airflow task orchestration without calling financial APIs or modifying Raw, Silver, or Gold datasets.

### Workflow

The DAG contains three sequential TaskFlow tasks:

1. `check_pipeline_configuration` — validates static, non-sensitive pipeline settings.
2. `prepare_pipeline_run` — prepares deterministic demonstration run metadata.
3. `summarize_pipeline_run` — validates the prepared metadata and returns a completion summary.

The TaskFlow API connects these tasks by passing each task's output to the next task.

### Scheduling and Safety

- Daily schedule: `@daily`
- UTC-aware start date
- Historical catchup disabled
- Paused by default
- Maximum one active DAG run
- One retry per failed task

The DAG does not use Twelve Data API credentials or connect to the financial Gold warehouse.

### Run the DAG Locally

1. Start the Airflow environment using the instructions above.
2. Open `http://localhost:8080`.
3. Open `financial_market_pipeline`.
4. Trigger a single manual run.
5. If the run remains queued while the DAG is paused, temporarily unpause it.
6. Inspect the run and its task instances.
7. Pause the DAG again after verification to prevent further scheduled runs.

When the DAG is unpaused, Airflow may also create an eligible scheduled run.

A successful execution shows all three task instances in the `success` state.

### Automated Validation

Run the lightweight repository tests:

```bash
python scripts/run_tests.py tests/unit/test_first_airflow_dag.py
```

To validate the actual DAG structure with Airflow, copy the validation script into the running DAG processor container:

```bash
docker cp scripts/validate_airflow_dag.py financial-market-airflow-airflow-dag-processor-1:/tmp/validate_airflow_dag.py
```

Then execute it:

```bash
MSYS_NO_PATHCONV=1 docker compose -f compose.airflow.yaml exec airflow-dag-processor python /tmp/validate_airflow_dag.py
```

The runtime validator checks DAG imports, registered tasks, dependency relationships, the UTC-aware start date, and scheduling safeguards.

The `MSYS_NO_PATHCONV=1` prefix prevents Windows Git Bash from rewriting the container's Linux file path.

### Verified Local Execution

During Issue #31 development, two DAG runs completed successfully: one manually triggered run and one scheduled run.

All six task instances succeeded, demonstrating that the three tasks execute in the correct dependency order.

The DAG was paused again after verification.

### Limitations

This DAG is a demonstration of orchestration infrastructure, not a complete financial ETL implementation.

Actual market-data extraction, Raw and Silver processing, Gold PostgreSQL loading, and financial indicator persistence will be integrated in subsequent issues.

## Financial market ingestion

The `financial_market_pipeline` DAG integrates the existing Twelve Data ingestion adapter with Apache Airflow. It currently supports controlled ingestion of **AAPL daily market data** into the project's Raw JSON storage layer.

This milestone integrates Raw ingestion only. Silver transformations, Gold warehouse loading, and financial analytics are not yet connected to the Airflow DAG.

### Safety controls

Live Twelve Data ingestion requires two independent authorizations:

1. The scheduler environment variable `ENABLE_TWELVE_DATA_INGESTION=true`.
2. The individual DAG run configuration containing `"allow_live_ingestion": true` (JSON boolean).

Both must be present. Otherwise, `ingest_raw_market_data` returns a disabled result without calling Twelve Data.

The default environment value is `false`. The ingestion task also has **zero Airflow retries**, while the ingestion adapter initializes the API client with **zero internal retries**. This avoids automatic repeated requests after a failed ingestion attempt.

**Keep the DAG paused and leave the environment flag disabled during normal development.** Unpausing the DAG can permit scheduled runs, which must remain unauthorized for live ingestion unless explicitly intended.

### Raw storage

The Airflow scheduler mounts the repository's `data/raw` directory at `/opt/financial-data/raw`. Successful ingestion writes JSON under:

`data/raw/twelve_data/AAPL/YYYY/MM/DD/<timestamp>.json`

Raw data is excluded from Git through `.gitignore`. API credentials must remain in the private `.env` file and must never appear in committed files, documentation examples, or logs.

### Controlled verification

The integration can be tested without making an API request:

```bash
docker cp scripts/test_airflow_ingestion_authorization.py \
  financial-market-airflow-airflow-scheduler-1:/tmp/test_airflow_ingestion_authorization.py

MSYS_NO_PATHCONV=1 docker compose -f compose.airflow.yaml exec \
  airflow-scheduler python /tmp/test_airflow_ingestion_authorization.py
```

The test verifies all four combinations of the environment and DAG-run authorization flags. The ingestion adapter is mocked, including in the authorized case.

Validate DAG loading separately:

```bash
docker compose -f compose.airflow.yaml exec \
  airflow-dag-processor airflow dags list-import-errors
```

The expected result is `No data found`.

A controlled live ingestion run requires available Twelve Data API quota and deliberate authorization. Do not enable live ingestion merely to validate DAG parsing or task dependencies.

### Current milestone limitations

- Only AAPL is configured for the Airflow ingestion task.
- Live ingestion is opt-in rather than automatically scheduled.
- Repeated authorized runs can write additional timestamped Raw JSON files.
- Silver and Gold pipeline stages will be integrated in later milestones.

## Raw-to-Silver orchestration

The `financial_market_pipeline` DAG includes a `process_raw_to_silver` task after `ingest_raw_market_data`.

The task reuses the existing market-data processing implementation to read a preserved Twelve Data JSON response, parse canonical records, validate financial observations, write valid records to partitioned Silver Parquet, and preserve invalid records in quarantine.

### Offline replay

Raw-to-Silver processing can run without requesting new market data.

Trigger the DAG manually with a run configuration containing an existing Raw file path relative to `data/raw`:

```json
{
  "raw_relative_path": "twelve_data/AAPL/2026/10/24/20261024T160953206116Z.json",
  "allow_live_ingestion": false
}
```

Replace the example path with a Raw file that exists locally.

Keep `ENABLE_TWELVE_DATA_INGESTION=false` to prevent live ingestion.

The ingestion task returns a disabled result, while `process_raw_to_silver` uses the explicitly selected Raw file.

If no Raw file is selected and ingestion is disabled, the processing task returns a disabled result without writing Silver data.

### Output storage

Valid observations are stored in partitioned Parquet files under:

`data/silver/symbol=<SYMBOL>/year=<YEAR>/data.parquet`

Invalid observations are written as JSON quarantine records under `data/quarantine`.

Both directories are mounted into the Airflow scheduler container.

The existing Silver writer merges observations by symbol and observation date, allowing a repeated Raw file to be processed without accumulating duplicate observations for the same dates.

### Validation and failure behavior

Malformed JSON or structurally invalid provider responses cause processing to fail.

Market observations that can be parsed but violate existing financial validation rules are preserved in quarantine.

The task has zero Airflow retries to avoid automatic repeated processing. Silver and quarantine output files remain available for inspection.

### Verification

The offline AAPL replay was verified with 30 Silver observations representing 30 unique dates and zero quarantined records.

Behavioral task checks can be run inside the Airflow scheduler using:

```bash
docker cp scripts/test_airflow_silver_task.py \
  financial-market-airflow-airflow-scheduler-1:/tmp/test_airflow_silver_task.py

MSYS_NO_PATHCONV=1 docker compose -f compose.airflow.yaml exec \
  airflow-scheduler python /tmp/test_airflow_silver_task.py
```

This milestone stops at the Silver layer. Loading the transformed data into the Gold PostgreSQL warehouse will be implemented separately.

## Silver-to-Gold Airflow orchestration

The `financial_market_pipeline` DAG includes `load_silver_to_gold` as its sixth task, downstream of `process_raw_to_silver`.

The task reuses the existing Gold warehouse loader to read validated Silver Parquet files and persist financial market observations into PostgreSQL.

### Database configuration

The Airflow scheduler connects to the Gold PostgreSQL container through the external Docker network `financial-market-shared`.

For Issue #37, Gold loading is restricted to the `financial_market_test` database. The scheduler receives its database credentials through environment variables configured in the private `.env` file.

The custom Airflow runtime in `Dockerfile.airflow` includes Psycopg 3, which is required by the project's warehouse connection module.

### Gold loading authorization

Database writes require both:

- `ENABLE_GOLD_LOADING=true` in the scheduler environment.
- `"allow_gold_loading": true` in the individual DAG run configuration.

The task additionally checks that `POSTGRES_DB` is `financial_market_test` before calling the Gold adapter.

Gold loading is disabled by default. Keep `ENABLE_GOLD_LOADING=false` during normal development.

### Controlled offline execution

An existing Raw JSON file and Silver Parquet partition can be processed without contacting Twelve Data.

Example manual DAG run configuration:

```json
{
  "allow_live_ingestion": false,
  "allow_gold_loading": true,
  "raw_relative_path": "twelve_data/AAPL/2026/10/24/20261024T160953206116Z.json",
  "silver_relative_paths": [
    "symbol=AAPL/year=2026/data.parquet"
  ]
}
```

This configuration permits a Gold write only while the environment-level Gold loading switch is also enabled.

After a controlled test, pause the DAG, restore `ENABLE_GOLD_LOADING=false`, and recreate the scheduler so that the updated environment takes effect.

### Transactional loading and repeated execution

The orchestration adapter validates the selected Silver paths and reads the Parquet records before invoking the existing Gold loader.

Selected records are loaded through one PostgreSQL transaction. The existing loader manages commits, rollbacks, and duplicate/conflict handling.

During integration verification:

- The first load inserted 30 AAPL observations.
- Repeating the load inserted zero additional records and reported 30 unchanged observations.
- The subsequent authorized Airflow task processed 30 records and reported 30 unchanged observations.
- No market observations were rejected during these checks.

### Current scope

The DAG orchestrates Raw ingestion, Raw-to-Silver processing, and Silver-to-Gold loading. Live ingestion and Gold writes remain explicitly gated.

The project does not yet run unattended production ingestion or loading. Dashboard integration, cloud deployment, and production scheduling remain separate milestones.