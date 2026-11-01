"""Unit contracts for M10 experimental *definitions*, not performance claims."""

import math

import pytest

from financial_data_platform.experiments.metrics import (
    gold_outcome_metrics,
    quality_metrics,
    throughput_records_per_second,
)


def test_quality_counts_and_unrounded_rates():
    result = quality_metrics(total_records=3, valid_count=2, invalid_count=1)
    assert result.acceptance_rate == pytest.approx(2 / 3)
    assert result.rejection_rate == pytest.approx(1 / 3)
    assert result.total_records == result.valid_count + result.invalid_count


def test_empty_quality_batch_has_undefined_experimental_rates():
    result = quality_metrics(total_records=0, valid_count=0, invalid_count=0)
    assert result.acceptance_rate is None
    assert result.rejection_rate is None


@pytest.mark.parametrize(
    "counts",
    [
        {"total_records": 2, "valid_count": 2, "invalid_count": 1},
        {"total_records": -1, "valid_count": 0, "invalid_count": 0},
        {"total_records": True, "valid_count": 1, "invalid_count": 0},
        {"total_records": 1, "valid_count": 0.5, "invalid_count": 0.5},
    ],
)
def test_quality_rejects_invalid_counts(counts):
    with pytest.raises(ValueError):
        quality_metrics(**counts)


def test_throughput_uses_selected_records_and_positive_elapsed_seconds():
    assert throughput_records_per_second(records=200, elapsed_seconds=2.5) == 80.0
    assert throughput_records_per_second(records=0, elapsed_seconds=2) == 0.0


@pytest.mark.parametrize("duration", [0, -1, float("nan"), float("inf"), True])
def test_throughput_rejects_invalid_elapsed(duration):
    with pytest.raises(ValueError):
        throughput_records_per_second(records=10, elapsed_seconds=duration)


def test_throughput_rejects_invalid_record_count():
    with pytest.raises(ValueError):
        throughput_records_per_second(records=-2, elapsed_seconds=1)


def test_gold_outcomes_keep_unchanged_and_rejected_separate():
    result = gold_outcome_metrics(
        records_read=8, inserted=2, updated=1, unchanged=4, rejected=1
    )
    assert result.applied == 3
    assert result.records_read == 8


def test_gold_outcomes_must_balance():
    with pytest.raises(ValueError, match="sum to records_read"):
        gold_outcome_metrics(
            records_read=3, inserted=1, updated=1, unchanged=1, rejected=1
        )


def test_gold_rejects_boolean_count():
    with pytest.raises(ValueError):
        gold_outcome_metrics(
            records_read=1, inserted=True, updated=0, unchanged=0, rejected=0
        )


def test_metrics_are_finite_for_valid_inputs():
    assert math.isfinite(throughput_records_per_second(records=5, elapsed_seconds=1))
