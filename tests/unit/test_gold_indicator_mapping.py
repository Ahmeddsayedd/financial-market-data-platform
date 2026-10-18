from datetime import date, datetime, timezone
from decimal import Decimal

from financial_data_platform.analytics.indicators import MarketIndicators
from financial_data_platform.models.market_data import MarketDataRecord
from financial_data_platform.warehouse.gold_indicator_mapping import (
    to_gold_indicator_values,
)


def test_to_gold_indicator_values():
    """Map calculated financial indicators to Gold column names."""

    record = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 9),
        open=Decimal("100.00"),
        high=Decimal("105.00"),
        low=Decimal("98.00"),
        close=Decimal("102.00"),
        volume=1000,
        source="twelve_data",
        extracted_at=datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    )

    indicators = MarketIndicators(
        record=record,
        price_change=Decimal("2.00"),
        daily_return_pct=Decimal("2.00"),
        sma_7=Decimal("101.50"),
        sma_30=None,
    )

    result = to_gold_indicator_values(indicators)

    assert result == {
        "price_change": Decimal("2.00"),
        "daily_return_pct": Decimal("2.00"),
        "sma_7": Decimal("101.50"),
        "sma_30": None,
    }   