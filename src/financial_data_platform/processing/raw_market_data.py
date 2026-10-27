import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from financial_data_platform.providers.twelve_data.parser import (
    parse_time_series,
)
from financial_data_platform.storage.quarantine import QuarantineWriter
from financial_data_platform.storage.silver import SilverWriter
from financial_data_platform.validation.market_data import (
    partition_market_data_records,
)
from financial_data_platform.processing.quality_reporting import (
    build_quality_report,
)


@dataclass(frozen=True)
class RawProcessingResult:
    """Summary of processing one preserved Raw response."""

    total_records: int
    valid_count: int
    invalid_count: int
    silver_paths: list[Path]
    quarantine_paths: list[Path]
    quality_report: dict[str, object]


def process_raw_market_data(
    *,
    raw_path: Path,
    silver_writer: SilverWriter,
    quarantine_writer: QuarantineWriter,
    extracted_at: datetime,
    detected_at: datetime,
) -> RawProcessingResult:
    """Process a preserved Twelve Data response into Silver and quarantine."""

    with raw_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    records = parse_time_series(
        payload,
        extracted_at=extracted_at,
    )

    validation_result = partition_market_data_records(records)

    silver_paths = silver_writer.write(validation_result.valid_records)

    quarantine_paths = [
        quarantine_writer.write(
            invalid_record,
            detected_at=detected_at,
        )
        for invalid_record in validation_result.invalid_records
    ]

    quality_report = build_quality_report(
        validation_result,
        quarantine_paths=quarantine_paths,
    )

    return RawProcessingResult(
        total_records=len(records),
        valid_count=len(validation_result.valid_records),
        invalid_count=len(validation_result.invalid_records),
        silver_paths=silver_paths,
        quarantine_paths=quarantine_paths,
        quality_report=quality_report,
    )
