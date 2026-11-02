# M11 — Airflow orchestration and populated dashboard evidence

This guide is a **local-only verification procedure**. It distinguishes a
real Airflow task execution from DAG-import smoke tests, and distinguishes
pipeline tracking rows from task-instance evidence and Gold data provenance.
Neither this guide nor the evidence collector enables live ingestion, triggers
an Airflow run, or modifies a database.

## 1. Safety preflight

- Use the already approved isolated PostgreSQL service containing
  `financial_market_test`. Never point this procedure at `financial_market`.
- Keep `ENABLE_TWELVE_DATA_INGESTION=false` and `ENABLE_GOLD_LOADING=false`
  for the initial manual DAG demonstration. The DAG remains paused by default.
- Keep `.env`, the Airflow administrator password, provider responses and full
  task logs private. Do not commit raw experiment outputs or screenshots with
  sensitive information.
- Confirm services without changing them:

```bash
docker compose ls --all
python scripts/verify_deployment_runtime.py --stack all
python scripts/validate_compose_health.py
```

The tracking-start task **writes one run record** to the test database even
when ingestion and Gold loading are disabled. Do not trigger a DAG manually
without approving that isolated development write first.

## 2. Manual Airflow execution (approved test instance only)

1. Inspect the current DAG graph for `financial_market_pipeline` in the local
   Airflow UI (`http://localhost:8080`). Verify seven task IDs and no imported
   DAG errors. Check that the DAG is paused and catchup disabled.
2. Manually trigger **one run with an empty run configuration**, only after
   approving a tracking write to `financial_market_test`. Never enable the live
   ingestion or Gold loading flags for this first demonstration.
3. Record the Airflow **run ID**, UTC start/end time, overall run status, and
   each of the seven task states. Capture a sanitized screenshot of the graph
   and task state view. Note that `summarize_pipeline_run` is a demo branch and
   does not by itself prove Raw → Silver → Gold execution.
4. Confirm `ingest_raw_market_data`, `process_raw_to_silver` and
   `load_silver_to_gold` report disabled/skipped-by-policy results with no
   external request or Gold loading. Do not mistake task `success` for actual
   ingestion: tasks can finish successfully while returning `disabled`.
5. Pause the DAG again if you temporarily unpaused it. Verify no unintended
   scheduled runs were created and retain the sanitized review evidence.

**Optional later investigation:** executing the real Raw → Silver → Gold DAG
branch requires a separate approved isolated-data plan, review of the mounted
Raw/Silver paths, authorization settings, and database writes. This guide does
not authorize such a run. Previous Issue #103 verified that path outside
Airflow using real replay data.

## 3. Collect database evidence for a specific Airflow run

Use Python with the isolated test database environment, e.g. the local `pt`
wrapper, which is a personal convenience and **not required by the project**.
Create the output directory manually if needed:

```bash
mkdir -p data/experiments/airflow-demo
pt scripts/collect_orchestration_evidence.py \
  --airflow-run-id 'PASTE_EXACT_AIRFLOW_RUN_ID' \
  --symbol AAPL \
  --confirm-test-db financial_market_test \
  --output data/experiments/airflow-demo/run-01.json
```

Use the **actual** run ID from the Airflow UI, without including credentials.
This command refuses the main database, checks `SELECT current_database()`,
uses a read-only transaction, and writes only a sanitized JSON report to the
ignored `data/experiments/` area. It does not call an API or write to Gold.
An existing run is required; absent tracking returns an error. Do not create
fake success rows to make evidence collection pass.

The report records the precise UUID5 tracking key, run counters/status and a
**current** AAPL Gold snapshot. These are separate observations: Gold rows
cannot be attributed to the supplied Airflow run merely because they are in
the same database. Compare the run ID and seven task states in the Airflow UI.
A completed tracked `success` does not independently prove an Airflow success.

## 4. Populated dashboard demonstration

With the test database still selected, start the local dashboard:

```bash
pt -m streamlit run src/financial_data_platform/dashboard/app.py
```

Perform and record a **manual** review (the automated CI AppTest separately
verifies page execution with an intentionally unavailable database):

| Page | Evidence to capture |
| --- | --- |
| Overview | Source `twelve_data`, asset AAPL, available date range |
| Market charts | AAPL OHLC and volume chart, and date-filter behavior |
| Indicators | SMA 7/30 and advanced charts; explain window warm-up nulls |
| Pipeline monitoring | Specific `financial_market_pipeline` run and its recorded status/counters |

Save screenshots locally with no passwords, tokens, raw provider payloads or
unrelated private runs in view. Record the run ID, source commit, review UTC
time, dataset SHA-256 from Issue #103, the resulting JSON report, and which
manual checks passed. A dashboard display is not proof of an end-to-end Airflow
Gold load: the AAPL records may have been created earlier by Issue #103.

## 5. Verification and claims

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest -q -m 'not integration'
pt scripts/run_tests.py
python scripts/smoke_dashboard.py
```

Keep separate labels in your thesis for: (a) real provider ingestion and test
Gold replay (#103); (b) repeated offline processing and read-only Gold audit
(#105); (c) Airflow import/runtime health (M9/M11); (d) the **manual Airflow
run** observed here; and (e) populated dashboard human inspection. Do not
report (d) or (e) as passed until actually observed and recorded. No unattended
or production deployment is demonstrated.
