-- Issue #27: Persist financial analytics indicators in Gold.
-- Preserve existing indicator columns for future development.

ALTER TABLE fact_market_metrics
    ADD COLUMN price_change NUMERIC(20,8),
    ADD COLUMN daily_return_pct NUMERIC(20,8),
    ADD COLUMN sma_7 NUMERIC(20,8),
    ADD COLUMN sma_30 NUMERIC(20,8);