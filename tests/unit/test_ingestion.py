from datetime import datetime, timezone
from unittest.mock import Mock

from financial_data_platform.ingestion import ingest_daily_market_data


def test_ingest_daily_market_data_fetches_and_preserves_raw_response():
    payload = {
        "meta": {"symbol": "AAPL"},
        "values": [
            {
                "datetime": "2026-10-05",
                "open": "250.00",
                "high": "255.00",
                "low": "249.00",
                "close": "254.00",
                "volume": "50000000",
            }
        ],
        "status": "ok",
    }

    extracted_at = datetime(
        2026,
        10,
        6,
        18,
        30,
        45,
        tzinfo=timezone.utc,
    )

    client = Mock()
    client.fetch_daily_time_series.return_value = payload

    raw_writer = Mock()
    raw_writer.write.return_value = Mock()

    raw_path = ingest_daily_market_data(
    symbol="AAPL",
    client=client,
    raw_writer=raw_writer,
    extracted_at=extracted_at,
    )

    client.fetch_daily_time_series.assert_called_once_with("AAPL")

    raw_writer.write.assert_called_once_with(
        payload,
        provider="twelve_data",
        symbol="AAPL",
        extracted_at=extracted_at,
    )

    assert raw_path == raw_writer.write.return_value
