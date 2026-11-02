"""Offline contracts for the read-only M10 provenance review command."""

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "review_m10_evidence.py"
spec = importlib.util.spec_from_file_location("review_m10_evidence", SCRIPT)
reviewer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(reviewer)


def _write_json(path, obj):
    path.write_text(json.dumps(obj, sort_keys=True) + "\n", encoding="utf-8")


def _make_pair(tmp_path):
    dataset = tmp_path / "fixture"
    raw = dataset / "raw"
    raw.mkdir(parents=True)
    item = raw / "SYN0001.json"
    item.write_text('{"synthetic":true}\n', encoding="utf-8")
    hashes = {"raw/SYN0001.json": hashlib.sha256(item.read_bytes()).hexdigest()}
    aggregate = (
        json.dumps(hashes, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    fixture_sha = hashlib.sha256(aggregate).hexdigest()
    manifest = {
        "schema_version": 1,
        "profile": "small",
        "scenario": "clean",
        "seed": 42,
        "symbol_count": 1,
        "expected_unique_observations": 100,
        "file_sha256": hashes,
        "dataset_sha256": fixture_sha,
    }
    _write_json(dataset / "manifest.json", manifest)
    evidence = tmp_path / "benchmark.jsonl"
    rows = [
        {
            "schema_version": 1,
            "experiment_id": "raw-silver-small-clean",
            "fixture_sha256": fixture_sha,
            "profile": "small",
            "scenario": "clean",
            "seed": 42,
            "symbol_count": 1,
            "expected_unique_observations": 100,
            "stage": "raw_to_silver",
            "git_sha": "a" * 40,
            "python_version": "3.11.8",
            "attempt": number,
            "warmup": number == 1,
            "status": "success",
            "elapsed_ns": 100000000,
            "total_records": 100,
        }
        for number in (1, 2)
    ]
    evidence.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    return dataset, evidence, rows


def test_fixture_benchmark_review(tmp_path):
    fixture, benchmark, _ = _make_pair(tmp_path)
    result = reviewer.review(
        pairs=[(fixture, benchmark)], quality=[], performance=None, gold=None
    )
    assert result["fixture_benchmark_pairs"] == 1
    assert result["benchmark_sha256"] == [
        hashlib.sha256(benchmark.read_bytes()).hexdigest()
    ]


def test_fixture_file_tampering_rejected(tmp_path):
    fixture, benchmark, _ = _make_pair(tmp_path)
    (fixture / "raw" / "SYN0001.json").write_text("modified", encoding="utf-8")
    with pytest.raises(ValueError, match="hash mismatch"):
        reviewer.review(
            pairs=[(fixture, benchmark)], quality=[], performance=None, gold=None
        )


def test_fixture_manifest_digest_tampering_rejected(tmp_path):
    fixture, benchmark, _ = _make_pair(tmp_path)
    manifest = json.loads((fixture / "manifest.json").read_text(encoding="utf-8"))
    manifest["dataset_sha256"] = "a" * 64
    _write_json(fixture / "manifest.json", manifest)
    with pytest.raises(ValueError, match="inventory digest"):
        reviewer.review(
            pairs=[(fixture, benchmark)], quality=[], performance=None, gold=None
        )


def test_benchmark_identity_tampering_rejected(tmp_path):
    fixture, benchmark, rows = _make_pair(tmp_path)
    rows[1]["fixture_sha256"] = "b" * 64
    benchmark.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="identity"):
        reviewer.review(
            pairs=[(fixture, benchmark)], quality=[], performance=None, gold=None
        )


def test_benchmark_warmup_order_rejected(tmp_path):
    fixture, benchmark, rows = _make_pair(tmp_path)
    rows[0]["warmup"] = False
    rows[1]["warmup"] = True
    benchmark.write_text(
        "".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8"
    )
    with pytest.raises(ValueError, match="Warmups"):
        reviewer.review(
            pairs=[(fixture, benchmark)], quality=[], performance=None, gold=None
        )


def test_duplicate_benchmark_rejected(tmp_path):
    fixture, benchmark, _ = _make_pair(tmp_path)
    with pytest.raises(ValueError, match="Duplicate"):
        reviewer.review(
            pairs=[(fixture, benchmark), (fixture, benchmark)],
            quality=[],
            performance=None,
            gold=None,
        )


def test_performance_digest_matches_supplied_inputs(tmp_path):
    fixture, benchmark, _ = _make_pair(tmp_path)
    digest = hashlib.sha256(benchmark.read_bytes()).hexdigest()
    performance = tmp_path / "performance.json"
    _write_json(
        performance,
        {
            "schema_version": 1,
            "source_schema_version": 1,
            "measured_stage": "raw_to_silver",
            "input_sha256": [digest],
            "groups": [{"input_sha256": [digest]}],
        },
    )
    result = reviewer.review(
        pairs=[(fixture, benchmark)], quality=[], performance=performance, gold=None
    )
    assert result["performance_checked"] is True
    data = json.loads(performance.read_text(encoding="utf-8"))
    data["input_sha256"] = ["c" * 64]
    _write_json(performance, data)
    with pytest.raises(ValueError, match="does not reference"):
        reviewer.review(
            pairs=[(fixture, benchmark)], quality=[], performance=performance, gold=None
        )


def test_quality_report_crosschecks_attempts(tmp_path):
    fixture, benchmark, rows = _make_pair(tmp_path)
    report = tmp_path / "quality.json"
    _write_json(
        report,
        {
            "schema_version": 1,
            "fixture_sha256": rows[0]["fixture_sha256"],
            "seed": 42,
            "profile": "small",
            "scenario": "clean",
            "attempts": [
                {
                    "attempt": r["attempt"],
                    "warmup": r["warmup"],
                    "status": r["status"],
                    "elapsed_ns": r["elapsed_ns"],
                    "failure_category": None,
                    "matches_expected": True,
                }
                for r in rows
            ],
            "summary": {
                "measured_attempts": 1,
                "measured_matching_attempts": 1,
                "all_matched": True,
            },
        },
    )
    reviewer.review(
        pairs=[(fixture, benchmark)], quality=[report], performance=None, gold=None
    )
    data = json.loads(report.read_text(encoding="utf-8"))
    data["summary"]["measured_matching_attempts"] = 0
    _write_json(report, data)
    with pytest.raises(ValueError, match="summary"):
        reviewer.review(
            pairs=[(fixture, benchmark)], quality=[report], performance=None, gold=None
        )


def test_gold_report_review(tmp_path):
    rows = []
    for scenario, outcomes in zip(
        reviewer._GOLD,
        (
            (2, 2, 0, 0, 0),
            (2, 0, 0, 2, 0),
            (1, 0, 1, 0, 0),
            (1, 0, 0, 1, 0),
            (1, 0, 0, 0, 1),
        ),
    ):
        row = dict(
            zip(
                ("records_read", "inserted", "updated", "unchanged", "rejected"),
                outcomes,
            )
        )
        row.update(
            scenario=scenario,
            matches_expected=True,
            before_state_sha256="a" * 64,
            after_state_sha256="a" * 64,
        )
        rows.append(row)
    report = tmp_path / "gold.json"
    data = {
        "schema_version": 1,
        "experiment": "gold_repeatability_rollback_only",
        "database": "financial_market_test",
        "rolled_back": True,
        "scenarios": rows,
    }
    _write_json(report, data)
    reviewer.review_gold(report)
    data["rolled_back"] = False
    _write_json(report, data)
    with pytest.raises(ValueError, match="rollback-only"):
        reviewer.review_gold(report)


def test_reject_missing_pairs():
    with pytest.raises(ValueError, match="between 1 and 20"):
        reviewer.review(pairs=[], quality=[], performance=None, gold=None)
