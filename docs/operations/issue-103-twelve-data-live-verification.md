# Issue #103 — Controlled Twelve Data live verification

This is a **local portfolio experiment**, not a production ingestion schedule.
All live calls are explicitly opted in, and CI tests use mocks rather than
Twelve Data credentials. The existing Airflow live-ingestion and Gold-loading
feature flags remain disabled by default.

## Requirements and safety

- Use Python 3.11, `python -m pip install -e ".[dev,dashboard]"`, and your own
  `TWELVE_DATA_API_KEY` stored in your ignored local `.env` file or environment.
  **Never upload or commit `.env`, raw provider payloads, or connection logs.**
- Only one symbol and one HTTP request per invocation, with `max_retries=0`.
  Rate-limit/API failure is reported without printing credentials or response
  bodies. The request is for `1day` data and 60–200 observations (100 default).
  Actual provider credits, entitlements, delays, and data availability depend
  on the account. Inspect the Twelve Data dashboard before running a live test.
- Artifacts and evidence are created under `data/experiments/issue103-live/`,
  which is ignored by Git. The summary has no API key or raw response body.
  Review all files before sharing anything outside the local machine.
- Database writes are **disabled** unless `--write-gold` is supplied together
  with `--confirm-test-db financial_market_test`. The command then overrides
  `POSTGRES_DB` only in its own process, connects to that database, and verifies
  `SELECT current_database()` before making any write. Ensure this is an
  approved, isolated, disposable test database with compatible migrations.
  Do not point this test at a warehouse containing valuable data.

## 1. One live fetch, validation and offline Silver transformation

From the repository root in Git Bash:

```bash
python scripts/verify_twelve_data_live.py --live --symbol AAPL --outputsize 100
```

Expected output: a JSON evidence summary with `mode: live`, `api_requests: 1`,
SHA-256 of Raw JSON, date range, record count, acceptance/rejection rate,
Raw-to-Silver timing, and `gold_write_enabled: false`. This uses the existing
Twelve Data client, Raw writer, parser, validation and Silver writer.

A failed API request must not be interpreted as a success or retried
indefinitely. The presence of a healthy Docker container is not evidence that
this live fetch succeeded.

## 2. Offline replay: no provider credit consumption

Copy the `raw_file` relative path from the live evidence summary. Its path is
relative to `data/experiments/issue103-live`:

```bash
python scripts/verify_twelve_data_live.py \
  --replay-raw data/experiments/issue103-live/raw/twelve_data/AAPL/YYYY/MM/DD/TIMESTAMP.json \
  --symbol AAPL
```

Substitute the path generated on your machine. The replay checks the same Raw
SHA-256, uses **zero HTTP calls**, and reprocesses Raw to Silver. Compare the
quality counts and record date range across both runs. Timing may vary across
runs and is **not** a controlled speed benchmark on its own.

## 3. Optional isolated Gold persistence and replay

Only after confirming `financial_market_test` exists, migrations have been
applied **to that test database**, and its data can safely be changed:

```bash
python scripts/verify_twelve_data_live.py \
  --replay-raw data/experiments/issue103-live/raw/twelve_data/AAPL/YYYY/MM/DD/TIMESTAMP.json \
  --symbol AAPL --write-gold --confirm-test-db financial_market_test
```

Repeat the identical command to check idempotency. The evidence records
`gold_counts.market` (inserted, updated, unchanged, rejected) and
`gold_counts.indicators` (updated, unchanged). The loader uses the existing
**atomic** market + advanced indicator transaction. Replaying should not insert
new market facts or modify existing indicator values if input and pre-existing
history are unchanged. The first run may report updates to pre-existing facts
if they have older `extracted_at` timestamps; inspect the counts.

Always keep the primary `financial_market` warehouse separate. Test isolation
is enforced by process configuration and a read-only database identity query;
this is not a substitute for connection/role restrictions outside this script.

## 4. Evidence and presentation reporting

Two JSON files remain under the ignored output directory:

- `last-live-summary.json`: live response provenance, row counts, quality
  and processing times, plus no Gold writes for the default invocation.
- `last-replay-summary.json`: replay metadata, zero API requests, and optional
  Gold counts. Each new run overwrites that mode's last summary; copy sanitized
  snapshots to a separate **local** evidence folder if comparing runs.

Record test date (UTC), SHA of checked-out Git commit, Python/Docker versions,
provider, AAPL date range, accepted/rejected observations, API request count,
Gold insert/unchanged counts, and repeated-load observations in your thesis
ledger. Measure a series of runs for timing claims; a single sample is only a
smoke result. A live fetch is not proof of entire Airflow DAG execution or
long-term production reliability.

## Tests

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest -q -m "not integration"
# Only against an approved isolated financial_market_test environment:
python scripts/run_tests.py
```

Then require all seven CI jobs on the PR. CI never makes live API calls.
