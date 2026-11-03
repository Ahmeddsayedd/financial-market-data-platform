"""Contract tests for the read-only final thesis evidence reviewer."""

import copy
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts/review_thesis_evidence.py"
spec = importlib.util.spec_from_file_location("review_thesis_evidence", SCRIPT)
reviewer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reviewer)


def sample():
    indicator = {key: 100 for key in reviewer.INDICATORS}
    replay = {
        "mode": "offline_replay",
        "api_requests": 0,
        "gold_writes": 0,
        "symbol": "AAPL",
        "repetitions": 5,
        "warmups": 1,
        "trials": [{"warmup": True}] + [{"warmup": False} for _ in range(5)],
        "quality": {"valid_count": 100, "invalid_count": 0},
        "records_parsed": 100,
        "raw_sha256": "a" * 64,
        "earliest_date": "2026-06-11",
        "latest_date": "2026-11-02",
        "raw_file": "raw/aapl.json",
        "raw_to_silver_seconds": {"median": 0.008},
    }
    audit = copy.deepcopy(replay)
    audit["gold_audit"] = {
        "database": "financial_market_test",
        "row_count": 100,
        "distinct_dates": 100,
        "query_seconds": 0.009,
        "indicator_non_null_counts": indicator,
    }

    def tracked(n):
        return {
            "database": "financial_market_test",
            "api_requests": 0,
            "database_writes": 0,
            "airflow_tracking": {
                "status": "success",
                "airflow_run_id": "manual__x",
                "counters": {
                    "records_extracted": n,
                    "records_validated": n,
                    "records_transformed": n,
                    "records_loaded": 0,
                    "records_rejected": 0,
                },
            },
            "gold_snapshot": {"row_count": 100, "indicator_non_null_counts": indicator},
        }

    return replay, audit, tracked(0), tracked(100)


def test_valid_consistent_reports():
    result = reviewer.review(*sample())
    assert result["status"] == "PASS"
    assert result["controlled_records_transformed"] == 100
    assert result["replay_median_ms"] == 8


@pytest.mark.parametrize(
    "index,change",
    [
        (0, ("api_requests", 1)),
        (1, ("gold_writes", 1)),
        (2, ("database", "financial_market")),
        (3, ("database_writes", 1)),
    ],
)
def test_rejects_unsafe_or_inconsistent_metadata(index, change):
    values = list(sample())
    values[index][change[0]] = change[1]
    with pytest.raises(ValueError):
        reviewer.review(*values)


def test_rejects_mismatching_input_hash():
    values = list(sample())
    values[1]["raw_sha256"] = "b" * 64
    with pytest.raises(ValueError, match="raw_sha256"):
        reviewer.review(*values)


def test_load_checks_schema_and_symlinks(tmp_path):
    path = tmp_path / "evidence.json"
    path.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    assert reviewer.load(path) == {"schema_version": 1}
    path.write_text(json.dumps({"schema_version": 2}), encoding="utf-8")
    with pytest.raises(ValueError):
        reviewer.load(path)
