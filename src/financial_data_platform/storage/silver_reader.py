"""Read validated market observations from Silver Parquet files."""

from pathlib import Path

import pyarrow.parquet as pq

from financial_data_platform.storage.silver import SILVER_SCHEMA
from financial_data_platform.models.market_data import MarketDataRecord


def read_silver_parquet(path: Path) -> list[MarketDataRecord]:
    """Read one Silver Parquet file into canonical market data records."""

    table = pq.ParquetFile(path).read()

    if not table.schema.equals(SILVER_SCHEMA, check_metadata=False):
        raise ValueError(
            f"Incompatible Silver schema in {path}: "
            f"expected {SILVER_SCHEMA}, got {table.schema}"
        )

    rows = table.to_pylist()

    return [
        MarketDataRecord(
            symbol=row["symbol"],
            observation_date=row["observation_date"],
            open=row["open"],
            high=row["high"],
            low=row["low"],
            close=row["close"],
            volume=row["volume"],
            source=row["source"],
            extracted_at=row["extracted_at"],
        )
        for row in rows
    ]