"""Structured quality reports for validated market observations."""

from collections import Counter
from pathlib import Path

from financial_data_platform.validation.market_data import (
    BatchValidationResult,
)


def build_quality_report(
    validation_result: BatchValidationResult,
    *,
    quarantine_paths: list[Path] | None = None,
) -> dict[str, object]:
    """Summarize record-level quality and violation occurrences.

    Rejected records are counted once, regardless of how many
    violations they contain.
    """
    valid_count = len(validation_result.valid_records)
    invalid_count = len(validation_result.invalid_records)
    total_records = valid_count + invalid_count

    violation_counts = Counter(
        violation.code
        for invalid_record in validation_result.invalid_records
        for violation in invalid_record.violations
    )

    paths = quarantine_paths if quarantine_paths is not None else []

    if quarantine_paths is not None and len(paths) != invalid_count:
        raise ValueError(
            "Quarantine path count must equal rejected record count"
        )

    return {
        "total_records": total_records,
        "valid_count": valid_count,
        "invalid_count": invalid_count,
        "acceptance_rate": (
            round(valid_count / total_records, 4)
            if total_records
            else 0.0
        ),
        "rejection_rate": (
            round(invalid_count / total_records, 4)
            if total_records
            else 0.0
        ),
        "violation_counts": dict(sorted(violation_counts.items())),
        "quarantine_paths": [path.as_posix() for path in paths],
    }