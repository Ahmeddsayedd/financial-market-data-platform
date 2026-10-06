from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from collections import defaultdict
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

def _validate_symbol_path_component(symbol: str) -> None:
    if not symbol or "/" in symbol or "\\" in symbol or ".." in symbol:
        raise ValueError("symbol must be a safe path component")

class SilverWriter:
    """Persist validated canonical market data to the Silver Parquet layer."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    def write(self, records: list[MarketDataRecord]) -> list[Path]:
        for record in records:
            _validate_symbol_path_component(record.symbol)
            
        partitions: dict[tuple[str, int], list[MarketDataRecord]] = defaultdict(list)

        for record in records:
            partition_key = (record.symbol, record.observation_date.year)
            partitions[partition_key].append(record)

        paths: list[Path] = []

        for (symbol, year), partition_records in sorted(partitions.items()):
            path = (
                self.base_dir
                / f"symbol={symbol}"
                / f"year={year}"
                / "data.parquet"
            )
            path.parent.mkdir(parents=True, exist_ok=True)

            rows = [
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
                for record in partition_records
            ]

            if path.exists():
                existing_table = pq.ParquetFile(path).read()
                existing_rows = existing_table.to_pylist()
            else:
                existing_rows = []

            rows_by_identity = {
                (row["symbol"], row["observation_date"]): row
                for row in existing_rows
            }

            for row in rows:
                identity = (row["symbol"], row["observation_date"])
                rows_by_identity[identity] = row

            merged_rows = sorted(
                rows_by_identity.values(),
                key=lambda row: (row["symbol"], row["observation_date"]),
            )

            table = pa.Table.from_pylist(
                merged_rows,
                schema=SILVER_SCHEMA,
            )

            pq.write_table(table, path)
            paths.append(path)

        return paths