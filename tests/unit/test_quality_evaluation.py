"""M10 quality evidence contracts: true observed rows, no invented metrics."""

import json
from copy import deepcopy

import pytest

from financial_data_platform.experiments.benchmark import run_benchmark
from financial_data_platform.experiments.quality_evaluation import evaluate_quality
from financial_data_platform.experiments.workloads import write_workload


def _evidence(tmp_path, *, scenario="clean", invalid_count=0, warmups=1, reps=2):
    dataset = tmp_path / "dataset"
    manifest = write_workload(
        output_dir=dataset, scenario=scenario, invalid_count=invalid_count
    )
    results = tmp_path / "benchmark.jsonl"
    rows = run_benchmark(
        dataset_dir=dataset,
        result_path=results,
        repetitions=reps,
        warmups=warmups,
    )
    return dataset, manifest, results, rows


def _evaluate(tmp_path, dataset, results, *, name="quality.json"):
    output = tmp_path / name
    report = evaluate_quality(
        dataset_dir=dataset, benchmark_results=results, output_path=output
    )
    assert json.loads(output.read_text(encoding="utf-8")) == report
    return report


def _rewrite(path, rows):
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def test_clean_counts_and_warmup_are_separate(tmp_path):
    dataset, manifest, results, _ = _evidence(tmp_path)
    report = _evaluate(tmp_path, dataset, results)
    assert report["fixture_sha256"] == manifest["dataset_sha256"]
    assert report["expected_per_attempt"]["total_records"] == 100
    assert report["expected_per_attempt"]["invalid_count"] == 0
    assert report["summary"] == {
        "warmup_attempts": 1,
        "measured_attempts": 2,
        "measured_matching_attempts": 2,
        "measured_mismatching_attempts": 0,
        "measured_successes": 2,
        "measured_failures": 0,
        "measured_parser_failures": 0,
        "measured_failure_rate": 0.0,
        "all_matched": True,
    }
    assert [a["warmup"] for a in report["attempts"]] == [True, False, False]
    assert all(a["observed_rejection_rate"] == 0.0 for a in report["attempts"])


def test_mixed_counts_and_per_code_occurrences(tmp_path):
    dataset, manifest, results, _ = _evidence(
        tmp_path, scenario="mixed", invalid_count=10, warmups=0, reps=1
    )
    report = _evaluate(tmp_path, dataset, results)
    observed = report["attempts"][0]
    assert observed["observed_total_records"] == 100
    assert observed["observed_valid_count"] == 90
    assert observed["observed_invalid_count"] == 10
    assert observed["observed_rejection_rate"] == 0.1
    assert (
        observed["observed_violation_counts"]
        == manifest["expected_violation_occurrences_by_code"]
    )
    assert sum(observed["observed_violation_counts"].values()) >= 10
    assert report["summary"]["all_matched"] is True


def test_invalid_only_has_one_hundred_financial_rejections(tmp_path):
    dataset, _, results, _ = _evidence(
        tmp_path, scenario="invalid_only", warmups=0, reps=1
    )
    report = _evaluate(tmp_path, dataset, results)
    attempt = report["attempts"][0]
    assert attempt["status"] == "success"
    assert attempt["observed_valid_count"] == 0
    assert attempt["observed_invalid_count"] == 100
    assert attempt["observed_rejection_rate"] == 1.0
    assert attempt["matches_expected"] is True


def test_parser_failure_matches_without_financial_rates(tmp_path):
    dataset, _, results, rows = _evidence(
        tmp_path, scenario="duplicate_date", warmups=1, reps=2
    )
    assert all(r["status"] == "failed" for r in rows)
    report = _evaluate(tmp_path, dataset, results)
    assert report["expected_per_attempt"]["total_records"] is None
    assert (
        report["expected_per_attempt"]["expected_parser_failed_batches_per_attempt"]
        == 1
    )
    assert report["summary"]["all_matched"] is True
    assert report["summary"]["measured_parser_failures"] == 2
    assert report["summary"]["measured_failure_rate"] == 1.0
    assert all(a["observed_rejection_rate"] is None for a in report["attempts"])


def test_count_mismatch_preserved_as_discrepancy(tmp_path):
    dataset, _, results, rows = _evidence(tmp_path, warmups=0, reps=1)
    rows[0]["valid_count"] = 99
    rows[0]["invalid_count"] = 1
    rows[0]["acceptance_rate"] = 0.99
    rows[0]["rejection_rate"] = 0.01
    rows[0]["violation_counts"] = {"NEGATIVE_VOLUME": 1}
    _rewrite(results, rows)
    report = _evaluate(tmp_path, dataset, results)
    assert report["summary"]["all_matched"] is False
    assert report["summary"]["measured_mismatching_attempts"] == 1
    assert "valid_count_mismatch" in report["attempts"][0]["discrepancies"]
    assert "invalid_count_mismatch" in report["attempts"][0]["discrepancies"]
    assert "violation_counts_mismatch" in report["attempts"][0]["discrepancies"]


def test_unexpected_failure_is_not_a_zero_rejection_rate(tmp_path):
    dataset, _, results, rows = _evidence(tmp_path, warmups=0, reps=1)
    rows[0]["status"] = "failed"
    rows[0]["failure_category"] = "processing_error"
    for key in (
        "total_records",
        "valid_count",
        "invalid_count",
        "violation_counts",
        "acceptance_rate",
        "rejection_rate",
        "throughput_records_per_second",
    ):
        rows[0][key] = None
    _rewrite(results, rows)
    report = _evaluate(tmp_path, dataset, results)
    assert report["summary"]["measured_failures"] == 1
    assert report["summary"]["measured_failure_rate"] == 1.0
    assert report["attempts"][0]["observed_rejection_rate"] is None
    assert report["summary"]["all_matched"] is False


def test_parser_failure_wrong_category_is_discrepancy(tmp_path):
    dataset, _, results, rows = _evidence(
        tmp_path, scenario="duplicate_date", warmups=0, reps=1
    )
    rows[0]["failure_category"] = "processing_error"
    _rewrite(results, rows)
    report = _evaluate(tmp_path, dataset, results)
    assert "parser_failure_mismatch" in report["attempts"][0]["discrepancies"]


def test_tampered_fixture_rejected_before_output(tmp_path):
    dataset, _, results, _ = _evidence(tmp_path, warmups=0, reps=1)
    path = dataset / "raw" / "SYN0001.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="checksum"):
        _evaluate(tmp_path, dataset, results)
    assert not (tmp_path / "quality.json").exists()


def test_evidence_with_wrong_fixture_hash_rejected(tmp_path):
    dataset, _, results, rows = _evidence(tmp_path, warmups=0, reps=1)
    rows[0]["fixture_sha256"] = "0" * 64
    _rewrite(results, rows)
    with pytest.raises(ValueError, match="identity"):
        _evaluate(tmp_path, dataset, results)


@pytest.mark.parametrize("field", ["acceptance_rate", "rejection_rate"])
def test_inconsistent_quality_rate_rejected(tmp_path, field):
    dataset, _, results, rows = _evidence(tmp_path, warmups=0, reps=1)
    rows[0][field] = 0.5
    _rewrite(results, rows)
    with pytest.raises(ValueError, match="fraction"):
        _evaluate(tmp_path, dataset, results)


def test_inconsistent_throughput_rejected(tmp_path):
    dataset, _, results, rows = _evidence(tmp_path, warmups=0, reps=1)
    rows[0]["throughput_records_per_second"] = 0.0
    _rewrite(results, rows)
    with pytest.raises(ValueError, match="Throughput"):
        _evaluate(tmp_path, dataset, results)


def test_failed_attempt_with_success_counts_rejected(tmp_path):
    dataset, _, results, rows = _evidence(tmp_path, warmups=0, reps=1)
    rows[0]["status"] = "failed"
    rows[0]["failure_category"] = "parser_error"
    _rewrite(results, rows)
    with pytest.raises(ValueError, match="Failed attempts"):
        _evaluate(tmp_path, dataset, results)


def test_attempts_out_of_order_rejected(tmp_path):
    dataset, _, results, rows = _evidence(tmp_path)
    rows[0], rows[1] = rows[1], rows[0]
    _rewrite(results, rows)
    with pytest.raises(ValueError, match="sequential"):
        _evaluate(tmp_path, dataset, results)


def test_warmup_after_measurement_rejected(tmp_path):
    dataset, _, results, rows = _evidence(tmp_path)
    rows[0]["warmup"] = False
    rows[1]["warmup"] = True
    _rewrite(results, rows)
    with pytest.raises(ValueError, match="Warm-up"):
        _evaluate(tmp_path, dataset, results)


def test_malformed_jsonl_rejected(tmp_path):
    dataset, _, results, _ = _evidence(tmp_path, warmups=0, reps=1)
    results.write_text("not-json\n", encoding="utf-8")
    with pytest.raises(ValueError, match="JSONL"):
        _evaluate(tmp_path, dataset, results)


def test_additional_secret_bearing_field_rejected(tmp_path):
    dataset, _, results, rows = _evidence(tmp_path, warmups=0, reps=1)
    rows[0]["provider_token"] = "DO_NOT_RETAIN"
    _rewrite(results, rows)
    with pytest.raises(ValueError, match="schema"):
        _evaluate(tmp_path, dataset, results)
    assert not (tmp_path / "quality.json").exists()


def test_existing_report_cannot_be_overwritten(tmp_path):
    dataset, _, results, _ = _evidence(tmp_path, warmups=0, reps=1)
    first = _evaluate(tmp_path, dataset, results)
    previous = (tmp_path / "quality.json").read_bytes()
    with pytest.raises(FileExistsError):
        _evaluate(tmp_path, dataset, results)
    assert (tmp_path / "quality.json").read_bytes() == previous
    assert first["summary"]["all_matched"] is True


def test_report_inside_dataset_rejected(tmp_path):
    dataset, _, results, _ = _evidence(tmp_path, warmups=0, reps=1)
    with pytest.raises(ValueError, match="input evidence or dataset"):
        evaluate_quality(
            dataset_dir=dataset,
            benchmark_results=results,
            output_path=dataset / "report.json",
        )


def test_report_parent_must_exist(tmp_path):
    dataset, _, results, _ = _evidence(tmp_path, warmups=0, reps=1)
    with pytest.raises(ValueError, match="parent"):
        evaluate_quality(
            dataset_dir=dataset,
            benchmark_results=results,
            output_path=tmp_path / "missing" / "quality.json",
        )


def test_no_db_or_provider_network_required(tmp_path, monkeypatch):
    import socket

    def deny(*args, **kwargs):
        raise AssertionError("Unexpected network access")

    monkeypatch.setattr(socket, "create_connection", deny)
    dataset, _, results, _ = _evidence(tmp_path, warmups=0, reps=1)
    report = _evaluate(tmp_path, dataset, results)
    assert report["summary"]["all_matched"] is True


def test_same_benchmark_evidence_preserves_observed_counts(tmp_path):
    dataset, _, results, original_rows = _evidence(
        tmp_path, scenario="mixed", invalid_count=12, warmups=1, reps=1
    )
    report = _evaluate(tmp_path, dataset, results)
    for evidence_row, report_row in zip(original_rows, report["attempts"], strict=True):
        assert evidence_row["valid_count"] == report_row["observed_valid_count"]
        assert evidence_row["invalid_count"] == report_row["observed_invalid_count"]
        assert (
            evidence_row["violation_counts"] == report_row["observed_violation_counts"]
        )
    assert deepcopy(original_rows) == original_rows
