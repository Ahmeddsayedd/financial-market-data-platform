# M9 — Structured pipeline logging and safe diagnostics (#71)

## Scope

Airflow task messages, DAG completion callbacks, and the Raw/Silver/Gold orchestration adapters emit one-line JSON log events through Python's `logging` API. They do not configure or replace Airflow's handlers. Existing tracking writes, task dependencies, ETL return values, and safety gates are unchanged.

## Event fields

`timestamp_utc` is ISO 8601 UTC with milliseconds. `severity`, `subsystem`, and `event` are always present. Optional fields include `dag_id`, `airflow_run_id`, `pipeline_run_id`, `stage`, `status`, and nonnegative processing counters. Only an explicit allowlist of extra fields is supported. Status `disabled` means no processing was authorized/selected; status `failed` is used for unsuccessful DAG completion and is not inferred from rejected record counts.

The JSON payload is emitted to an existing logger named `financial_data_platform.<subsystem>`; Airflow may add its own task timestamp/format around the payload. This implementation intentionally does not call `logging.basicConfig()` or change Airflow log handlers.

## Redaction and limits

Sensitive keys are never accepted as metadata fields. String identifiers are length-limited and restricted to simple characters; values with secret-related words, credential-bearing URLs, or control characters become `[REDACTED]`. Raw responses, full paths, database connection strings, arbitrary exception text, and environment dumps must **never** be passed to the helper. It is a defensive allowlist, not a general-purpose secret scrubber for all third-party library output or uncaught tracebacks.

Preserve exception tracebacks via Airflow's own error capture. The event API accepts `error_type` (class name) rather than exception messages that may disclose settings. Operators must restrict access to Airflow logs appropriately.

## Run correlation

Airflow task events carry DAG/run IDs where a `dag_run` context is available. The start and finalization events also include the deterministic `pipeline_run_id`. The reusable adapter functions have no Airflow context and therefore emit subsystem, event, status and counts only; they are not given invented identifiers. When investigating a failure, use Airflow's DAG run/task IDs to locate the task logs, then compare with `pipeline_run` rows from the isolated `financial_market_test` database.

## Safety and verification

The helper emits no network calls or SQL and does not create additional pipeline runs. The existing double-authorization for ingestion and Gold loading and the test-database restriction remain unchanged.

```bash
python -m pytest -q tests/unit/test_structured_events.py
python -m ruff check .
python -m ruff format --check .
python scripts/run_tests.py
```

Verify all six existing GitHub Actions jobs. Run the offline Airflow DAG import smoke test to check Airflow compatibility without triggering a DAG. Do not turn on ingestion to inspect logs.
