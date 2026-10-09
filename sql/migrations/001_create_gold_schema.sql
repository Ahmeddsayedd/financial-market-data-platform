-- Dimension: financial instruments
-- Grain: one row per (source, symbol).

CREATE TABLE dim_asset (
    asset_key BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,

    source VARCHAR(50) NOT NULL,
    symbol VARCHAR(20) NOT NULL,

    company_name TEXT,
    exchange VARCHAR(50),
    currency CHAR(3),
    sector TEXT,

    CONSTRAINT uq_dim_asset_source_symbol
        UNIQUE (source, symbol),

    CONSTRAINT ck_dim_asset_source_not_blank
        CHECK (LENGTH(TRIM(source)) > 0),

    CONSTRAINT ck_dim_asset_symbol_not_blank
        CHECK (LENGTH(TRIM(symbol)) > 0)
);


-- Dimension: calendar dates
-- Grain: one row per calendar date.

CREATE TABLE dim_date (
    date_key INTEGER PRIMARY KEY,
    full_date DATE NOT NULL UNIQUE,

    day SMALLINT NOT NULL,
    month SMALLINT NOT NULL,
    quarter SMALLINT NOT NULL,
    year INTEGER NOT NULL,
    day_of_week SMALLINT NOT NULL,


    CONSTRAINT ck_dim_date_key_consistency
        CHECK (
            date_key = (
                EXTRACT(YEAR FROM full_date)::INTEGER * 10000
                + EXTRACT(MONTH FROM full_date)::INTEGER * 100
                + EXTRACT(DAY FROM full_date)::INTEGER
            )
        ),


    CONSTRAINT ck_dim_date_calendar_consistency
        CHECK (
            day = EXTRACT(DAY FROM full_date)
            AND month = EXTRACT(MONTH FROM full_date)
            AND quarter = EXTRACT(QUARTER FROM full_date)
            AND year = EXTRACT(YEAR FROM full_date)
            AND day_of_week = EXTRACT(ISODOW FROM full_date)
        )
);


-- Operational metadata: pipeline executions
-- Grain: one row per logical pipeline execution.

CREATE TABLE pipeline_run (
    run_id UUID PRIMARY KEY,
    dag_id TEXT,

    started_at TIMESTAMPTZ NOT NULL,
    finished_at TIMESTAMPTZ,

    status VARCHAR(20) NOT NULL,

    records_extracted INTEGER NOT NULL DEFAULT 0,
    records_validated INTEGER NOT NULL DEFAULT 0,
    records_transformed INTEGER NOT NULL DEFAULT 0,
    records_loaded INTEGER NOT NULL DEFAULT 0,
    records_rejected INTEGER NOT NULL DEFAULT 0,

    duration_seconds NUMERIC(12,3),
    source VARCHAR(50),

    CONSTRAINT ck_pipeline_run_status
        CHECK (status IN ('running', 'success', 'failed')),

    CONSTRAINT ck_pipeline_run_counters_nonnegative
        CHECK (
            records_extracted >= 0
            AND records_validated >= 0
            AND records_transformed >= 0
            AND records_loaded >= 0
            AND records_rejected >= 0
        ),

    CONSTRAINT ck_pipeline_run_time_order
        CHECK (
            finished_at IS NULL
            OR finished_at >= started_at
        ),

    CONSTRAINT ck_pipeline_run_duration_nonnegative
        CHECK (
            duration_seconds IS NULL
            OR duration_seconds >= 0
        )
);


-- Fact: daily market observations and financial metrics
-- Grain: one row per asset per observation date.

CREATE TABLE fact_market_metrics (
    asset_key BIGINT NOT NULL,
    date_key INTEGER NOT NULL,

    open NUMERIC(20,8) NOT NULL,
    high NUMERIC(20,8) NOT NULL,
    low NUMERIC(20,8) NOT NULL,
    close NUMERIC(20,8) NOT NULL,
    volume BIGINT NOT NULL,

    extracted_at TIMESTAMPTZ NOT NULL,

    -- Calculated financial metrics will be populated in M5.
    period_return NUMERIC(20,8),
    log_return NUMERIC(20,8),
    sma_20 NUMERIC(20,8),
    sma_50 NUMERIC(20,8),
    rolling_volatility_20d NUMERIC(20,8),
    rsi_14 NUMERIC(20,8),
    drawdown NUMERIC(20,8),
    volume_zscore NUMERIC(20,8),

    pipeline_run_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT pk_fact_market_metrics
        PRIMARY KEY (asset_key, date_key),

    CONSTRAINT fk_fact_market_metrics_asset
        FOREIGN KEY (asset_key)
        REFERENCES dim_asset(asset_key),

    CONSTRAINT fk_fact_market_metrics_date
        FOREIGN KEY (date_key)
        REFERENCES dim_date(date_key),

    CONSTRAINT fk_fact_market_metrics_pipeline_run
        FOREIGN KEY (pipeline_run_id)
        REFERENCES pipeline_run(run_id),

    CONSTRAINT ck_fact_market_metrics_positive_prices
        CHECK (
            open > 0
            AND high > 0
            AND low > 0
            AND close > 0
        ),

    CONSTRAINT ck_fact_market_metrics_nonnegative_volume
        CHECK (volume >= 0),

    CONSTRAINT ck_fact_market_metrics_price_range
        CHECK (
            high >= low
            AND open BETWEEN low AND high
            AND close BETWEEN low AND high
        )
);