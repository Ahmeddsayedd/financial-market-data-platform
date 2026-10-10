"""Map canonical financial market records to Gold warehouse values."""

from datetime import date
from financial_data_platform.models.market_data import MarketDataRecord


def to_date_key(observation_date: date) -> int:
    """Convert a date to its YYYYMMDD integer key."""
    return (
        observation_date.year * 10000
        + observation_date.month * 100
        + observation_date.day
    )


def to_date_dimension(observation_date: date) -> dict:
    """Map a trading date to its Gold calendar dimension attributes."""

    return {
        "date_key": to_date_key(observation_date),
        "full_date": observation_date,
        "day": observation_date.day,
        "month": observation_date.month,
        "quarter": (observation_date.month - 1) // 3 + 1,
        "year": observation_date.year,
        "day_of_week": observation_date.isoweekday(),
    }


def to_asset_identity(record: MarketDataRecord) -> tuple[str, str]:
    """Return the source and symbol identifying an asset in Gold."""
    return record.source, record.symbol


def to_market_fact(
    record: MarketDataRecord,
    asset_key: int,
) -> dict:
    """Map a canonical market observation to Gold fact values."""

    return {
        "asset_key": asset_key,
        "date_key": to_date_key(record.observation_date),
        "open": record.open,
        "high": record.high,
        "low": record.low,
        "close": record.close,
        "volume": record.volume,
        "extracted_at": record.extracted_at,
    }