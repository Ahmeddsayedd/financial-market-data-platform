# M8 — Streamlit dashboard: local setup

The dashboard is a read-only view of the existing PostgreSQL Gold warehouse.
It retrieves available assets using the analytics query layer introduced in
Issue #53. Issue #57 adds interactive historical OHLCV and volume charts;
Issue #59 adds financial-indicator visualizations; Issue #61 adds pipeline monitoring.

## Install

Use Python 3.11 or newer. From the repository root, install the dashboard
extra (and, optionally, the development/test tools):

```bash
python -m pip install -e ".[dashboard,dev]"
```

The dashboard dependency is optional so the data pipeline and existing CI
quality gates do not need to install Streamlit.

## Database configuration

Start the existing PostgreSQL instance with your normal local procedure.
The dashboard uses the same `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`,
`POSTGRES_USER`, and `POSTGRES_PASSWORD` environment variables as the
existing warehouse connector. When launched as a Streamlit application, it
automatically loads the repository-root `.env` using `python-dotenv`; already
set environment variables take precedence (`override=False`).

For local work, use a dedicated database account with `SELECT` privileges
on the required Gold tables wherever possible. The query layer explicitly
opens read-only transactions, but database-level permissions provide an
additional safeguard.

Never commit `.env` files or credentials. Do not use production credentials
for local tests.

## Launch

With PostgreSQL running and your private repository-root `.env` configured,
run from the repository root:

```bash
python -m streamlit run src/financial_data_platform/dashboard/app.py
```

The browser opens the overview page, which lists assets with source, symbol,
and available company metadata. An empty warehouse shows an informational
message. Missing credentials or database connectivity show a generic message
without exposing connection details.

The dashboard does not ingest data, call Twelve Data, modify warehouse rows,
or calculate financial indicators.

## Tests

Run the dashboard's database-independent unit tests:

```bash
python -m pytest -q tests/unit/test_dashboard_app.py
```

Run all database-independent tests and quality checks:

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest -q -m "not integration"
```

For the complete suite, use the existing local test runner with an isolated
`financial_market_test` database:

```bash
python scripts/run_tests.py
```

## Market charts (Issue #57)

The sidebar includes **Market charts** alongside the existing **Overview** page.
Market charts are built with Plotly, installed through the dashboard extra.
Select a source and symbol (the two together uniquely identify an asset). You may
optionally enable inclusive start/end observation dates. The candlestick chart
shows recorded daily OHLC prices, and a separate bar chart shows trading volume.
The summary reports the number of selected observations, the latest close in the
selection, and the difference between its first and last closing prices.

The dashboard uses the existing `get_market_history()` read-only query. The
current query returns the **earliest** 5,000 matching observations in date order.
When 5,000 rows are returned, the app warns that more rows *may* exist and that
users should narrow their date range rather than assume the result is complete.
This version intentionally does not implement pagination or latest-N queries.

Decimal market values remain exact in the analytics query layer and summary;
Plotly receives floating-point copies solely for chart rendering. The dashboard
does not recompute persisted Gold financial indicators, ingest prices, or write
to the database.

Run the market-chart unit tests (no Streamlit/Plotly installation required):

```bash
python -m pytest -q tests/unit/test_dashboard_market_charts.py tests/unit/test_market_chart_figures.py
```

To see populated charts, connect the application to a Gold warehouse containing
previously validated historical observations. Do **not** load test fixtures into
a primary/production warehouse just to demonstrate the UI.


## Financial indicators (Issue #59)

The **Indicators** navigation page plots the four currently persisted metrics:
`price_change`, `daily_return_pct`, `sma_7`, and `sma_30`. The close/SMA
figure overlays SMA 7 and SMA 30 on stored closing prices; separate figures
show daily price changes and percentage returns.

Select source and symbol independently, then optionally filter the inclusive
observation-date range. Data comes from the same `get_market_history()`
read-only Gold query used by Market charts; a single query aligns dates and
values. No indicators are recalculated. Database `NULL` indicator values
remain missing (Plotly gaps), and zero values remain genuine zeros.

The page warns when the earliest 5,000 observations are returned, because
there may be more matching records. Narrow the date range for complete views.
For insufficient history with no calculated indicators, it shows an
informational message while retaining the closing-price chart.

Run indicator-chart tests without installing Streamlit or Plotly:

```bash
python -m pytest -q tests/unit/test_dashboard_indicators.py tests/unit/test_indicator_chart_figures.py
```

Only use isolated test data when visually verifying populated charts; never
seed the primary warehouse for UI demonstrations.

## Pipeline monitoring (Issue #61)

The **Pipeline monitoring** page displays persisted `pipeline_run` records from
PostgreSQL Gold. It provides source, status, and optional inclusive **UTC**
execution-start date filters. Results show the newest runs first, up to 500.

The page reports counts of **displayed** successful, failed and running runs,
plus the stored record counters: extracted, validated, transformed, loaded and
rejected. Counts reflect pipeline tracking snapshots; a zero can also mean a
stage was disabled or did not report an observation count. A loaded counter
includes inserted and updated observations, not unchanged replays. Do not
interpret extracted records as the number of Twelve Data requests or files.

The page displays the run UUID, DAG ID, start/finish times, source, status,
duration and recorded counters. If the query reaches 500 rows, totals cover
only those returned runs, not all historical matches. A separate date or source
filter can narrow the displayed selection.

Detailed violation codes are produced by the separate quality-report and
quarantine JSON mechanism. They are **not linked to `pipeline_run` rows** in
the current schema and are therefore **not** claimed or derived from the
recorded rejection counter. The monitoring page does not read arbitrary
filesystem paths or expose quarantine record payloads.

All monitoring queries use PostgreSQL read-only transactions and parameter
binding. They do not trigger Airflow, ingestion, or SQL updates. For production
use, configure a SELECT-only database role for additional protection.

Run focused tests using:

```bash
python -m pytest -q tests/unit/test_pipeline_monitoring_queries.py tests/unit/test_dashboard_pipeline_monitoring.py
```

Run isolated PostgreSQL integration tests with the established test runner:

```bash
python scripts/run_tests.py tests/integration/test_pipeline_monitoring_integration.py -v
```

Only `financial_market_test` is used for the integration fixture, which
removes only test-owned UUIDs. Do not point integration tests at a primary
warehouse.
