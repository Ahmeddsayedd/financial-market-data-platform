# Raw-to-Silver-to-Gold Integration Tests

## Purpose

Validate the complete financial-market ETL pipeline using local Raw fixtures, real Silver Parquet storage, quarantine JSON, and the PostgreSQL test warehouse.

## Prerequisites

- Python development environment with project dependencies installed
- Docker Desktop and PostgreSQL test database running
- Current Gold database migrations applied
- Local PostgreSQL connection configuration available through `.env`
- `financial_market_test` available as the database

## Running the tests

```bash
python scripts/run_tests.py tests/integration/test_raw_to_gold_e2e.py -v
```

Run the entire suite with:

```bash
python scripts/run_tests.py
```

## Scenarios

1. **Valid batch:** Confirm two validated observations reach Gold with exact OHLCV values and extraction timestamps.
2. **Mixed-quality batch:** Confirm the invalid observation is quarantined, its violation codes are reported, and only the valid observation reaches Gold.
3. **Replay:** Process the same Raw observations twice and verify Gold reports unchanged facts rather than inserting duplicates.

## Database safety

The integration tests require `financial_market_test`.

Each test generates a unique symbol and checks the actual connected PostgreSQL database.

The Gold loader commits transactions, so a fixture performs targeted cleanup of only the generated asset and its fact rows.

Shared date-dimension rows are not deleted.

Tests must never truncate warehouse tables or delete unrelated assets.

## Limitations

These tests verify ETL behavior using local fixtures. They do not contact the Twelve Data API, trigger Airflow scheduling, test concurrent ingestion, or benchmark pipeline performance.