"""Reusable Raw-to-Silver orchestration adapter."""

from datetime import datetime, timezone
from pathlib import Path

from financial_data_platform.processing.raw_market_data import (
    process_raw_market_data,
)
from financial_data_platform.storage.quarantine import QuarantineWriter
from financial_data_platform.storage.silver import SilverWriter


def process_raw_file_to_silver(
    *,
    raw_relative_path: str,
    raw_base_dir: Path,
    silver_base_dir: Path,
    quarantine_base_dir: Path,
    detected_at: datetime | None = None,
) -> dict[str, object]:
    """Process one preserved Raw response into Silver and quarantine.

    Raw paths must be relative to raw_base_dir and must have the
    timestamped filename produced by RawResponseWriter.
    """
    if not isinstance(raw_relative_path, str) or not raw_relative_path:
        raise ValueError("raw_relative_path must be a nonempty string")

    relative_path = Path(raw_relative_path)

    if relative_path.is_absolute() or ".." in relative_path.parts:
        raise ValueError("Raw path must stay inside the Raw storage directory")

    raw_root = raw_base_dir.resolve()
    raw_path = (raw_root / relative_path).resolve()

    if not raw_path.is_relative_to(raw_root):
        raise ValueError("Raw path escapes the Raw storage directory")

    if not raw_path.is_file():
        raise FileNotFoundError(f"Raw file does not exist: {relative_path}")

    try:
        extracted_at = datetime.strptime(
            raw_path.name,
            "%Y%m%dT%H%M%S%fZ.json",
        ).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise ValueError(
            "Raw filename must contain its UTC extraction timestamp"
        ) from exc

    processing_time = detected_at or datetime.now(timezone.utc)

    if (
        processing_time.tzinfo is None
        or processing_time.utcoffset() is None
    ):
        raise ValueError("detected_at must be timezone-aware")

    result = process_raw_market_data(
        raw_path=raw_path,
        silver_writer=SilverWriter(silver_base_dir),
        quarantine_writer=QuarantineWriter(quarantine_base_dir),
        extracted_at=extracted_at,
        detected_at=processing_time,
    )

    return {
        "status": "success",
        "raw_path": str(raw_path),
        "total_records": result.total_records,
        "valid_count": result.valid_count,
        "invalid_count": result.invalid_count,
        "silver_paths": [str(path) for path in result.silver_paths],
        "quarantine_paths": [
            str(path) for path in result.quarantine_paths
        ],
        "quality_report": result.quality_report,
    }