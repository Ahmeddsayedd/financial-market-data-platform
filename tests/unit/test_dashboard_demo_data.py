"""Database-independent safety and fixture-contract tests for M8 demo records."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from financial_data_platform.dashboard import demo_data


def test_demo_symbol_is_unique_shaped():
    symbol = demo_data.new_demo_symbol()
    assert len(symbol) == 16
    assert symbol.startswith("DEMO")
    demo_data._validate_symbol(symbol)


@pytest.mark.parametrize("symbol", ["AAPL", "DEMO../BAD", "demo123", "DEMO123", ""])
def test_demo_rejects_unowned_symbols(symbol):
    with pytest.raises(ValueError):
        demo_data._validate_symbol(symbol)


def test_demo_has_35_dates_with_7_and_30_day_coverage():
    closes = [demo_data._prices(i)[3] for i in range(demo_data.DEMO_DAYS)]
    assert demo_data.FIRST_DATE == date(2026, 9, 1)
    assert len(closes) == 35
    assert demo_data._indicators(0, closes) == (None, None, None, None)
    assert demo_data._indicators(5, closes)[2] is None
    assert demo_data._indicators(6, closes)[2] is not None
    assert demo_data._indicators(28, closes)[3] is None
    assert demo_data._indicators(29, closes)[3] is not None
    assert demo_data._indicators(1, closes)[1] is not None
    assert demo_data._indicators(1, closes)[1].as_tuple().exponent == -8
    for index in range(35):
        _, high, low, close = demo_data._prices(index)
        assert low <= close <= high


def test_run_ids_are_stable_distinct_and_demo_scoped():
    symbol = "DEMO012345ABCDEF"
    assert demo_data._run_id(symbol, "success") == demo_data._run_id(symbol, "success")
    assert demo_data._run_id(symbol, "failed") != demo_data._run_id(symbol, "success")
    assert demo_data._run_id("DEMO123456ABCDEF", "success") != demo_data._run_id(
        symbol, "success"
    )


def test_seed_rejects_wrong_configured_database_before_writes():
    connection = MagicMock()
    cursor = (
        connection.__enter__.return_value.cursor.return_value.__enter__.return_value
    )
    with (
        patch.object(demo_data, "connect_to_database", return_value=connection),
        patch.object(
            demo_data,
            "get_database_config",
            return_value={"dbname": "financial_market"},
        ),
    ):
        with pytest.raises(ValueError, match="financial_market_test"):
            demo_data.seed_demo_data("DEMO012345ABCDEF")
    cursor.execute.assert_not_called()


def test_cleanup_rejects_wrong_connected_database_before_deleting():
    connection = MagicMock()
    cursor = (
        connection.__enter__.return_value.cursor.return_value.__enter__.return_value
    )
    cursor.fetchone.return_value = ("financial_market",)
    with (
        patch.object(demo_data, "connect_to_database", return_value=connection),
        patch.object(
            demo_data,
            "get_database_config",
            return_value={"dbname": demo_data.TEST_DATABASE},
        ),
    ):
        with pytest.raises(ValueError, match="Connected database"):
            demo_data.cleanup_demo_data("DEMO012345ABCDEF")
    cursor.execute.assert_called_once_with("SELECT current_database()")


def test_demo_zero_return_is_preserved_as_real_zero():
    closes = [Decimal("100.00000000")] * demo_data.DEMO_DAYS
    change, pct, *_ = demo_data._indicators(1, closes)
    assert change == Decimal("0E-8")
    assert pct == Decimal("0E-8")
