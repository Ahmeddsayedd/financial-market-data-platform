# Issue #101 — Financial analytics completion: verification and traceability

## Requirements coverage

| Requirement | Implementation | Verification |
| --- | --- | --- |
| BL-01: Period return | `daily_return_pct` and `period_return`; one-period percentage return | `test_financial_indicators.py`; `test_advanced_indicators.py` |
| BL-02: Log return | `log_return`; Decimal natural logarithm of positive close ratio | `test_advanced_indicators.py` |
| BL-03: SMA 20/50 | Existing SMA 7/30 retained; SMA 20/50 persisted to the existing fact table | `test_advanced_indicators.py`; Gold integration |
| BL-04: Volatility | 20-return sample stdev, annualized by √252, expressed in percent | `test_advanced_indicators.py`; Gold integration |
| BL-05: Drawdown | Percentage change from running maximum closing price | `test_advanced_indicators.py`; Gold integration |
| BL-06: RSI 14 | Wilder-smoothed RSI after 14 valid close changes | `test_advanced_indicators.py`; Gold integration |
| BL-07: Volume | Trailing 20-observation volume z-score (sample standard deviation) | `test_advanced_indicators.py`; Gold integration |
| BL-08: Calculation verification | Known-value, warm-up, edge-case, source partitioning, replay tests | Unit + isolated Gold integration |

The full definitions and numerical conventions are in
[`docs/financial-indicator-definitions.md`](../financial-indicator-definitions.md).
These requirements were originally in the requirements document; acceptance
of this issue must be based on local/CI results, not just this table.

## Database safety and migrations

The eight advanced columns already exist in the original Gold migration
`001_create_gold_schema.sql`; the four legacy columns were added in migration
`002_add_financial_indicators.sql`. No new migration or destructive DDL is part
of #101. Neither production nor `financial_market` should be used for integration
verification. The new integration test forces `POSTGRES_DB=financial_market_test`,
checks `current_database()`, and rolls back without committing its test-owned
records. Do not run SQL migrations merely to apply this code-only update.

## Verification sequence (Git Bash, Python 3.11)

1. Create a dedicated branch from current `main`; extract Issue #101 ZIP at
   the repository root, preserving directories.
2. Run `python -m ruff format .` **only if** the formatting check reports
   differences; inspect any changed files before staging.
3. Run `python -m ruff check .` and `python -m ruff format --check .`.
4. Run `python -m pytest -q -m "not integration"`.
5. Before any integration test, inspect the isolated test database setup and
   verify the test DB is `financial_market_test` (the repository `.env` may
   select the primary local DB for the application). Do not expose secrets.
6. In the approved isolated test environment, run
   `python scripts/run_tests.py` and record totals.
7. Run `python scripts/smoke_dashboard.py` with installed dashboard extras.
8. Review `git diff --check`, staged file list, and secret hygiene. Push a PR
   and confirm **all seven GitHub Actions jobs** on its exact commit.

Docker runtime startup, real Twelve Data requests, and committed/live Gold
loads are *not* verified by this issue. Those require the later opt-in live
API/e2e issue. Do not label this issue “production verified.”

## Reviewer expectations

- Spot-check identical replay against existing Gold history; equality should
  result in no write (`IS DISTINCT FROM`) and no extracted-at modification.
- Confirm SMA7/SMA30 displays still work with new SMA20/SMA50 charts.
- Check NULLs rather than zeros for incomplete windows, except the defined
  flat RSI / constant-volume edge cases.
- Verify no provider calls or ingestion flags were enabled by this patch.
