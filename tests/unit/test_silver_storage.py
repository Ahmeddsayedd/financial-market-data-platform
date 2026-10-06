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