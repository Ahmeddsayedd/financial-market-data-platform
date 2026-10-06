from datetime import date, datetime, timezone
from decimal import Decimal

import pyarrow.parquet as pq
import pyarrow as pa

from financial_data_platform.models.market_data import MarketDataRecord
from financial_data_platform.storage.silver import SilverWriter


def test_writes_single_record_to_symbol_year_partition(tmp_path):
    record = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 5),
        open=Decimal("250.00"),
        high=Decimal("255.00"),
        low=Decimal("249.00"),
        close=Decimal("254.00"),
        volume=1_000_000,
        source="twelve_data",
        extracted_at=datetime(2026, 10, 6, 18, 30, 45, tzinfo=timezone.utc),
    )

    writer = SilverWriter(tmp_path)

    paths = writer.write([record])

    expected_path = (
        tmp_path
        / "symbol=AAPL"
        / "year=2026"
        / "data.parquet"
    )

    assert paths == [expected_path]
    assert expected_path.exists()

    table = pq.ParquetFile(expected_path).read()

    assert table.num_rows == 1



def test_writes_records_with_explicit_silver_schema(tmp_path):
    record = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 5),
        open=Decimal("250.12345678"),
        high=Decimal("255.12345678"),
        low=Decimal("249.12345678"),
        close=Decimal("254.12345678"),
        volume=1_000_000,
        source="twelve_data",
        extracted_at=datetime(2026, 10, 6, 18, 30, 45, tzinfo=timezone.utc),
    )

    writer = SilverWriter(tmp_path)

    paths = writer.write([record])

    table = pq.ParquetFile(paths[0]).read()

    expected_schema = pa.schema(
        [
            pa.field("symbol", pa.string(), nullable=False),
            pa.field("observation_date", pa.date32(), nullable=False),
            pa.field("open", pa.decimal128(20, 8), nullable=False),
            pa.field("high", pa.decimal128(20, 8), nullable=False),
            pa.field("low", pa.decimal128(20, 8), nullable=False),
            pa.field("close", pa.decimal128(20, 8), nullable=False),
            pa.field("volume", pa.int64(), nullable=False),
            pa.field("source", pa.string(), nullable=False),
            pa.field(
                "extracted_at",
                pa.timestamp("us", tz="UTC"),
                nullable=False,
            ),
        ]
    )

    assert table.schema == expected_schema



def test_writes_multiple_records_to_same_partition(tmp_path):
    records = [
        MarketDataRecord(
            symbol="AAPL",
            observation_date=date(2026, 10, 5),
            open=Decimal("250.00"),
            high=Decimal("255.00"),
            low=Decimal("249.00"),
            close=Decimal("254.00"),
            volume=1_000_000,
            source="twelve_data",
            extracted_at=datetime(
                2026, 10, 6, 18, 30, 45, tzinfo=timezone.utc
            ),
        ),
        MarketDataRecord(
            symbol="AAPL",
            observation_date=date(2026, 10, 6),
            open=Decimal("254.00"),
            high=Decimal("258.00"),
            low=Decimal("252.00"),
            close=Decimal("257.00"),
            volume=1_100_000,
            source="twelve_data",
            extracted_at=datetime(
                2026, 10, 7, 18, 30, 45, tzinfo=timezone.utc
            ),
        ),
    ]

    writer = SilverWriter(tmp_path)

    paths = writer.write(records)

    expected_path = (
        tmp_path
        / "symbol=AAPL"
        / "year=2026"
        / "data.parquet"
    )

    assert paths == [expected_path]

    table = pq.ParquetFile(expected_path).read()

    assert table.num_rows == 2
    assert table.column("observation_date").to_pylist() == [
        date(2026, 10, 5),
        date(2026, 10, 6),
    ]



def test_writes_records_to_multiple_symbol_year_partitions(tmp_path):
    records = [
        MarketDataRecord(
            symbol="AAPL",
            observation_date=date(2025, 12, 31),
            open=Decimal("200.00"),
            high=Decimal("205.00"),
            low=Decimal("198.00"),
            close=Decimal("204.00"),
            volume=900_000,
            source="twelve_data",
            extracted_at=datetime(
                2026, 1, 2, 12, 0, tzinfo=timezone.utc
            ),
        ),
        MarketDataRecord(
            symbol="AAPL",
            observation_date=date(2026, 1, 2),
            open=Decimal("205.00"),
            high=Decimal("208.00"),
            low=Decimal("203.00"),
            close=Decimal("207.00"),
            volume=1_000_000,
            source="twelve_data",
            extracted_at=datetime(
                2026, 1, 3, 12, 0, tzinfo=timezone.utc
            ),
        ),
        MarketDataRecord(
            symbol="MSFT",
            observation_date=date(2026, 1, 2),
            open=Decimal("450.00"),
            high=Decimal("455.00"),
            low=Decimal("448.00"),
            close=Decimal("454.00"),
            volume=800_000,
            source="twelve_data",
            extracted_at=datetime(
                2026, 1, 3, 12, 0, tzinfo=timezone.utc
            ),
        ),
    ]

    writer = SilverWriter(tmp_path)

    paths = writer.write(records)

    expected_paths = [
        tmp_path / "symbol=AAPL" / "year=2025" / "data.parquet",
        tmp_path / "symbol=AAPL" / "year=2026" / "data.parquet",
        tmp_path / "symbol=MSFT" / "year=2026" / "data.parquet",
    ]

    assert paths == expected_paths

    for path in expected_paths:
        assert path.exists()
        assert pq.ParquetFile(path).read().num_rows == 1



def test_preserves_existing_records_when_writing_to_existing_partition(tmp_path):
    writer = SilverWriter(tmp_path)

    first_record = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 5),
        open=Decimal("250.00"),
        high=Decimal("255.00"),
        low=Decimal("249.00"),
        close=Decimal("254.00"),
        volume=1_000_000,
        source="twelve_data",
        extracted_at=datetime(
            2026, 10, 6, 18, 30, 45, tzinfo=timezone.utc
        ),
    )

    second_record = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 6),
        open=Decimal("254.00"),
        high=Decimal("258.00"),
        low=Decimal("252.00"),
        close=Decimal("257.00"),
        volume=1_100_000,
        source="twelve_data",
        extracted_at=datetime(
            2026, 10, 7, 18, 30, 45, tzinfo=timezone.utc
        ),
    )

    writer.write([first_record])
    paths = writer.write([second_record])

    table = pq.ParquetFile(paths[0]).read()

    assert table.num_rows == 2
    assert table.column("observation_date").to_pylist() == [
        date(2026, 10, 5),
        date(2026, 10, 6),
    ]



def test_replaces_existing_record_with_same_identity(tmp_path):
    writer = SilverWriter(tmp_path)

    original_record = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 5),
        open=Decimal("250.00"),
        high=Decimal("255.00"),
        low=Decimal("249.00"),
        close=Decimal("254.00"),
        volume=1_000_000,
        source="twelve_data",
        extracted_at=datetime(
            2026, 10, 6, 18, 30, 45, tzinfo=timezone.utc
        ),
    )

    corrected_record = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 5),
        open=Decimal("250.00"),
        high=Decimal("260.00"),
        low=Decimal("249.00"),
        close=Decimal("259.00"),
        volume=1_200_000,
        source="twelve_data",
        extracted_at=datetime(
            2026, 10, 7, 18, 30, 45, tzinfo=timezone.utc
        ),
    )

    writer.write([original_record])
    paths = writer.write([corrected_record])

    table = pq.ParquetFile(paths[0]).read()

    assert table.num_rows == 1

    row = table.to_pylist()[0]

    assert row["symbol"] == "AAPL"
    assert row["observation_date"] == date(2026, 10, 5)
    assert row["close"] == Decimal("259.00000000")
    assert row["volume"] == 1_200_000
    assert row["extracted_at"] == datetime(
        2026, 10, 7, 18, 30, 45, tzinfo=timezone.utc
    )



def test_repeated_identical_write_is_idempotent(tmp_path):
    record = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 5),
        open=Decimal("250.00"),
        high=Decimal("255.00"),
        low=Decimal("249.00"),
        close=Decimal("254.00"),
        volume=1_000_000,
        source="twelve_data",
        extracted_at=datetime(
            2026, 10, 6, 18, 30, 45, tzinfo=timezone.utc
        ),
    )

    writer = SilverWriter(tmp_path)

    first_paths = writer.write([record])
    second_paths = writer.write([record])

    assert second_paths == first_paths

    table = pq.ParquetFile(first_paths[0]).read()

    assert table.num_rows == 1
    assert table.column("observation_date").to_pylist() == [
        date(2026, 10, 5)
    ]


def test_empty_input_writes_nothing(tmp_path):
    writer = SilverWriter(tmp_path)

    paths = writer.write([])

    assert paths == []
    assert list(tmp_path.rglob("*.parquet")) == []