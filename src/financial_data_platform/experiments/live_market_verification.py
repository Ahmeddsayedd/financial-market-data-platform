"""Bounded, opt-in Twelve Data evidence collection for a local thesis demo.

This module does not load .env or call the network on import. The CLI owns
explicit authorization; its write path refuses every database except the
isolated financial_market_test database.
"""

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from financial_data_platform.ingestion import ingest_daily_market_data
from financial_data_platform.providers.twelve_data.client import TwelveDataClient
from financial_data_platform.providers.twelve_data.parser import parse_time_series
from financial_data_platform.storage.raw import RawResponseWriter

TEST_DATABASE = "financial_market_test"
_SYMBOL = re.compile(r"[A-Z][A-Z0-9.\-]{0,14}\Z")


class VerificationError(ValueError):
    """Reject unsafe/incomplete verification configuration."""


def validate_symbol(symbol: str) -> str:
    """Restrict live queries and filesystem paths to one simple ticker."""
    if not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol):
        raise VerificationError("Symbol must be an uppercase ticker (max 15 chars).")
    return symbol


def validate_outputsize(outputsize: int) -> int:
    """Bound the provider response and its API credit footprint."""
    if not 60 <= outputsize <= 200:
        raise VerificationError("outputsize must be between 60 and 200.")
    return outputsize


def _connect_test_database():
    from financial_data_platform.warehouse.db import connect_to_database

    return connect_to_database()


def require_isolated_database(*, confirmation: str) -> None:
    """Verify the configured and actual DB before any Gold write."""
    if confirmation != TEST_DATABASE:
        raise VerificationError("Explicit confirmation of test database is required.")
    if os.getenv("POSTGRES_DB") != TEST_DATABASE:
        raise VerificationError("POSTGRES_DB must equal financial_market_test.")

    connection = _connect_test_database()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            row = cursor.fetchone()
            if row is None or row[0] != TEST_DATABASE:
                raise VerificationError(
                    "Connected database is not financial_market_test."
                )
        connection.rollback()  # Read-only preflight; never commit a preflight.
    finally:
        connection.close()


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _relative_to(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError as exc:
        raise VerificationError(
            "Input file must stay within the experiment root."
        ) from exc


def _process_to_silver(**kwargs: Any) -> dict[str, Any]:
    # Defer optional Parquet dependencies until a real run is requested.
    from financial_data_platform.orchestration.silver import process_raw_file_to_silver

    return process_raw_file_to_silver(**kwargs)


def _load_gold_records(silver_paths: list[str]) -> dict[str, Any]:
    from financial_data_platform.storage.silver_reader import read_silver_parquet
    from financial_data_platform.warehouse.gold_indicator_persistence import (
        load_market_records_with_indicators,
    )

    records = []
    for silver_path in silver_paths:
        records.extend(read_silver_parquet(Path(silver_path)))
    return load_market_records_with_indicators(records)


def verify_market_data(
    *,
    experiment_root: Path,
    symbol: str,
    live_client: TwelveDataClient | None = None,
    replay_raw: Path | None = None,
    outputsize: int = 100,
    write_gold: bool = False,
    confirm_test_db: str = "",
) -> dict[str, Any]:
    """Fetch once (or replay), validate, persist Raw/Silver, optionally Gold.

    All on-disk artifacts remain in experiment_root, which callers should place
    below ignored data/experiments. No API credentials or provider payloads are
    inserted into the small summary JSON.
    """
    validate_symbol(symbol)
    validate_outputsize(outputsize)
    if (live_client is None) == (replay_raw is None):
        raise VerificationError("Select exactly one of live client or replay Raw file.")

    root = experiment_root.resolve()
    raw_dir = root / "raw"

    if write_gold:
        # Check BEFORE making HTTP calls or writing any new files.
        require_isolated_database(confirmation=confirm_test_db)

    start = time.perf_counter()
    request_count = 0
    if live_client is not None:
        extracted_at = datetime.now(timezone.utc)
        # This uses the existing client and raw writer; one request, zero retries.
        raw_path = ingest_daily_market_data(
            symbol=symbol,
            client=live_client,
            raw_writer=RawResponseWriter(raw_dir),
            extracted_at=extracted_at,
            outputsize=outputsize,
        )
        request_count = 1
    else:
        raw_path = replay_raw.resolve()
        _relative_to(raw_path, raw_dir)
        if not raw_path.is_file():
            raise VerificationError("Raw replay file does not exist.")
    fetch_seconds = round(time.perf_counter() - start, 6)

    # Per-extraction partitions prevent old Silver rows from contaminating
    # the current experiment. Replaying the same Raw file uses the same path.
    silver_dir = root / "silver" / raw_path.stem
    quarantine_dir = root / "quarantine" / raw_path.stem

    # Independently verify the symbol before transforming or loading anything.
    payload = json.loads(raw_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise VerificationError("Provider response must be an object.")
    meta = payload.get("meta")
    if not isinstance(meta, dict) or meta.get("symbol") != symbol:
        raise VerificationError("Provider response symbol does not match the request.")
    if meta.get("interval") not in (None, "1day"):
        raise VerificationError("Provider response interval is not daily.")

    # Parser also detects duplicate dates, malformed timestamps, and bad values.
    parsed = parse_time_series(payload, extracted_at=datetime.now(timezone.utc))
    transform_start = time.perf_counter()
    result = _process_to_silver(
        raw_relative_path=_relative_to(raw_path, raw_dir),
        raw_base_dir=raw_dir,
        silver_base_dir=silver_dir,
        quarantine_base_dir=quarantine_dir,
    )
    processing_seconds = round(time.perf_counter() - transform_start, 6)
    if result["valid_count"] == 0:
        raise VerificationError("No valid observations; refusing Gold write.")

    gold_counts: dict[str, Any] | None = None
    gold_seconds: float | None = None
    if write_gold:
        # Check again immediately before opening the write transaction.
        require_isolated_database(confirmation=confirm_test_db)
        gold_start = time.perf_counter()
        gold_counts = _load_gold_records(result["silver_paths"])
        gold_seconds = round(time.perf_counter() - gold_start, 6)

    dates = sorted(record.observation_date for record in parsed)
    summary = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider": "twelve_data",
        "mode": "live" if live_client is not None else "replay",
        "symbol": symbol,
        "interval": "1day",
        "requested_outputsize": outputsize if live_client is not None else None,
        "api_requests": request_count,
        "raw_sha256": _digest(raw_path),
        "raw_file": _relative_to(raw_path, root),
        "records_parsed": len(parsed),
        "earliest_date": dates[0].isoformat(),
        "latest_date": dates[-1].isoformat(),
        "quality": {
            key: result["quality_report"][key]
            for key in (
                "total_records",
                "valid_count",
                "invalid_count",
                "acceptance_rate",
                "rejection_rate",
                "violation_counts",
            )
        },
        "silver_files": len(result["silver_paths"]),
        "fetch_or_replay_seconds": fetch_seconds,
        "raw_to_silver_seconds": processing_seconds,
        "gold_write_enabled": write_gold,
        "gold_database": TEST_DATABASE if write_gold else None,
        "gold_counts": gold_counts,
        "gold_seconds": gold_seconds,
    }
    root.mkdir(parents=True, exist_ok=True)
    # Distinct summary files preserve evidence for first run and replay.
    summary_name = (
        "last-live-summary.json" if live_client else "last-replay-summary.json"
    )
    (root / summary_name).write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary
