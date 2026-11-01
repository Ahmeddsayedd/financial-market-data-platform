"""Offline bounded benchmark contracts; each run uses isolated temporary paths."""

import hashlib
import json
from pathlib import Path

import pytest

from financial_data_platform.experiments import benchmark
from financial_data_platform.experiments.workloads import write_workload


def _dataset(tmp_path, **kwargs):
    folder = tmp_path / "dataset"
    manifest = write_workload(output_dir=folder, **kwargs)
    return folder, manifest


def _records(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_clean_benchmark_has_real_counts_and_throughput(tmp_path):
    dataset, manifest = _dataset(tmp_path)
    output = tmp_path / "results.jsonl"
    rows = benchmark.run_benchmark(
        dataset_dir=dataset, result_path=output, repetitions=2, warmups=1
    )
    assert rows == _records(output)
    assert [row["warmup"] for row in rows] == [True, False, False]
    assert [row["attempt"] for row in rows] == [1, 2, 3]
    assert all(row["status"] == "success" for row in rows)
    assert all(row["total_records"] == 100 for row in rows)
    assert all(row["valid_count"] == 100 for row in rows)
    assert all(row["invalid_count"] == 0 for row in rows)
    assert all(row["acceptance_rate"] == 1.0 for row in rows)
    assert all(row["rejection_rate"] == 0.0 for row in rows)
    assert all(row["elapsed_ns"] > 0 for row in rows)
    assert all(row["throughput_records_per_second"] > 0 for row in rows)
    assert all(row["fixture_sha256"] == manifest["dataset_sha256"] for row in rows)
    assert all(row["failure_category"] is None for row in rows)


def test_mixed_rejections_and_violation_occurrences(tmp_path):
    dataset, manifest = _dataset(tmp_path, scenario="mixed", invalid_count=10)
    rows = benchmark.run_benchmark(
        dataset_dir=dataset,
        result_path=tmp_path / "out.jsonl",
        repetitions=1,
        warmups=0,
    )
    row = rows[0]
    assert row["status"] == "success"
    assert (row["total_records"], row["valid_count"], row["invalid_count"]) == (
        100,
        90,
        10,
    )
    assert row["rejection_rate"] == 0.1
    assert row["violation_counts"] == manifest["expected_violation_occurrences_by_code"]
    assert sum(row["violation_counts"].values()) >= 10


def test_invalid_only_still_a_successful_processing_attempt(tmp_path):
    dataset, _ = _dataset(tmp_path, scenario="invalid_only")
    row = benchmark.run_benchmark(
        dataset_dir=dataset,
        result_path=tmp_path / "out.jsonl",
        repetitions=1,
        warmups=0,
    )[0]
    assert row["status"] == "success"
    assert row["valid_count"] == 0
    assert row["invalid_count"] == 100
    assert row["rejection_rate"] == 1.0


def test_duplicate_date_failure_has_no_fabricated_metrics(tmp_path):
    dataset, _ = _dataset(tmp_path, scenario="duplicate_date")
    rows = benchmark.run_benchmark(
        dataset_dir=dataset,
        result_path=tmp_path / "out.jsonl",
        repetitions=2,
        warmups=1,
    )
    assert len(rows) == 3
    for row in rows:
        assert row["status"] == "failed"
        assert row["failure_category"] == "parser_error"
        assert row["elapsed_ns"] > 0
        assert row["total_records"] is None
        assert row["throughput_records_per_second"] is None
        assert row["violation_counts"] is None
        assert row["rejection_rate"] is None


def test_result_file_refuses_overwrite_and_keeps_original(tmp_path):
    dataset, _ = _dataset(tmp_path)
    output = tmp_path / "results.jsonl"
    benchmark.run_benchmark(
        dataset_dir=dataset, result_path=output, repetitions=1, warmups=0
    )
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        benchmark.run_benchmark(
            dataset_dir=dataset, result_path=output, repetitions=1, warmups=0
        )
    assert output.read_bytes() == before


def test_corrupted_fixture_is_rejected_before_results_are_created(tmp_path):
    dataset, _ = _dataset(tmp_path)
    file = dataset / "raw/SYN0001.json"
    file.write_bytes(file.read_bytes() + b" ")
    output = tmp_path / "out.jsonl"
    with pytest.raises(ValueError, match="checksum"):
        benchmark.run_benchmark(
            dataset_dir=dataset, result_path=output, repetitions=1, warmups=0
        )
    assert not output.exists()


def test_corrupted_aggregate_checksum_is_rejected(tmp_path):
    dataset, _ = _dataset(tmp_path)
    manifest_file = dataset / "manifest.json"
    manifest = json.loads(manifest_file.read_text())
    manifest["dataset_sha256"] = "0" * 64
    manifest_file.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="checksum"):
        benchmark.load_verified_workload(dataset)


def test_modified_manifest_counts_are_rejected(tmp_path):
    dataset, _ = _dataset(tmp_path)
    manifest_file = dataset / "manifest.json"
    manifest = json.loads(manifest_file.read_text())
    manifest["expected_financial_valid"] = 99
    manifest_file.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="expectation"):
        benchmark.load_verified_workload(dataset)


@pytest.mark.parametrize(
    "repetitions,warmups", [(0, 0), (21, 0), (1, 6), (True, 0), (1, -1)]
)
def test_unbounded_or_invalid_attempt_count_rejected(tmp_path, repetitions, warmups):
    with pytest.raises(ValueError):
        benchmark.run_benchmark(
            dataset_dir=tmp_path,
            result_path=tmp_path / "out.jsonl",
            repetitions=repetitions,
            warmups=warmups,
        )


def test_results_inside_fixture_directory_are_rejected(tmp_path):
    dataset, _ = _dataset(tmp_path)
    with pytest.raises(ValueError, match="inside"):
        benchmark.run_benchmark(
            dataset_dir=dataset,
            result_path=dataset / "results.jsonl",
            repetitions=1,
            warmups=0,
        )


def test_result_parent_must_exist(tmp_path):
    dataset, _ = _dataset(tmp_path)
    with pytest.raises(ValueError, match="parent"):
        benchmark.run_benchmark(
            dataset_dir=dataset,
            result_path=tmp_path / "missing" / "results.jsonl",
            repetitions=1,
            warmups=0,
        )


def test_output_extension_is_jsonl(tmp_path):
    dataset, _ = _dataset(tmp_path)
    with pytest.raises(ValueError, match="jsonl"):
        benchmark.run_benchmark(
            dataset_dir=dataset,
            result_path=tmp_path / "results.txt",
            repetitions=1,
            warmups=0,
        )


def test_manifest_checksums_are_sha256(tmp_path):
    dataset, manifest = _dataset(tmp_path)
    validated, files = benchmark.load_verified_workload(dataset)
    assert validated == manifest
    assert len(files) == manifest["symbol_count"]
    for path in files:
        assert (
            hashlib.sha256(path.read_bytes()).hexdigest()
            == manifest["file_sha256"][f"raw/{path.name}"]
        )


def test_repeated_attempts_use_distinct_temporary_directories(tmp_path, monkeypatch):
    dataset, _ = _dataset(tmp_path)
    original = benchmark.process_raw_market_data
    paths: list[Path] = []

    def inspect(**kwargs):
        paths.append(kwargs["silver_writer"].base_dir)
        return original(**kwargs)

    monkeypatch.setattr(benchmark, "process_raw_market_data", inspect)
    rows = benchmark.run_benchmark(
        dataset_dir=dataset,
        result_path=tmp_path / "results.jsonl",
        repetitions=2,
        warmups=0,
    )
    assert len(rows) == 2
    assert len(paths) == 8
    assert len({p for p in paths}) == 2
    assert all(not p.exists() for p in paths)


def test_no_db_or_network_dependency(tmp_path, monkeypatch):
    import socket

    def deny(*args, **kwargs):
        raise AssertionError("Unexpected network access")

    monkeypatch.setattr(socket, "create_connection", deny)
    dataset, _ = _dataset(tmp_path)
    rows = benchmark.run_benchmark(
        dataset_dir=dataset,
        result_path=tmp_path / "results.jsonl",
        repetitions=1,
        warmups=0,
    )
    assert rows[0]["status"] == "success"


def test_failed_processing_exception_message_not_leaked(tmp_path, monkeypatch):
    dataset, _ = _dataset(tmp_path)

    def fail(**kwargs):
        raise RuntimeError("SECRET_VALUE_DO_NOT_PRINT")

    monkeypatch.setattr(benchmark, "process_raw_market_data", fail)
    output = tmp_path / "results.jsonl"
    row = benchmark.run_benchmark(
        dataset_dir=dataset,
        result_path=output,
        repetitions=1,
        warmups=0,
    )[0]
    assert row["status"] == "failed"
    assert row["failure_category"] == "processing_error"
    assert "SECRET_VALUE_DO_NOT_PRINT" not in output.read_text(encoding="utf-8")
