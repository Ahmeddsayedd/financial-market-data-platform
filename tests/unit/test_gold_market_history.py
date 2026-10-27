from unittest.mock import MagicMock

from financial_data_platform.warehouse.gold_market_history import (
    read_gold_market_records,
)
from datetime import date, datetime, timezone
from decimal import Decimal
from financial_data_platform.models.market_data import MarketDataRecord


def test_read_gold_market_records_queries_one_asset():
    """Retrieve historical Gold observations for one source and symbol."""

    cursor = MagicMock()
    cursor.fetchall.return_value = []

    result = read_gold_market_records(
        cursor=cursor,
        source="twelve_data",
        symbol="AAPL",
    )

    assert result == []

    sql, params = cursor.execute.call_args.args

    assert "fact_market_metrics" in sql
    assert "dim_asset" in sql
    assert "dim_date" in sql
    assert "ORDER BY" in sql.upper()

    assert params == ("twelve_data", "AAPL")


def test_read_gold_market_records_reconstructs_market_data():
    """Convert PostgreSQL rows into canonical MarketDataRecord objects."""

    extracted_at = datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc)

    cursor = MagicMock()
    cursor.fetchall.return_value = [
        (
            "AAPL",
            date(2026, 10, 9),
            Decimal("100.00000000"),
            Decimal("105.00000000"),
            Decimal("98.00000000"),
            Decimal("102.00000000"),
            1000,
            "twelve_data",
            extracted_at,
        )
    ]

    result = read_gold_market_records(
        cursor=cursor,
        source="twelve_data",
        symbol="AAPL",
    )

    assert result == [
        MarketDataRecord(
            symbol="AAPL",
            observation_date=date(2026, 10, 9),
            open=Decimal("100.00000000"),
            high=Decimal("105.00000000"),
            low=Decimal("98.00000000"),
            close=Decimal("102.00000000"),
            volume=1000,
            source="twelve_data",
            extracted_at=extracted_at,
        )
    ]
