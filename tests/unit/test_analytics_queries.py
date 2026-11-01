"""Unit tests for read-only dashboard queries; no database required."""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from financial_data_platform.analytics.queries import (
    Asset,
    IndicatorObservation,
    MarketObservation,
    get_indicator_history,
    get_market_history,
    list_assets,
)


def fake_connection(rows):
    connection = MagicMock()
    cursor = (
        connection.__enter__.return_value.cursor.return_value.__enter__.return_value
    )
    cursor.fetchall.return_value = rows
    return connection, cursor


def test_list_assets_returns_typed_records_and_read_only_transaction():
    connection, cursor = fake_connection(
        [(1, "twelve_data", "AAPL", "Apple", "NASDAQ", "USD", "Technology")]
    )
    with patch(
        "financial_data_platform.analytics.queries.connect_to_database",
        return_value=connection,
    ):
        result = list_assets("twelve_data")

    assert result == [
        Asset(1, "twelve_data", "AAPL", "Apple", "NASDAQ", "USD", "Technology")
    ]
    assert cursor.execute.call_args_list[0].args == ("SET TRANSACTION READ ONLY",)
    assert cursor.execute.call_args_list[1].args[1] == ("twelve_data",)
    assert "WHERE source = %s" in cursor.execute.call_args_list[1].args[0]
    assert "ORDER BY source ASC, symbol ASC" in cursor.execute.call_args_list[1].args[0]
    assert cursor.execute.call_count == 2


def test_list_assets_without_filter_and_empty_results():
    connection, cursor = fake_connection([])
    with patch(
        "financial_data_platform.analytics.queries.connect_to_database",
        return_value=connection,
    ):
        assert list_assets() == []
    assert cursor.execute.call_args_list[1].args[1] == ()
    assert "WHERE source = %s" not in cursor.execute.call_args_list[1].args[0]


def test_market_history_maps_decimal_values_and_filters():
    day = date(2026, 10, 9)
    extracted = datetime(2026, 10, 9, 18, tzinfo=timezone.utc)
    values = (
        day,
        Decimal("100"),
        Decimal("105"),
        Decimal("98"),
        Decimal("102"),
        1000,
        extracted,
        Decimal("2"),
        Decimal("2"),
        None,
        Decimal("101"),
    )
    connection, cursor = fake_connection([values])
    with patch(
        "financial_data_platform.analytics.queries.connect_to_database",
        return_value=connection,
    ):
        result = get_market_history(
            "twelve_data", "AAPL", start_date=day, end_date=day, limit=10
        )
    assert result == [MarketObservation(*values)]
    assert cursor.execute.call_args_list[0].args == ("SET TRANSACTION READ ONLY",)
    assert cursor.execute.call_args_list[1].args[1] == (
        "twelve_data",
        "AAPL",
        day,
        day,
        day,
        day,
        10,
    )
    assert "ORDER BY d.full_date ASC" in cursor.execute.call_args_list[1].args[0]


def test_indicator_history_returns_persisted_values_and_nulls():
    day = date(2026, 10, 9)
    connection, cursor = fake_connection(
        [(day, Decimal("2"), None, None, Decimal("101"))]
    )
    with patch(
        "financial_data_platform.analytics.queries.connect_to_database",
        return_value=connection,
    ):
        result = get_indicator_history("twelve_data", "AAPL")
    assert result == [
        IndicatorObservation(day, Decimal("2"), None, None, Decimal("101"))
    ]
    assert cursor.execute.call_args_list[1].args[1][-1] == 5000


@pytest.mark.parametrize(
    "kwargs",
    [
        {"source": "", "symbol": "AAPL"},
        {"source": "twelve_data", "symbol": "  "},
        {"source": "twelve_data", "symbol": "AAPL", "start_date": "2026-10-09"},
        {
            "source": "twelve_data",
            "symbol": "AAPL",
            "end_date": datetime.now(timezone.utc),
        },
        {
            "source": "twelve_data",
            "symbol": "AAPL",
            "start_date": date(2026, 10, 10),
            "end_date": date(2026, 10, 9),
        },
        {"source": "twelve_data", "symbol": "AAPL", "limit": 0},
        {"source": "twelve_data", "symbol": "AAPL", "limit": 5001},
        {"source": "twelve_data", "symbol": "AAPL", "limit": True},
    ],
)
def test_invalid_filters_fail_before_connecting(kwargs):
    with patch(
        "financial_data_platform.analytics.queries.connect_to_database"
    ) as connect:
        with pytest.raises(ValueError):
            get_market_history(**kwargs)
        with pytest.raises(ValueError):
            get_indicator_history(**kwargs)
    connect.assert_not_called()


def test_invalid_asset_filter_fails_before_connecting():
    with patch(
        "financial_data_platform.analytics.queries.connect_to_database"
    ) as connect:
        with pytest.raises(ValueError):
            list_assets(" ")
    connect.assert_not_called()


def test_connection_errors_propagate():
    with patch(
        "financial_data_platform.analytics.queries.connect_to_database",
        side_effect=OSError("offline"),
    ):
        with pytest.raises(OSError, match="offline"):
            list_assets()
