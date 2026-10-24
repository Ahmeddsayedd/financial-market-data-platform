"""Tests for the Raw-to-Silver orchestration adapter."""

import json
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from financial_data_platform.orchestration.silver import (
    process_raw_file_to_silver,
)


RAW_RELATIVE_PATH = (
    "twelve_data/AAPL/2026/10/24/"
    "20261024T160953206116Z.json"
)


def write_raw_fixture(tmp_path, *, invalid=False):
    raw_root = tmp_path / "raw"
    raw_file = raw_root / RAW_RELATIVE_PATH
    raw_file.parent.mkdir(parents=True)

    payload = {
        "meta": {"symbol": "AAPL"},
        "values": [
            {
                "datetime": "2026-10-23",
                "open": "250.00",
                "high": "255.00",
                "low": "249.00",
                "close": "254.00",
                "volume": "-100" if invalid else "1000000",
            }
        ],
    }

    raw_file.write_text(json.dumps(payload), encoding="utf-8")
    return raw_root


def process_fixture(tmp_path, raw_root, **overrides):
    arguments = {
        "raw_relative_path": RAW_RELATIVE_PATH,
        "raw_base_dir": raw_root,
        "silver_base_dir": tmp_path / "silver",
        "quarantine_base_dir": tmp_path / "quarantine",
        "detected_at": datetime(2026, 10, 24, tzinfo=timezone.utc),
    }
    arguments.update(overrides)
    return process_raw_file_to_silver(**arguments)


def test_processes_valid_raw_file_into_silver(tmp_path):
    raw_root = write_raw_fixture(tmp_path)

    result = process_fixture(tmp_path, raw_root)

    assert result["status"] == "success"
    assert result["total_records"] == 1
    assert result["valid_count"] == 1
    assert result["invalid_count"] == 0
    assert len(result["silver_paths"]) == 1
    assert result["quarantine_paths"] == []
    assert result["quality_report"]["total_records"] == 1
    assert result["quality_report"]["valid_count"] == 1
    assert result["quality_report"]["invalid_count"] == 0
    assert result["quality_report"]["acceptance_rate"] == 1.0
    assert result["quality_report"]["violation_counts"] == {}

    json.dumps(result["quality_report"])

    table = pq.read_table(
        result["silver_paths"][0],
        partitioning=None,
    )

    assert table.num_rows == 1
    assert table.column("symbol").to_pylist() == ["AAPL"]
    assert table.column("extracted_at").to_pylist() == [
        datetime(2026, 10, 24, 16, 9, 53, 206116, tzinfo=timezone.utc)
    ]


def test_invalid_record_is_quarantined(tmp_path):
    raw_root = write_raw_fixture(tmp_path, invalid=True)

    result = process_fixture(tmp_path, raw_root)

    assert result["total_records"] == 1
    assert result["valid_count"] == 0
    assert result["invalid_count"] == 1
    assert result["silver_paths"] == []
    assert len(result["quarantine_paths"]) == 1
    report = result["quality_report"]
    assert report["total_records"] == 1
    assert report["valid_count"] == 0
    assert report["invalid_count"] == 1
    assert report["rejection_rate"] == 1.0
    assert report["violation_counts"] == {"NEGATIVE_VOLUME": 1}
    assert [Path(path) for path in report["quarantine_paths"]] == [
    Path(path) for path in result["quarantine_paths"]
]


def test_missing_raw_file_fails(tmp_path):
    with pytest.raises(FileNotFoundError):
        process_fixture(tmp_path, tmp_path / "raw")


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../outside.json",
        "../../secrets.json",
        "/tmp/outside.json",
    ],
)
def test_rejects_unsafe_raw_paths(tmp_path, unsafe_path):
    with pytest.raises(ValueError):
        process_fixture(
            tmp_path,
            tmp_path / "raw",
            raw_relative_path=unsafe_path,
        )


def test_rejects_filename_without_extraction_timestamp(tmp_path):
    raw_root = write_raw_fixture(tmp_path)

    original = raw_root / RAW_RELATIVE_PATH
    renamed = original.with_name("invalid-name.json")
    original.rename(renamed)

    with pytest.raises(ValueError, match="extraction timestamp"):
        process_fixture(
            tmp_path,
            raw_root,
            raw_relative_path=str(renamed.relative_to(raw_root)),
        )


def test_rejects_naive_processing_timestamp(tmp_path):
    raw_root = write_raw_fixture(tmp_path)

    with pytest.raises(ValueError, match="timezone-aware"):
        process_fixture(
            tmp_path,
            raw_root,
            detected_at=datetime(2026, 10, 24),
        )


def test_reprocessing_preserves_single_market_observation(tmp_path):
    raw_root = write_raw_fixture(tmp_path)

    first = process_fixture(tmp_path, raw_root)
    second = process_fixture(tmp_path, raw_root)

    assert first["silver_paths"] == second["silver_paths"]

    table = pq.read_table(
        second["silver_paths"][0],
        partitioning=None,
    )
    assert table.num_rows == 1


def test_mixed_quality_report_reaches_orchestration(tmp_path):
    """Report multiple violations without counting a record twice."""
    raw_root = write_raw_fixture(tmp_path)
    raw_path = raw_root / RAW_RELATIVE_PATH

    payload = json.loads(raw_path.read_text(encoding="utf-8"))

    invalid_observation = dict(payload["values"][0])
    invalid_observation["datetime"] = "2026-10-22"
    invalid_observation["close"] = "NaN"
    invalid_observation["volume"] = "-100"

    payload["values"].append(invalid_observation)

    raw_path.write_text(
        json.dumps(payload),
        encoding="utf-8",
    )

    result = process_fixture(tmp_path, raw_root)
    report = result["quality_report"]

    assert result["status"] == "success"
    assert result["total_records"] == 2
    assert result["valid_count"] == 1
    assert result["invalid_count"] == 1

    assert report["total_records"] == 2
    assert report["valid_count"] == 1
    assert report["invalid_count"] == 1
    assert report["acceptance_rate"] == 0.5
    assert report["rejection_rate"] == 0.5
    assert report["violation_counts"] == {
        "NEGATIVE_VOLUME": 1,
        "NON_FINITE_CLOSE": 1,
    }

    assert len(result["silver_paths"]) == 1
    assert len(result["quarantine_paths"]) == 1

    # A valid record survives the invalid observation.
    silver_table = pq.read_table(
        result["silver_paths"][0],
        partitioning=None,
    )
    assert silver_table.num_rows == 1

    quarantined = json.loads(
        Path(result["quarantine_paths"][0]).read_text(
            encoding="utf-8"
        )
    )

    assert {item["code"] for item in quarantined["violations"]} == {
        "NEGATIVE_VOLUME",
        "NON_FINITE_CLOSE",
    }

    # The complete orchestration result is compatible with JSON.
    json.dumps(result)