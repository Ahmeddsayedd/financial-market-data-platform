"""Tests for the Raw-to-Silver orchestration adapter."""

import json
from datetime import datetime, timezone

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