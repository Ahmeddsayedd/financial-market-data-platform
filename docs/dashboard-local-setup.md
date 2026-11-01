# M8 — Streamlit dashboard: local setup

The dashboard is a read-only view of the existing PostgreSQL Gold warehouse.
It retrieves available assets using the analytics query layer introduced in
Issue #53. This foundation does not yet include price charts, indicators, or
pipeline monitoring pages; those belong to subsequent M8 issues.

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
