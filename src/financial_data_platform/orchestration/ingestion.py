"""Reusable ingestion entry point for workflow orchestrators.

Issue #33: Reuse the existing Twelve Data ingestion pipeline
without coupling business logic to Apache Airflow.
"""

from collections.abc import Sequence
from datetime import datetime, timezone
from pathlib import Path

from financial_data_platform.config import get_twelve_data_api_key
from financial_data_platform.ingestion import ingest_daily_market_data
from financial_data_platform.providers.twelve_data.client import TwelveDataClient
from financial_data_platform.storage.raw import RawResponseWriter


DEFAULT_SYMBOLS = ("AAPL",)


def ingest_market_symbols(
    *,
    symbols: Sequence[str] = DEFAULT_SYMBOLS,
    raw_base_dir: Path,
    extracted_at: datetime | None = None,
) -> dict[str, object]:
    """Fetch and persist Raw data for a controlled set of symbols.

    Returns a small JSON-serializable summary suitable for Airflow XCom.
    Raises on extraction or persistence errors so Airflow can report failure.
    """
    selected_symbols = tuple(symbols)

    if not selected_symbols:
        raise ValueError("At least one market symbol is required.")

    if any(
        not isinstance(symbol, str) or not symbol.strip() for symbol in selected_symbols
    ):
        raise ValueError("Market symbols must be non-empty strings.")

    if len(set(selected_symbols)) != len(selected_symbols):
        raise ValueError("Duplicate market symbols are not allowed.")

    if extracted_at is None:
        extracted_at = datetime.now(timezone.utc)

    if extracted_at.tzinfo is None or extracted_at.utcoffset() is None:
        raise ValueError("extracted_at must be timezone-aware.")

    client = TwelveDataClient(
        api_key=get_twelve_data_api_key(),
        max_retries=0,
    )
    raw_writer = RawResponseWriter(base_dir=raw_base_dir)

    stored_paths: list[str] = []

    for symbol in selected_symbols:
        raw_path = ingest_daily_market_data(
            symbol=symbol,
            client=client,
            raw_writer=raw_writer,
            extracted_at=extracted_at,
        )
        stored_paths.append(str(raw_path))

    return {
        "provider": "twelve_data",
        "status": "success",
        "symbols": list(selected_symbols),
        "files_written": len(stored_paths),
        "raw_paths": stored_paths,
    }
