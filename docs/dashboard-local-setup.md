# M8 — Streamlit dashboard: local setup

The dashboard is a read-only view of the existing PostgreSQL Gold warehouse.
It retrieves available assets using the analytics query layer introduced in
Issue #53. Issue #57 adds interactive historical OHLCV and volume charts;
financial indicator overlays and pipeline monitoring remain future M8 work.

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
existing warehouse connector. It does **not** automatically read `.env`.

For local work, use a dedicated database account with `SELECT` privileges
on the required Gold tables wherever possible. The query layer explicitly
opens read-only transactions, but database-level permissions provide an
additional safeguard.

Never commit `.env` files or credentials. Do not use production credentials
for local tests.

## Launch

Set the PostgreSQL environment variables in the shell using your existing
secure local setup, then run from the repository root:

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
