"""Offline performance analysis contracts; all samples are fabricated test data."""

import copy
import json

import pytest

from financial_data_platform.experiments.performance_analysis import (
    analyze_performance,
    load_benchmark_evidence,
    render_markdown,
    write_performance_analysis,
)


def _row(*, profile="small", elapsed_ns=1_000_000_000, attempt=1, warmup=False):
    count = {"small": 100, "medium": 1000, "large": 10000}[profile]
    return {
        "schema_version": 1,
        "experiment_id": f"raw-silver-{profile}-clean",
        "git_sha": "a" * 40,
        "fixture_sha256": {"small": "1", "medium": "2", "large": "3"}[profile] * 64,
        "seed": 20261001,
        "profile": profile,
        "scenario": "clean",
        "symbol_count": 4,
        "expected_unique_observations": count,
        "python_version": "3.11.9",
        "stage": "raw_to_silver",
        "attempt": attempt,
        "warmup": warmup,
        "status": "success",
        "elapsed_ns": elapsed_ns,
        "total_records": count,
        "valid_count": count,
        "invalid_count": 0,
        "violation_counts": {},
        "acceptance_rate": 1.0,
        "rejection_rate": 0.0,
        "throughput_records_per_second": count * 1e9 / elapsed_ns,
        "failure_category": None,
    }


def _source(tmp_path, name="sample.jsonl", rows=None):
    file = tmp_path / name
    rows = [_row()] if rows is None else rows
    file.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return file


def _failed(**kwargs):
    row = _row(**kwargs)
    row.update(
        status="failed",
        elapsed_ns=None,
        failure_category="parser_error",
        total_records=None,
        valid_count=None,
        invalid_count=None,
        violation_counts=None,
        acceptance_rate=None,
        rejection_rate=None,
        throughput_records_per_second=None,
    )
    return row


def test_single_group_descriptive_metrics_and_warmup_excluded(tmp_path):
    path = _source(
        tmp_path,
        rows=[
            _row(attempt=1, warmup=True, elapsed_ns=99_000_000_000),
            _row(attempt=2, elapsed_ns=1_000_000_000),
            _row(attempt=3, elapsed_ns=3_000_000_000),
            _row(attempt=4, elapsed_ns=2_000_000_000),
        ],
    )
    report = analyze_performance([path])
    group = report["groups"][0]
    assert group["warmup_attempts"] == 1
    assert group["measured_attempts"] == 3
    assert group["successful_attempts"] == 3
    assert group["elapsed_seconds"]["median"] == 2.0
    assert group["elapsed_seconds"]["p95_nearest_rank"] == 3.0
    assert group["elapsed_seconds"]["minimum"] == 1.0
    assert group["throughput_records_per_second"]["median"] == 50.0
    assert "99" not in str(group["elapsed_seconds"])
    assert report["comparisons"] == []


def test_cross_tier_scaling_uses_median_ratios(tmp_path):
    small = _source(
        tmp_path,
        "small.jsonl",
        [
            _row(elapsed_ns=1_000_000_000, attempt=1),
            _row(elapsed_ns=3_000_000_000, attempt=2),
        ],
    )
    medium = _source(
        tmp_path, "medium.jsonl", [_row(profile="medium", elapsed_ns=8_000_000_000)]
    )
    report = analyze_performance([medium, small])
    comparison = report["comparisons"][0]
    assert comparison["record_ratio"] == 10
    assert comparison["median_elapsed_ratio"] == 4
    assert comparison["median_throughput_ratio"] == pytest.approx(1.875)
    assert report == analyze_performance([small, medium])


def test_failures_counted_without_fake_timings(tmp_path):
    path = _source(tmp_path, rows=[_failed()])
    group = analyze_performance([path])["groups"][0]
    assert group["failed_attempts"] == 1
    assert group["failure_categories"] == {"parser_error": 1}
    assert group["elapsed_seconds"] is None
    assert "n/a" in render_markdown(analyze_performance([path]))


def test_failed_rows_may_have_measured_elapsed_without_success_metrics(tmp_path):
    failed = _failed()
    failed["elapsed_ns"] = 500
    assert (
        analyze_performance([_source(tmp_path, rows=[failed])])["groups"][0][
            "elapsed_seconds"
        ]
        is None
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", 2),
        ("elapsed_ns", 0),
        ("elapsed_ns", True),
        ("elapsed_ns", -5),
        ("total_records", 0),
        ("total_records", True),
        ("valid_count", 99),
        ("acceptance_rate", 0.1),
        ("throughput_records_per_second", 9999),
        ("git_sha", "bad"),
        ("fixture_sha256", "bad"),
        ("stage", "bronze_to_gold"),
        ("symbol_count", 0),
        ("profile", "unknown"),
        ("profile", []),
        ("scenario", []),
        ("status", "maybe"),
        ("warmup", 1),
        ("violation_counts", {"bad": -1}),
    ],
)
def test_corrupt_schema_is_rejected(tmp_path, field, value):
    row = _row()
    row[field] = value
    with pytest.raises(ValueError):
        analyze_performance([_source(tmp_path, rows=[row])])


def test_missing_fields_are_rejected(tmp_path):
    row = _row()
    del row["throughput_records_per_second"]
    with pytest.raises(ValueError):
        analyze_performance([_source(tmp_path, rows=[row])])


def test_bad_attempt_order_and_interleaved_warmup(tmp_path):
    with pytest.raises(ValueError, match="contiguous"):
        analyze_performance([_source(tmp_path, rows=[_row(attempt=2)])])
    with pytest.raises(ValueError, match="Warm-ups"):
        analyze_performance(
            [_source(tmp_path, rows=[_row(attempt=1), _row(attempt=2, warmup=True)])]
        )


def test_mixed_metadata_rejected(tmp_path):
    second = _row(attempt=2)
    second["seed"] = 99
    with pytest.raises(ValueError, match="Mixed"):
        analyze_performance([_source(tmp_path, rows=[_row(), second])])


def test_duplicate_input_does_not_double_count(tmp_path):
    path = _source(tmp_path)
    with pytest.raises(ValueError, match="Duplicate"):
        analyze_performance([path, path])


def test_mismatched_revision_does_not_compare(tmp_path):
    small = _source(tmp_path)
    medium_row = _row(profile="medium")
    medium_row["git_sha"] = "b" * 40
    medium = _source(tmp_path, "medium.jsonl", [medium_row])
    assert analyze_performance([small, medium])["comparisons"] == []


def test_mismatched_scenario_does_not_compare(tmp_path):
    small = _source(tmp_path)
    medium_row = _row(profile="medium")
    medium_row["scenario"] = "invalid_only"
    medium_row["experiment_id"] = "raw-silver-medium-invalid_only"
    medium = _source(tmp_path, "medium.jsonl", [medium_row])
    assert analyze_performance([small, medium])["comparisons"] == []


def test_success_and_failed_metrics_must_be_distinct(tmp_path):
    failed = _failed()
    failed["total_records"] = 50
    with pytest.raises(ValueError, match="Failed"):
        analyze_performance([_source(tmp_path, rows=[failed])])
    success = _row()
    success["failure_category"] = "parser_error"
    with pytest.raises(ValueError, match="Successful"):
        analyze_performance([_source(tmp_path, rows=[success])])


def test_invalid_json_and_bounds(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"elapsed_ns": NaN}\n')
    with pytest.raises(ValueError):
        load_benchmark_evidence(path)
    path.write_text("\n".join([json.dumps(_row())] * 101))
    with pytest.raises(ValueError, match="number"):
        load_benchmark_evidence(path)
    with pytest.raises(ValueError):
        analyze_performance([])


def test_outputs_are_stable_and_refuse_overwrite(tmp_path):
    input_file = _source(tmp_path)
    json_out = tmp_path / "report.json"
    md_out = tmp_path / "report.md"
    report = write_performance_analysis(
        inputs=[input_file], json_output=json_out, markdown_output=md_out
    )
    assert json.loads(json_out.read_text()) == report
    assert "Offline Raw-to-Silver" in md_out.read_text()
    json_bytes = json_out.read_bytes()
    md_bytes = md_out.read_bytes()
    with pytest.raises(FileExistsError):
        write_performance_analysis(
            inputs=[input_file], json_output=json_out, markdown_output=md_out
        )
    assert json_out.read_bytes() == json_bytes
    assert md_out.read_bytes() == md_bytes
    write_performance_analysis(
        inputs=[input_file],
        json_output=tmp_path / "report2.json",
        markdown_output=tmp_path / "report2.md",
    )
    assert (tmp_path / "report2.json").read_bytes() == json_bytes
    assert (tmp_path / "report2.md").read_bytes() == md_bytes


def test_output_preflight_and_no_partial_files(tmp_path):
    input_file = _source(tmp_path)
    json_out = tmp_path / "report.json"
    md_out = tmp_path / "report.md"
    md_out.write_text("existing")
    with pytest.raises(FileExistsError):
        write_performance_analysis(
            inputs=[input_file], json_output=json_out, markdown_output=md_out
        )
    assert not json_out.exists()
    assert md_out.read_text() == "existing"
    with pytest.raises(ValueError):
        write_performance_analysis(
            inputs=[input_file],
            json_output=tmp_path / "missing" / "out.json",
            markdown_output=tmp_path / "out.md",
        )


def test_input_symlink_is_rejected(tmp_path):
    path = _source(tmp_path)
    link = tmp_path / "link.jsonl"
    try:
        link.symlink_to(path)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation unavailable")
    with pytest.raises(ValueError, match="non-symlink"):
        analyze_performance([link])


def test_analysis_never_modifies_inputs(tmp_path):
    path = _source(tmp_path)
    original = path.read_bytes()
    one = copy.deepcopy(analyze_performance([path]))
    assert path.read_bytes() == original
    assert one["groups"][0]["input_sha256"] == one["input_sha256"]


def test_ambiguous_profile_evidence_skips_cross_tier_comparison(tmp_path):
    small = _source(tmp_path, "small.jsonl")
    another = _row()
    another["fixture_sha256"] = "f" * 64
    second_small = _source(tmp_path, "other-small.jsonl", [another])
    medium = _source(tmp_path, "medium.jsonl", [_row(profile="medium")])
    report = analyze_performance([small, second_small, medium])
    assert len(report["groups"]) == 3
    assert report["comparisons"] == []
