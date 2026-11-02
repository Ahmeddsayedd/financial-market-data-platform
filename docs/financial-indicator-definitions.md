# Issue #101 — Financial indicator methodology and verification

Calculations are performed **per `(source, symbol)` in ascending trading-observation
order**, using existing Gold market-history rows. Windows count observations,
not calendar days. Loading a historical record recalculates the complete asset
history inside the caller's existing transaction; no provider calls occur.

| Gold column | Formula / convention | Earliest observation |
| --- | --- | --- |
| `price_change` | `close[t] - close[t-1]` | 2 |
| `daily_return_pct`, `period_return` | `100 * (close[t]/close[t-1] - 1)` | 2 |
| `log_return` | natural logarithm of `close[t]/close[t-1]` | 2 |
| `sma_7`, `sma_30` | arithmetic mean of latest 7 / 30 closes | 7 / 30 |
| `sma_20`, `sma_50` | arithmetic mean of latest 20 / 50 closes | 20 / 50 |
| `rolling_volatility_20d` | sample stdev of 20 daily **fractional** returns multiplied by `sqrt(252)*100` (annualized percent) | 21 |
| `rsi_14` | Wilder's 14-change RSI, initial simple mean gain/loss, then smoothing `new=(13*old + latest)/14` | 15 |
| `drawdown` | `100 * (close[t]/max(close[1:t]) - 1)`; nonpositive percent | 1 |
| `volume_zscore` | `(latest_volume - mean)/sample_stdev` on 20 volumes | 20 |

**Edge cases:** Missing preceding observations yield `NULL` for change and
returns; all moving averages and rolling indicators have `NULL` during warm-up.
All fixed records in valid OHLCV require positive prices. Scalar helpers return
`None` for nonpositive log inputs and zero return denominator. Constant-volume
windows yield z-score 0. A flat RSI window returns 50; only gains returns 100,
only losses returns 0. Dates are not gap-filled. The volatility value is a
historical estimate and not a future-risk forecast.

Decimal arithmetic is used for calculated values, with PostgreSQL
`NUMERIC(20,8)` rounding at persistence. Calculated values should never be
compared to externally rounded data without a stated tolerance. Queries return
persisted Decimals; visualization only converts to floating-point at rendering.

The Gold table already contained the advanced columns in migration
`001_create_gold_schema.sql`; **no new migration is required**. Existing
SMA 7/30 columns were added in migration 002. Existing warehouses must have
both migrations applied. Neither migration is to be rerun manually on a live
warehouse. Before any integration run, verify the connection is to the approved
`financial_market_test` database; never point tests at the primary warehouse.

## Verification and scope

- `python -m pytest -q tests/unit/test_advanced_indicators.py` covers formulas,
  warm-up, isolation, edge cases, and replay.
- `python -m pytest -q -m "not integration"` verifies non-database regressions.
- `python scripts/run_tests.py` is allowed **only** after verifying test DB
  isolation; it reads `.env` and can write through integration fixtures.
- The pipeline remains offline by default. The separate Twelve Data live
  provider exercise belongs to a later, explicitly opt-in issue.
