from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from financial_data_platform.models.market_data import MarketDataRecord


SILVER_SCHEMA = pa.schema(
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

class SilverWriter:
    """Persist validated canonical market data to the Silver Parquet layer."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    def write(self, records: list[MarketDataRecord]) -> list[Path]:
        record = records[0]

        path = (
            self.base_dir
            / f"symbol={record.symbol}"
            / f"year={record.observation_date.year}"
            / "data.parquet"
        )
        path.parent.mkdir(parents=True, exist_ok=True)

        table = pa.Table.from_pylist(
            [
                {
                    "symbol": record.symbol,
                    "observation_date": record.observation_date,
                    "open": record.open,
                    "high": record.high,
                    "low": record.low,
                    "close": record.close,
                    "volume": record.volume,
                    "source": record.source,
                    "extracted_at": record.extracted_at,
                }
            ],
            schema=SILVER_SCHEMA,
        )

        pq.write_table(table, path)

        return [path]