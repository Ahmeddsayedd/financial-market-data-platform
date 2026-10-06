from datetime import datetime
from pathlib import Path

from financial_data_platform.providers.twelve_data.client import TwelveDataClient
from financial_data_platform.storage.raw import RawResponseWriter


def ingest_daily_market_data(
    *,
    symbol: str,
    client: TwelveDataClient,
    raw_writer: RawResponseWriter,
    extracted_at: datetime,
) -> Path:
    """Fetch daily market data and preserve the provider response in raw storage."""
    payload = client.fetch_daily_time_series(symbol)

    raw_path = raw_writer.write(
        payload,
        provider="twelve_data",
        symbol=symbol,
        extracted_at=extracted_at,
    )

    return raw_path