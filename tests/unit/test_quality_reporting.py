"""Tests for structured Raw-to-Silver quality reporting."""

import json
from dataclasses import replace
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from financial_data_platform.models.market_data import MarketDataRecord
from financial_data_platform.processing.quality_reporting import (
    build_quality_report,
)
from financial_data_platform.validation.market_data import (
    partition_market_data_records,
)


@pytest.fixture
def valid_record():
    return MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 5),
        open=Decimal("250.00"),
        high=Decimal("255.00"),
        low=Decimal("249.00"),
        close=Decimal("254.00"),
        volume=1000,
        source="twelve_data",
        extracted_at=datetime(2026, 10, 6, tzinfo=timezone.utc),
    )


def test_clean_batch_reports_zero_rejections(valid_record):
    batch = partition_market_data_records([valid_record])

    report = build_quality_report(batch, quarantine_paths=[])

    assert report == {
        "total_records": 1,
        "valid_count": 1,
        "invalid_count": 0,
        "acceptance_rate": 1.0,
        "rejection_rate": 0.0,
        "violation_counts": {},
        "quarantine_paths": [],
    }


def test_multiple_violations_count_one_rejected_record(valid_record):
    invalid = replace(
        valid_record,
        observation_date=date(2026, 10, 6),
        close=Decimal("NaN"),
        volume=-1,
    )
    batch = partition_market_data_records([valid_record, invalid])

    report = build_quality_report(
        batch,
        quarantine_paths=[Path("quarantine/invalid.json")],
    )

    assert report["total_records"] == 2
    assert report["valid_count"] == 1
    assert report["invalid_count"] == 1
    assert report["acceptance_rate"] == 0.5
    assert report["rejection_rate"] == 0.5
    assert report["violation_counts"] == {
        "NEGATIVE_VOLUME": 1,
        "NON_FINITE_CLOSE": 1,
    }
    assert report["quarantine_paths"] == [
        "quarantine/invalid.json"
    ]


def test_violation_counts_aggregate_across_records(valid_record):
    first = replace(
        valid_record,
        observation_date=date(2026, 10, 6),
        volume=-1,
    )
    second = replace(
        valid_record,
        observation_date=date(2026, 10, 7),
        volume=-2,
    )
    batch = partition_market_data_records(
        [valid_record, first, second]
    )

    report = build_quality_report(batch)

    assert report["total_records"] == 3
    assert report["invalid_count"] == 2
    assert report["violation_counts"] == {
        "NEGATIVE_VOLUME": 2,
    }
    assert report["acceptance_rate"] == 0.3333
    assert report["rejection_rate"] == 0.6667


def test_invalid_only_batch_has_zero_acceptance(valid_record):
    invalid = replace(valid_record, volume=-1)
    batch = partition_market_data_records([invalid])

    report = build_quality_report(batch)

    assert report["valid_count"] == 0
    assert report["invalid_count"] == 1
    assert report["acceptance_rate"] == 0.0
    assert report["rejection_rate"] == 1.0


def test_empty_batch_has_defined_rates():
    batch = partition_market_data_records([])

    report = build_quality_report(batch)

    assert report["total_records"] == 0
    assert report["acceptance_rate"] == 0.0
    assert report["rejection_rate"] == 0.0
    assert report["violation_counts"] == {}


def test_report_is_json_serializable(valid_record):
    invalid = replace(valid_record, volume=-1)
    batch = partition_market_data_records([invalid])

    report = build_quality_report(
        batch,
        quarantine_paths=[Path("quarantine/aapl.json")],
    )

    encoded = json.dumps(report, sort_keys=True)
    decoded = json.loads(encoded)

    assert decoded == report


def test_quarantine_count_must_match_invalid_records(valid_record):
    invalid = replace(valid_record, volume=-1)
    batch = partition_market_data_records([invalid])

    with pytest.raises(
        ValueError,
        match="Quarantine path count",
    ):
        build_quality_report(batch, quarantine_paths=[])