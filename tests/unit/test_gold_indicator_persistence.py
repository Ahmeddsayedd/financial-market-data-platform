from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import (
    MagicMock,
    patch,
)
import pytest
from financial_data_platform.warehouse.gold_indicator_persistence import (
    persist_market_indicators,
    update_gold_indicators,
    calculate_and_persist_indicators,
    load_market_records_with_indicators,
)
from financial_data_platform.analytics.indicators import MarketIndicators
from financial_data_platform.models.market_data import MarketDataRecord

def test_update_gold_indicators_updates_existing_fact():
    """Update indicator columns without modifying OHLCV data."""

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

    cursor = MagicMock()
    cursor.fetchone.return_value = (record.extracted_at,)
    cursor.rowcount = 1

    updated = update_gold_indicators(
        cursor=cursor,
        asset_key=42,
        indicators=indicators,
    )

    assert updated is True

    sql, params = cursor.execute.call_args.args

    assert "UPDATE fact_market_metrics" in sql
    assert "price_change" in sql
    assert "daily_return_pct" in sql
    assert "sma_7" in sql
    assert "sma_30" in sql

    assert "open =" not in sql
    assert "high =" not in sql
    assert "low =" not in sql
    assert "close =" not in sql
    assert "volume =" not in sql
    assert "AND extracted_at = %s" in sql
    assert "SET extracted_at =" not in sql

    assert params == (
        Decimal("2.00"),
        Decimal("2.00"),
        Decimal("101.50"),
        None,
        42,
        20261009,
        record.extracted_at,
        Decimal("2.00"),
        Decimal("2.00"),
        Decimal("101.50"),
        None,
    )


def test_update_gold_indicators_skips_identical_values():
    """Do not update a fact when all indicator values are unchanged."""

    from unittest.mock import patch

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

    cursor = MagicMock()
    cursor.fetchone.return_value = (record.extracted_at,)
    cursor.rowcount = 0

    updated = update_gold_indicators(
        cursor=cursor,
        asset_key=42,
        indicators=indicators,
    )

    assert updated is False


def test_update_gold_indicators_uses_null_safe_change_detection():
    """Only update indicators when their values actually differ."""

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

    cursor = MagicMock()
    cursor.fetchone.return_value = (record.extracted_at,)
    cursor.rowcount = 0

    update_gold_indicators(
        cursor=cursor,
        asset_key=42,
        indicators=indicators,
    )

    sql, _ = cursor.execute.call_args.args

    assert "IS DISTINCT FROM" in sql.upper()


def test_update_gold_indicators_requires_matching_extraction_timestamp():
    """Prevent stale observations from overwriting newer Gold indicators."""

    from unittest.mock import MagicMock

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
        sma_7=None,
        sma_30=None,
    )

    cursor = MagicMock()
    cursor.fetchone.return_value = (record.extracted_at,)
    cursor.rowcount = 0

    update_gold_indicators(
        cursor=cursor,
        asset_key=42,
        indicators=indicators,
    )

    sql, params = cursor.execute.call_args.args

    assert "AND extracted_at = %s" in sql
    assert record.extracted_at in params


def test_persist_market_indicators_updates_existing_fact():
    """Persist calculated indicators for an existing Gold asset."""

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
        sma_7=None,
        sma_30=None,
    )

    cursor = MagicMock()

    with (
        patch(
            "financial_data_platform.warehouse.gold_indicator_persistence.ensure_asset",
            return_value=42,
        ) as mock_asset,
        patch(
            "financial_data_platform.warehouse.gold_indicator_persistence.update_gold_indicators",
            return_value=True,
        ) as mock_update,
    ):
        result = persist_market_indicators(cursor, [indicators])

    mock_asset.assert_called_once_with(
        cursor,
        source="twelve_data",
        symbol="AAPL",
    )
    mock_update.assert_called_once_with(
        cursor=cursor,
        asset_key=42,
        indicators=indicators,
    )
    assert result == {"updated": 1, "unchanged": 0}


def test_persist_market_indicators_counts_mixed_outcomes():
    """Count updated and skipped indicator writes separately."""

    from dataclasses import replace

    first_record = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 8),
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

    second_record = replace(
        first_record,
        observation_date=date(2026, 10, 9),
    )

    first = MarketIndicators(
        record=first_record,
        price_change=None,
        daily_return_pct=None,
        sma_7=None,
        sma_30=None,
    )

    second = replace(
        first,
        record=second_record,
        price_change=Decimal("2.00"),
        daily_return_pct=Decimal("2.00"),
    )

    cursor = MagicMock()

    with (
        patch(
            "financial_data_platform.warehouse.gold_indicator_persistence.ensure_asset",
            return_value=42,
        ),
        patch(
            "financial_data_platform.warehouse.gold_indicator_persistence.update_gold_indicators",
            side_effect=[True, False],
        ) as mock_update,
    ):
        result = persist_market_indicators(cursor, [first, second])

    assert result == {"updated": 1, "unchanged": 1}
    assert mock_update.call_count == 2


def test_calculate_and_persist_indicators_connects_analytics_to_gold():
    """Calculate indicators from Gold history and pass them to persistence."""

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

    cursor = MagicMock()
    expected_counts = {"updated": 1, "unchanged": 0}

    with (
        patch(
            "financial_data_platform.warehouse.gold_indicator_persistence.read_gold_market_records",
            return_value=[record],
        ) as mock_history,
        patch(
            "financial_data_platform.warehouse.gold_indicator_persistence.persist_market_indicators",
            return_value=expected_counts,
        ) as mock_persist,
    ):
        result = calculate_and_persist_indicators(cursor, [record])

    mock_history.assert_called_once_with(
        cursor=cursor,
        source="twelve_data",
        symbol="AAPL",
    )

    mock_persist.assert_called_once()

    passed_cursor, calculated = mock_persist.call_args.args

    assert passed_cursor is cursor
    assert len(calculated) == 1
    assert calculated[0].record == record
    assert calculated[0].price_change is None
    assert calculated[0].daily_return_pct is None
    assert result == expected_counts


def test_calculate_and_persist_indicators_uses_gold_history():
    """Calculate indicators using historical Gold records."""

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

    cursor = MagicMock()

    with (
        patch(
            "financial_data_platform.warehouse.gold_indicator_persistence.read_gold_market_records",
            return_value=[record],
        ) as mock_history,
        patch(
            "financial_data_platform.warehouse.gold_indicator_persistence.persist_market_indicators",
            return_value={"updated": 1, "unchanged": 0},
        ) as mock_persist,
    ):
        calculate_and_persist_indicators(cursor, [record])

    mock_history.assert_called_once_with(
        cursor=cursor,
        source="twelve_data",
        symbol="AAPL",
    )

    calculated = mock_persist.call_args.args[1]

    assert len(calculated) == 1
    assert calculated[0].record == record


def test_calculate_and_persist_indicators_sma_7_across_batches():
    """Calculate SMA 7 using existing Gold history."""

    base = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 1),
        open=Decimal("100"),
        high=Decimal("110"),
        low=Decimal("90"),
        close=Decimal("101"),
        volume=1000,
        source="twelve_data",
        extracted_at=datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    )

    from dataclasses import replace

    history = [
        replace(
            base,
            observation_date=base.observation_date + timedelta(days=index),
            close=Decimal(101 + index),
        )
        for index in range(7)
    ]

    cursor = MagicMock()

    with (
        patch(
            "financial_data_platform.warehouse.gold_indicator_persistence.read_gold_market_records",
            return_value=history,
        ) as mock_history,
        patch(
            "financial_data_platform.warehouse.gold_indicator_persistence.persist_market_indicators",
            return_value={"updated": 7, "unchanged": 0},
        ) as mock_persist,
    ):
        calculate_and_persist_indicators(cursor, [history[-1]])

    mock_history.assert_called_once_with(
        cursor=cursor,
        source="twelve_data",
        symbol="AAPL",
    )

    calculated = mock_persist.call_args.args[1]

    assert len(calculated) == 7
    assert all(item.sma_7 is None for item in calculated[:6])
    assert calculated[6].sma_7 == Decimal("104")


def test_load_market_records_with_indicators_rolls_back_on_failure():
    """Roll back market loading if indicator persistence fails."""

    import psycopg

    connection = MagicMock()

    with (
        patch(
            "financial_data_platform.warehouse.gold_indicator_persistence.connect_to_database",
            return_value=connection,
        ),
        patch(
            "financial_data_platform.warehouse.gold_indicator_persistence.load_market_batch",
            return_value={
                "inserted": 1,
                "updated": 0,
                "unchanged": 0,
                "rejected": 0,
            },
        ),
        patch(
            "financial_data_platform.warehouse.gold_indicator_persistence.calculate_and_persist_indicators",
            side_effect=psycopg.DatabaseError("Indicator persistence failed"),
        ),
    ):
        with pytest.raises(
            psycopg.DatabaseError,
            match="Indicator persistence failed",
        ):
            load_market_records_with_indicators([])

    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()
    connection.close.assert_called_once()


def test_load_market_records_with_indicators_commits_on_success():
    """Commit market facts and indicators in one transaction."""

    connection = MagicMock()

    expected_market_counts = {
        "inserted": 2,
        "updated": 0,
        "unchanged": 0,
        "rejected": 0,
    }
    expected_indicator_counts = {
        "updated": 1,
        "unchanged": 1,
    }

    with (
        patch(
            "financial_data_platform.warehouse.gold_indicator_persistence.connect_to_database",
            return_value=connection,
        ),
        patch(
            "financial_data_platform.warehouse.gold_indicator_persistence.load_market_batch",
            return_value=expected_market_counts,
        ) as mock_market,
        patch(
            "financial_data_platform.warehouse.gold_indicator_persistence.calculate_and_persist_indicators",
            return_value=expected_indicator_counts,
        ) as mock_indicators,
    ):
        result = load_market_records_with_indicators([])

    cursor = connection.cursor.return_value.__enter__.return_value

    mock_market.assert_called_once_with(cursor, [])
    mock_indicators.assert_called_once_with(cursor, [])

    assert result == {
        "market": expected_market_counts,
        "indicators": expected_indicator_counts,
    }

    connection.commit.assert_called_once()
    connection.rollback.assert_not_called()
    connection.close.assert_called_once()


def test_load_market_records_with_indicators_recalculates_after_correction():
    """Recalculate indicators after a market correction is loaded."""

    record = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 9),
        open=Decimal("100.00"),
        high=Decimal("110.00"),
        low=Decimal("98.00"),
        close=Decimal("104.00"),
        volume=1000,
        source="twelve_data",
        extracted_at=datetime(
            2026, 10, 9, 19, 0, tzinfo=timezone.utc
        ),
    )

    connection = MagicMock()
    call_order = []

    def mock_market_batch(cursor, records):
        call_order.append("market")
        return {
            "inserted": 0,
            "updated": 1,
            "unchanged": 0,
            "rejected": 0,
        }

    def mock_indicators(cursor, records):
        call_order.append("indicators")
        return {"updated": 2, "unchanged": 1}

    with (
        patch(
            "financial_data_platform.warehouse.gold_indicator_persistence.connect_to_database",
            return_value=connection,
        ),
        patch(
            "financial_data_platform.warehouse.gold_indicator_persistence.load_market_batch",
            side_effect=mock_market_batch,
        ),
        patch(
            "financial_data_platform.warehouse.gold_indicator_persistence.calculate_and_persist_indicators",
            side_effect=mock_indicators,
        ),
    ):
        result = load_market_records_with_indicators([record])

    assert call_order == ["market", "indicators"]
    assert result["market"]["updated"] == 1
    assert result["indicators"]["updated"] == 2
    connection.commit.assert_called_once()


def test_load_market_records_with_indicators_rolls_back_rejected_batch():
    """Rejected market observations abort the combined transaction."""

    connection = MagicMock()

    with (
        patch(
            "financial_data_platform.warehouse.gold_indicator_persistence.connect_to_database",
            return_value=connection,
        ),
        patch(
            "financial_data_platform.warehouse.gold_indicator_persistence.load_market_batch",
            return_value={
                "inserted": 1,
                "updated": 0,
                "unchanged": 0,
                "rejected": 1,
            },
        ),
        patch(
            "financial_data_platform.warehouse.gold_indicator_persistence.calculate_and_persist_indicators",
        ) as mock_indicators,
    ):
        with pytest.raises(ValueError, match="rejected"):
            load_market_records_with_indicators([])

    mock_indicators.assert_not_called()
    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()
    connection.close.assert_called_once()