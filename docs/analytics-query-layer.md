# M8 — Read-only analytics query layer

The first dashboard capability reads existing Gold warehouse data. It never
calculates indicators, loads market data, or changes warehouse records.

## API

Module: `financial_data_platform.analytics.queries`

- `list_assets(source=None)` returns sorted `Asset` records, including optional
  company metadata and a stripped three-character currency.
- `get_market_history(source, symbol, *, start_date=None, end_date=None, limit=5000)`
  returns chronologically ordered `MarketObservation` objects with OHLCV,
  extraction time, and the four currently persisted indicators.
- `get_indicator_history(source, symbol, *, start_date=None, end_date=None, limit=5000)`
  returns chronologically ordered `IndicatorObservation` objects containing the
  four persisted indicators: `price_change`, `daily_return_pct`, `sma_7`, `sma_30`.

Date filters are inclusive. An unknown asset or empty range returns `[]`.
The `limit` must be between 1 and 5000; the API returns the *earliest* matching
observations when the limit is reached. Pagination and descending/latest-N
queries are separate future enhancements.

`Decimal` is preserved for financial values, and missing indicators remain
`None`. No future/planned indicator columns are exposed as if populated.

## Read-only behavior and security

- Uses the project's existing PostgreSQL environment configuration.
- Every query executes inside a PostgreSQL `READ ONLY` transaction.
- Fixed SQL statements use bound parameters for all user-provided filters.
- The module does not issue DML statements or call live providers.
- Production deployment should additionally use a dedicated PostgreSQL role
  granted `SELECT` only on the required Gold tables, for defense in depth.
- The current connector still accepts any configured database; unlike the
  integration tests, the query module does not hard-code a database name.

## Verification

Run unit tests without PostgreSQL:

```bash
python -m pytest -q tests/unit/test_analytics_queries.py
```

With the isolated `financial_market_test` database and migrations applied,
run integration tests using the local runner:

```bash
python scripts/run_tests.py tests/integration/test_analytics_queries_integration.py -v
```

Never point integration tests at a primary or production warehouse.
