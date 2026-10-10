from datetime import date, datetime, timezone
from decimal import Decimal

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from financial_data_platform.models.market_data import MarketDataRecord
from financial_data_platform.storage.silver import SILVER_SCHEMA
from financial_data_platform.storage.silver_reader import read_silver_parquet


def test_read_silver_parquet_preserves_canonical_types(tmp_path):
    """Read Silver Parquet without losing financial precision."""

    parquet_path = tmp_path / "data.parquet"

    expected = MarketDataRecord(
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

    table = pa.Table.from_pylist(
        [vars(expected)],
        schema=SILVER_SCHEMA,
    )
    pq.write_table(table, parquet_path)

    actual = read_silver_parquet(parquet_path)

    assert actual == [expected]
    assert isinstance(actual[0].close, Decimal)
    assert isinstance(actual[0].observation_date, date)
    assert actual[0].extracted_at.utcoffset().total_seconds() == 0


def test_read_silver_parquet_returns_multiple_observations(tmp_path):
    """Read every observation from a Silver Parquet file."""

    parquet_path = tmp_path / "data.parquet"

    records = [
        MarketDataRecord(
            symbol="AAPL",
            observation_date=date(2026, 10, 8),
            open=Decimal("250.00000000"),
            high=Decimal("255.00000000"),
            low=Decimal("248.00000000"),
            close=Decimal("253.00000000"),
            volume=1000000,
            source="twelve_data",
            extracted_at=datetime(
                2026, 10, 9, 18, 0, tzinfo=timezone.utc
            ),
        ),
        MarketDataRecord(
            symbol="AAPL",
            observation_date=date(2026, 10, 9),
            open=Decimal("253.00000000"),
            high=Decimal("258.00000000"),
            low=Decimal("251.00000000"),
            close=Decimal("256.00000000"),
            volume=1200000,
            source="twelve_data",
            extracted_at=datetime(
                2026, 10, 9, 18, 0, tzinfo=timezone.utc
            ),
        ),
    ]

    table = pa.Table.from_pylist(
        [vars(record) for record in records],
        schema=SILVER_SCHEMA,
    )
    pq.write_table(table, parquet_path)

    actual = read_silver_parquet(parquet_path)

    assert actual == records
    assert len(actual) == 2


def test_read_silver_parquet_handles_empty_file(tmp_path):
    """An empty Silver Parquet file returns no records."""

    parquet_path = tmp_path / "data.parquet"

    empty_table = pa.Table.from_pylist(
        [],
        schema=SILVER_SCHEMA,
    )
    pq.write_table(empty_table, parquet_path)

    actual = read_silver_parquet(parquet_path)

    assert actual == []


def test_read_silver_parquet_rejects_incompatible_schema(tmp_path):
    """Reject Parquet files that do not match the Silver schema."""

    parquet_path = tmp_path / "data.parquet"

    invalid_table = pa.table(
        {
            "symbol": ["AAPL"],
            "observation_date": [date(2026, 10, 9)],
        }
    )
    pq.write_table(invalid_table, parquet_path)

    with pytest.raises(ValueError, match="Incompatible Silver schema"):
        read_silver_parquet(parquet_path)


def test_read_silver_parquet_rejects_float_prices(tmp_path):
    """Reject floating-point prices in place of exact decimals."""

    parquet_path = tmp_path / "data.parquet"

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

    table = pa.Table.from_pylist(
        [vars(record)],
        schema=SILVER_SCHEMA,
    )

    # Deliberately replace the exact decimal open column with float64.
    float_open = pa.array(
        [250.12345678],
        type=pa.float64(),
    )
    invalid_table = table.set_column(
        2,
        pa.field("open", pa.float64(), nullable=False),
        float_open,
    )

    pq.write_table(invalid_table, parquet_path)

    with pytest.raises(ValueError, match="Incompatible Silver schema"):
        read_silver_parquet(parquet_path)


def test_read_silver_parquet_rejects_missing_file(tmp_path):
    """Report a missing Silver Parquet file clearly."""

    missing_path = tmp_path / "missing.parquet"

    with pytest.raises(FileNotFoundError):
        read_silver_parquet(missing_path)


def test_read_silver_parquet_inside_hive_partition_directories(tmp_path):
    """Read a physical Parquet file without inferring partition columns."""
    from datetime import date, datetime, timezone
    from decimal import Decimal

    from financial_data_platform.models.market_data import MarketDataRecord
    from financial_data_platform.storage.silver import SilverWriter
    from financial_data_platform.storage.silver_reader import read_silver_parquet

    record = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 9),
        open=Decimal("250.00000000"),
        high=Decimal("255.00000000"),
        low=Decimal("248.00000000"),
        close=Decimal("253.00000000"),
        volume=1000000,
        source="twelve_data",
        extracted_at=datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc),
    )

    writer = SilverWriter(base_dir=tmp_path)
    paths = writer.write([record])

    assert len(paths) == 1

    loaded_records = read_silver_parquet(paths[0])

    assert loaded_records == [record]