from datetime import date

from financial_data_platform.warehouse.gold_mapping import (
    to_date_key,
    to_date_dimension,
    to_asset_identity,
    to_market_fact,
)
from financial_data_platform.models.market_data import MarketDataRecord


def test_to_date_key_converts_observation_date():
    """Convert a trading date into its YYYYMMDD warehouse key."""

    observation_date = date(2026, 10, 9)

    result = to_date_key(observation_date)

    assert result == 20261009
    assert isinstance(result, int)


def test_to_date_dimension_maps_calendar_attributes():
    """Map a trading date to the Gold calendar dimension."""

    observation_date = date(2026, 10, 9)

    result = to_date_dimension(observation_date)

    assert result == {
        "date_key": 20261009,
        "full_date": date(2026, 10, 9),
        "day": 9,
        "month": 10,
        "quarter": 4,
        "year": 2026,
        "day_of_week": 5,
    }


def test_to_date_dimension_handles_new_year():
    """Map January 1 correctly across the calendar-year boundary."""

    result = to_date_dimension(date(2027, 1, 1))

    assert result == {
        "date_key": 20270101,
        "full_date": date(2027, 1, 1),
        "day": 1,
        "month": 1,
        "quarter": 1,
        "year": 2027,
        "day_of_week": 5,
    }


from datetime import datetime, timezone
from decimal import Decimal


def test_to_asset_identity_preserves_source_and_symbol():
    """Asset identity must include the source and ticker symbol."""

    record = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 9),
        open=Decimal("250.00000000"),
        high=Decimal("255.00000000"),
        low=Decimal("248.00000000"),
        close=Decimal("253.00000000"),
        volume=1000000,
        source="twelve_data",
        extracted_at=datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    )

    result = to_asset_identity(record)

    assert result == ("twelve_data", "AAPL")


def test_to_market_fact_preserves_prices_and_identity():
    """Map a canonical observation to its Gold market fact values."""

    record = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 9),
        open=Decimal("250.12345678"),
        high=Decimal("255.00000000"),
        low=Decimal("248.50000000"),
        close=Decimal("253.87654321"),
        volume=1234567,
        source="twelve_data",
        extracted_at=datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    )

    result = to_market_fact(record, asset_key=42)

    assert result == {
        "asset_key": 42,
        "date_key": 20261009,
        "open": Decimal("250.12345678"),
        "high": Decimal("255.00000000"),
        "low": Decimal("248.50000000"),
        "close": Decimal("253.87654321"),
        "volume": 1234567,
        "extracted_at": datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    }

    assert isinstance(result["close"], Decimal)