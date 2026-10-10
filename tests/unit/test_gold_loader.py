from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
from dataclasses import replace
import psycopg
import pytest

from financial_data_platform.warehouse.gold_loader import (
    ensure_asset,
    ensure_date,
    insert_market_fact,
    load_market_batch,
    load_market_records, 
    load_silver_file,
)
from financial_data_platform.models.market_data import MarketDataRecord


def test_ensure_asset_inserts_and_returns_asset_key():
    """Insert an asset or resolve its existing surrogate key."""

    cursor = MagicMock()
    cursor.fetchone.return_value = (42,)

    result = ensure_asset(
        cursor,
        source="twelve_data",
        symbol="AAPL",
    )

    assert result == 42

    cursor.execute.assert_called_once()

    sql, params = cursor.execute.call_args.args

    assert "INSERT INTO dim_asset" in sql
    assert "ON CONFLICT" in sql
    assert "RETURNING asset_key" in sql
    assert params == ("twelve_data", "AAPL")


def test_ensure_date_inserts_calendar_attributes():
    """Insert a trading date with consistent Gold calendar attributes."""

    cursor = MagicMock()

    result = ensure_date(cursor, date(2026, 10, 9))

    assert result == 20261009

    cursor.execute.assert_called_once()

    sql, params = cursor.execute.call_args.args

    assert "INSERT INTO dim_date" in sql
    assert "ON CONFLICT" in sql

    assert params == (
        20261009,
        date(2026, 10, 9),
        9,
        10,
        4,
        2026,
        5,
    )


def test_insert_market_fact_preserves_ohlcv_and_keys():
    """Insert a Gold fact with parameterized, precise financial values."""

    record = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 9),
        open=Decimal("250.12345678"),
        high=Decimal("255.00000000"),
        low=Decimal("248.50000000"),
        close=Decimal("253.87654321"),
        volume=1234567,
        source="twelve_data",
        extracted_at=datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc),
    )

    cursor = MagicMock()

    insert_market_fact(cursor, record, asset_key=42)

    cursor.execute.assert_called_once()
    sql, params = cursor.execute.call_args.args

    assert "INSERT INTO fact_market_metrics" in sql
    assert "%s" in sql
    assert params == (
        42,
        20261009,
        Decimal("250.12345678"),
        Decimal("255.00000000"),
        Decimal("248.50000000"),
        Decimal("253.87654321"),
        1234567,
        datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc),
    )


def test_load_market_batch_handles_empty_input():
    """An empty batch must not execute SQL or create records."""

    cursor = MagicMock()

    result = load_market_batch(cursor, [])

    assert result == {
        "inserted": 0,
        "updated": 0,
        "unchanged": 0,
        "rejected": 0,
    }

    cursor.execute.assert_not_called()


def test_load_market_batch_inserts_one_observation():
    """Load one market observation and count the insertion."""

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

    cursor = MagicMock()

    with (
        patch(
            "financial_data_platform.warehouse.gold_loader.ensure_asset",
            return_value=42,
        ) as mock_asset,
        patch(
            "financial_data_platform.warehouse.gold_loader.ensure_date",
            return_value=20261009,
        ) as mock_date,
        patch(
            "financial_data_platform.warehouse.gold_loader.insert_market_fact",
            return_value="insert",
        ) as mock_fact,
    ):
        result = load_market_batch(cursor, [record])

    assert result == {
        "inserted": 1,
        "updated": 0,
        "unchanged": 0,
        "rejected": 0,
    }

    mock_asset.assert_called_once_with(
        cursor,
        source="twelve_data",
        symbol="AAPL",
    )
    mock_date.assert_called_once_with(
        cursor,
        record.observation_date,
    )
    mock_fact.assert_called_once_with(cursor, record, 42)


def test_load_market_batch_counts_mixed_outcomes():
    """Count all four possible outcomes in one batch."""

    base_record = MarketDataRecord(
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

    records = [
        replace(
            base_record,
            observation_date=date(2026, 10, day),
        )
        for day in (6, 7, 8, 9)
    ]

    cursor = MagicMock()

    with (
        patch(
            "financial_data_platform.warehouse.gold_loader.ensure_asset",
            return_value=42,
        ),
        patch(
            "financial_data_platform.warehouse.gold_loader.ensure_date",
        ),
        patch(
            "financial_data_platform.warehouse.gold_loader.insert_market_fact",
            side_effect=["insert", "update", "unchanged", "reject"],
        ),
    ):
        result = load_market_batch(cursor, records)

    assert result == {
        "inserted": 1,
        "updated": 1,
        "unchanged": 1,
        "rejected": 1,
    }



def test_load_market_batch_propagates_database_error():
    """Stop batch processing when a PostgreSQL operation fails."""

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

    cursor = MagicMock()

    with patch(
        "financial_data_platform.warehouse.gold_loader.ensure_asset",
        side_effect=psycopg.DatabaseError("Simulated database failure"),
    ):
        with pytest.raises(psycopg.DatabaseError, match="Simulated database failure"):
            load_market_batch(cursor, [record])


def test_load_market_records_rolls_back_on_database_failure():
    """A database error must roll back the entire batch."""

    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value

    with (
        patch(
            "financial_data_platform.warehouse.gold_loader.connect_to_database",
            return_value=connection,
        ),
        patch(
            "financial_data_platform.warehouse.gold_loader.load_market_batch",
            side_effect=psycopg.DatabaseError("Simulated failure"),
        ),
    ):
        with pytest.raises(
            psycopg.DatabaseError,
            match="Simulated failure",
        ):
            load_market_records([])

    connection.rollback.assert_called_once()
    connection.commit.assert_not_called()
    connection.close.assert_called_once()


def test_load_market_records_commits_successful_batch():
    """A successful batch commits once and closes its connection."""

    connection = MagicMock()
    expected_counts = {
        "inserted": 2,
        "updated": 1,
        "unchanged": 1,
        "rejected": 0,
    }

    with (
        patch(
            "financial_data_platform.warehouse.gold_loader.connect_to_database",
            return_value=connection,
        ),
        patch(
            "financial_data_platform.warehouse.gold_loader.load_market_batch",
            return_value=expected_counts,
        ) as mock_batch,
    ):
        result = load_market_records([])

    cursor = connection.cursor.return_value.__enter__.return_value

    mock_batch.assert_called_once_with(cursor, [])
    assert result == expected_counts

    connection.commit.assert_called_once()
    connection.rollback.assert_not_called()
    connection.close.assert_called_once()


def test_load_silver_file_reads_parquet_and_loads_records():
    """Read a Silver file and pass its records to the Gold loader."""

    parquet_path = "data/silver/symbol=AAPL/year=2026/data.parquet"
    records = [MagicMock()]
    expected_counts = {
        "inserted": 1,
        "updated": 0,
        "unchanged": 0,
        "rejected": 0,
    }

    with (
        patch(
            "financial_data_platform.warehouse.gold_loader.read_silver_parquet",
            return_value=records,
        ) as mock_reader,
        patch(
            "financial_data_platform.warehouse.gold_loader.load_market_records",
            return_value=expected_counts,
        ) as mock_loader,
    ):
        result = load_silver_file(parquet_path)

    mock_reader.assert_called_once_with(parquet_path)
    mock_loader.assert_called_once_with(records)
    assert result == expected_counts