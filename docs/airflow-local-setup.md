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