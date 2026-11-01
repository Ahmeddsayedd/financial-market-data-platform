# M8 final dashboard review — isolated populated data

Issue #63 verifies the four Streamlit dashboard pages with a **disposable** PostgreSQL data set. The sample is designed for human-facing UI inspection and automated integration tests. It is not a Twelve Data feed, and it is not a replacement for the production calculation pipeline.

## Safety requirements

- Use **only** the isolated `financial_market_test` PostgreSQL database, already migrated through `001` and `002`.
- Ensure your private `.env` refers to this *test* Docker instance. Do not print, upload, or commit `.env`.
- The seed/clean tool checks the configured database name **and** `SELECT current_database()` before doing any writes. The tool must not be run against a primary database, even to inspect it.
- The fixture source is `dashboard_demo`; its generated symbol has the form `DEMO` plus 12 hexadecimal characters.
- One seed creates 35 daily observations (September 1–October 5, 2026), persisted price changes, daily returns, SMA 7, SMA 30, and three `pipeline_run` rows representing success, failure, and running.
- This is *fixture data*: the demo helper calculates illustrative, deterministic indicators solely for test/demo seeding. Dashboard queries continue to read values, never recalculate them.
- Cleanup removes only the matching `dashboard_demo` asset and facts and that demo identifier's three pipeline runs. Generic `dim_date` calendar rows are deliberately retained because other records may share them.

## Local setup and visual review

Install once in a Python 3.11 environment:

```bash
python -m pip install -e ".[dev,dashboard]"
```

With the isolated PostgreSQL container running and your test-only `.env` configured, create a dataset:

```bash
python scripts/dashboard_demo.py seed
```

**Save the generated `DEMO...` symbol** displayed in the console; it is needed for targeted cleanup. This command is explicit and is never run by the dashboard itself.

Launch the dashboard:

```bash
python -m streamlit run src/financial_data_platform/dashboard/app.py
```

Check all four pages:

1. **Overview:** identify the generated `dashboard_demo` asset.
2. **Market charts:** select source `dashboard_demo` and the generated symbol. Check 35 OHLC candlesticks, 35 volume bars, the first/last selected dates, and summary metrics. Exercise a narrower date filter.
3. **Indicators:** choose the same source/symbol. Verify price with SMA 7 and SMA 30 overlays; the first six SMA 7 entries and first 29 SMA 30 entries are missing, **not zero**. Inspect daily change and return charts and the narrower date filter.
4. **Pipeline monitoring:** choose source `dashboard_demo`. Inspect success, failure, and running rows and their recorded counters; filter by each status and optionally by UTC start date. Counts are the displayed run totals, not global historical totals.

As with all Streamlit runs, preexisting process environment variables override the `.env` values. Confirm `POSTGRES_DB` and the target *instance* before seeding, not by exposing credentials.

## Targeted cleanup

Stop Streamlit (`Ctrl+C`) when finished, then remove only your session's fixture records using the exact generated symbol:

```bash
python scripts/dashboard_demo.py clean --symbol DEMO012345ABCDEF
```

Replace `DEMO012345ABCDEF` with **your actual generated symbol**. Cleanup is repeatable. It will not erase unrelated asset or run records. The script does **not** run `docker compose down --volumes` and does not remove any Docker infrastructure.

## Automated verification

The pytest integration fixture seeds unique records in `financial_market_test` and removes them in `finally`; it also verifies the underlying asset, indicators, market history, date filters, run states, counters, and all four populated page paths. Chart functions are replaced with mocks for UI wiring tests because the CI `dev` extra does not install Plotly or Streamlit. Existing figure tests verify chart serialization/mapping; manual inspection of real Plotly output remains an explicit separate acceptance check.

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest -q -m "not integration"
python scripts/run_tests.py
```

The tests do not call Twelve Data or start Airflow. Full integration tests require the isolated PostgreSQL service, its migration-test database, and the established CI setup.

If setup fails, do **not** redirect the fixture tool to another database to force a pass. Repair the isolated test environment first.
