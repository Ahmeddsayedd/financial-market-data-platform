"""Read-only, dashboard-oriented queries against the existing Gold warehouse."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from financial_data_platform.warehouse.db import connect_to_database


@dataclass(frozen=True)
class Asset:
    asset_key: int
    source: str
    symbol: str
    company_name: str | None
    exchange: str | None
    currency: str | None
    sector: str | None


@dataclass(frozen=True)
class MarketObservation:
    observation_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    extracted_at: datetime
    price_change: Decimal | None
    daily_return_pct: Decimal | None
    sma_7: Decimal | None
    sma_30: Decimal | None
    period_return: Decimal | None = None
    log_return: Decimal | None = None
    sma_20: Decimal | None = None
    sma_50: Decimal | None = None
    rolling_volatility_20d: Decimal | None = None
    rsi_14: Decimal | None = None
    drawdown: Decimal | None = None
    volume_zscore: Decimal | None = None


@dataclass(frozen=True)
class IndicatorObservation:
    observation_date: date
    price_change: Decimal | None
    daily_return_pct: Decimal | None
    sma_7: Decimal | None
    sma_30: Decimal | None
    period_return: Decimal | None = None
    log_return: Decimal | None = None
    sma_20: Decimal | None = None
    sma_50: Decimal | None = None
    rolling_volatility_20d: Decimal | None = None
    rsi_14: Decimal | None = None
    drawdown: Decimal | None = None
    volume_zscore: Decimal | None = None


def _nonblank(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonblank string")


def _validate_filters(
    source: str,
    symbol: str,
    start_date: date | None,
    end_date: date | None,
    limit: int,
) -> None:
    _nonblank(source, "source")
    _nonblank(symbol, "symbol")
    for name, value in (("start_date", start_date), ("end_date", end_date)):
        if value is not None and (
            not isinstance(value, date) or isinstance(value, datetime)
        ):
            raise ValueError(f"{name} must be a date or None")
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValueError("start_date must not be after end_date")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 5000:
        raise ValueError("limit must be an integer between 1 and 5000")


def _read_rows(query: str, params: tuple) -> list[tuple]:
    """Execute a fixed SELECT in a PostgreSQL read-only transaction."""
    with connect_to_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute(query, params)
            return cursor.fetchall()


def list_assets(source: str | None = None) -> list[Asset]:
    """List Gold assets in a stable order; optionally restrict to one source."""
    if source is not None:
        _nonblank(source, "source")

    query = """
        SELECT asset_key, source, symbol, company_name, exchange,
               BTRIM(currency), sector
        FROM dim_asset
    """
    params: tuple = ()

    if source is not None:
        query += " WHERE source = %s"
        params = (source,)

    query += " ORDER BY source ASC, symbol ASC"

    rows = _read_rows(query, params)
    return [Asset(*row) for row in rows]


def get_market_history(
    source: str,
    symbol: str,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 5000,
) -> list[MarketObservation]:
    """Read historical OHLCV and all persisted financial indicators."""
    _validate_filters(source, symbol, start_date, end_date, limit)
    rows = _read_rows(
        """
        SELECT d.full_date, f.open, f.high, f.low, f.close, f.volume,
               f.extracted_at, f.price_change, f.daily_return_pct,
               f.sma_7, f.sma_30,
               f.period_return, f.log_return, f.sma_20, f.sma_50,
               f.rolling_volatility_20d, f.rsi_14, f.drawdown, f.volume_zscore
        FROM fact_market_metrics AS f
        JOIN dim_asset AS a ON a.asset_key = f.asset_key
        JOIN dim_date AS d ON d.date_key = f.date_key
        WHERE a.source = %s AND a.symbol = %s
          AND (%s::date IS NULL OR d.full_date >= %s::date)
          AND (%s::date IS NULL OR d.full_date <= %s::date)
        ORDER BY d.full_date ASC
        LIMIT %s
        """,
        (source, symbol, start_date, start_date, end_date, end_date, limit),
    )
    return [MarketObservation(*row) for row in rows]


def get_indicator_history(
    source: str,
    symbol: str,
    *,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = 5000,
) -> list[IndicatorObservation]:
    """Read persisted financial indicators without recalculating them."""
    _validate_filters(source, symbol, start_date, end_date, limit)
    rows = _read_rows(
        """
        SELECT d.full_date, f.price_change, f.daily_return_pct,
               f.sma_7, f.sma_30,
               f.period_return, f.log_return, f.sma_20, f.sma_50,
               f.rolling_volatility_20d, f.rsi_14, f.drawdown, f.volume_zscore
        FROM fact_market_metrics AS f
        JOIN dim_asset AS a ON a.asset_key = f.asset_key
        JOIN dim_date AS d ON d.date_key = f.date_key
        WHERE a.source = %s AND a.symbol = %s
          AND (%s::date IS NULL OR d.full_date >= %s::date)
          AND (%s::date IS NULL OR d.full_date <= %s::date)
        ORDER BY d.full_date ASC
        LIMIT %s
        """,
        (source, symbol, start_date, start_date, end_date, end_date, limit),
    )
    return [IndicatorObservation(*row) for row in rows]
