"""M10 experimental metric contracts independent of ETL and database execution.

Metrics are derived from measured inputs, not estimates. This module does not
start experiments, make requests, connect to databases, or write output files.
"""

import math
from dataclasses import dataclass


def _count(value: int, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative integer")
    return value


def _elapsed(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("elapsed_seconds must be a positive finite number")
    elapsed = float(value)
    if not math.isfinite(elapsed) or elapsed <= 0:
        raise ValueError("elapsed_seconds must be a positive finite number")
    return elapsed


@dataclass(frozen=True)
class QualityMetrics:
    """Raw-to-Silver parsed-observation counts and unrounded fractions."""

    total_records: int
    valid_count: int
    invalid_count: int
    acceptance_rate: float | None
    rejection_rate: float | None


def quality_metrics(
    *, total_records: int, valid_count: int, invalid_count: int
) -> QualityMetrics:
    """Evaluate a *parsed* batch; None means the denominator is zero.

    The production quality report deliberately uses 0.0 for an empty batch;
    experiments instead mark the statistical rate undefined (None), to avoid
    treating an empty batch as evidence of successful validation.
    """
    total = _count(total_records, "total_records")
    valid = _count(valid_count, "valid_count")
    invalid = _count(invalid_count, "invalid_count")
    if total != valid + invalid:
        raise ValueError("total_records must equal valid_count plus invalid_count")
    return QualityMetrics(
        total_records=total,
        valid_count=valid,
        invalid_count=invalid,
        acceptance_rate=valid / total if total else None,
        rejection_rate=invalid / total if total else None,
    )


def throughput_records_per_second(*, records: int, elapsed_seconds: float) -> float:
    """Number of records completed during a measured positive elapsed duration."""
    return _count(records, "records") / _elapsed(elapsed_seconds)


@dataclass(frozen=True)
class GoldOutcomeMetrics:
    """Gold record outcomes, distinct from Raw-to-Silver invalid observations."""

    records_read: int
    inserted: int
    updated: int
    unchanged: int
    rejected: int
    applied: int


def gold_outcome_metrics(
    *, records_read: int, inserted: int, updated: int, unchanged: int, rejected: int
) -> GoldOutcomeMetrics:
    """Validate a completed Gold batch's mutually exclusive record outcomes."""
    read = _count(records_read, "records_read")
    inserted = _count(inserted, "inserted")
    updated = _count(updated, "updated")
    unchanged = _count(unchanged, "unchanged")
    rejected = _count(rejected, "rejected")
    if read != inserted + updated + unchanged + rejected:
        raise ValueError("Gold outcomes must sum to records_read")
    return GoldOutcomeMetrics(
        records_read=read,
        inserted=inserted,
        updated=updated,
        unchanged=unchanged,
        rejected=rejected,
        applied=inserted + updated,
    )
