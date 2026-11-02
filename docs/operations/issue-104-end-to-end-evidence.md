# Issue #104 — Real-market replay benchmark and Gold read-only audit

## Purpose and limits

This is a **repeatable local evidence-collection procedure** built on the real
Twelve Data AAPL Raw JSON saved in Issue #103. It does **not** call Twelve Data,
execute an Airflow DAG, load Gold, change database data, or measure live API
latency. The Gold audit optionally reads existing rows in the disposable
`financial_market_test` database. This must not be represented as complete
production end-to-end performance or an Airflow task-execution measurement.

The script performs one optional warm-up and 2–10 timed measured offline
replays (five by default). Each replay runs the existing Raw-to-Silver
transformation, yielding a Parquet Silver file and data-quality counts. It
requires exactly matching Raw SHA-256, date range, accepted/rejected counts,
and output-file count across all attempts. Warm-ups are excluded from reported
min/median/mean/max/population standard deviation. Failure aborts the report;
no made-up measurements are substituted.

## Prerequisites

- Python 3.11 with project dependencies, local source at the reviewed Git SHA.
- An existing, privately stored Raw JSON from the successful Issue #103 live
  fetch; no new API access is necessary.
- The `.env` remains local and ignored. Neither Raw JSON, PostgreSQL settings,
  provider keys nor local evidence reports should be committed.
- Existing test database migrations and facts only if using the optional audit.

## 1. Repeated offline replay, no API calls or Gold writes

From the repository root (Git Bash):

```bash
python scripts/collect_thesis_evidence.py \
  --replay-raw data/experiments/issue103-live/raw/twelve_data/AAPL/2026/11/02/20261102T230104258952Z.json \
  --symbol AAPL --repetitions 5 --warmups 1 \
  --output data/experiments/issue104-aapl-replay-01.json
```

Use your actual Raw path if it differs. Choose a **new** `.json` output path
for each new experiment; overwrites are rejected. The default experiment root
is `data/experiments/issue103-live`. Timings and Git SHA are captured locally;
this repository does not contain or fabricate measured results. The previous
Issue #103 `last-replay-summary.json`, Silver and quarantine outputs may be
replaced during replay. Copy any prior evidence you need to keep first.

## 2. Read-only isolated Gold audit (optional)

Only when the test database is approved and already contains the AAPL data:

```bash
python scripts/collect_thesis_evidence.py \
  --replay-raw data/experiments/issue103-live/raw/twelve_data/AAPL/2026/11/02/20261102T230104258952Z.json \
  --symbol AAPL --repetitions 5 --warmups 1 \
  --audit-test-gold --confirm-test-db financial_market_test \
  --output data/experiments/issue104-aapl-gold-audit-01.json
```

This checks the server-side `current_database()` identity and executes a
parameterized SQL SELECT inside a read-only transaction. It reports the count
of existing twelve_data/AAPL Gold facts, distinct dates, date range, non-NULL
counts for seven advanced indicators, and **one observed query duration**.
Non-NULL counts establish presence, not independently validated numerical
accuracy. Row counts may exceed 100 if the test database already had data.
No data is inserted, updated, or deleted by this audit. The SQL duration is
not a repeated query-latency benchmark.

## 3. Interpretation and reporting

- Report the exact UTC collection timestamp, Git SHA, host/OS/Python versions,
  Raw SHA-256, valid/rejected totals, and repetition counts.
- Use the measured median/dispersion from `raw_to_silver_seconds`, excluding
  warm-ups. These timings cover Issue #103's Raw-to-Silver workflow and local
  filesystem operations, not provider fetch or Gold write latency.
- Compare the persisted audit date range and count to Issue #103's first load
  and identical replay, with the caveat of pre-existing Gold records.
- Preserve the prior actual live-fetch duration, first Gold-load duration and
  idempotent replay counts as **separate Issue #103 samples**. Do not combine
  them into a single unobserved end-to-end runtime or SLA.
- Keep the full local JSON evidence under ignored `data/experiments/` and
  review/redact it before sharing. The code writes no provider response body
  into the summary, but local paths and environment metadata may be sensitive.

## 4. Quality gate

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest -q -m "not integration"
# Approved isolated PostgreSQL test setup only:
python scripts/run_tests.py
```

Verify all seven GitHub Actions jobs for the PR. This issue does not change
CI workflows, migrations, Airflow scheduling, API calls, or production services.
