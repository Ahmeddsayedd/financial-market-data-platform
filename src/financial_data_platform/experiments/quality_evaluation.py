"""Offline comparison of verified M10 synthetic expectations with benchmark evidence.

This module does not execute ETL, contact providers, or connect to databases.
It never treats a parser failure as a financially rejected observation.
"""

import json
import math
import re
from pathlib import Path

from financial_data_platform.experiments.benchmark import (
    MAX_REPETITIONS,
    MAX_WARMUPS,
    RESULT_SCHEMA_VERSION,
    load_verified_workload,
)
from financial_data_platform.experiments.metrics import quality_metrics

EVALUATION_SCHEMA_VERSION = 1
MAX_EVIDENCE_BYTES = 2_000_000
FAILURE_CATEGORIES = frozenset(
    {
        "parser_error",
        "invalid_json",
        "file_io_error",
        "validation_error",
        "outcome_mismatch",
        "processing_error",
        "invalid_clock",
    }
)
SUCCESS_FIELDS = (
    "total_records",
    "valid_count",
    "invalid_count",
    "violation_counts",
    "acceptance_rate",
    "rejection_rate",
    "throughput_records_per_second",
)
EVIDENCE_FIELDS = frozenset(
    {
        "schema_version",
        "experiment_id",
        "git_sha",
        "fixture_sha256",
        "seed",
        "profile",
        "scenario",
        "symbol_count",
        "expected_unique_observations",
        "python_version",
        "stage",
        "attempt",
        "warmup",
        "status",
        "elapsed_ns",
        "failure_category",
        *SUCCESS_FIELDS,
    }
)
_GIT_SHA = re.compile(r"[0-9a-f]{40,64}\Z")
_VERSION = re.compile(r"[0-9]+(?:\.[0-9]+){1,3}\Z")
_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")


def _count(value: object, name: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"Invalid nonnegative integer: {name}")
    return value


def _fraction(value: object, name: str) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"Invalid finite fraction: {name}")
    if not 0 <= value <= 1:
        raise ValueError(f"Out-of-range fraction: {name}")
    return float(value)


def _result_path(output: Path, dataset: Path, evidence: Path) -> Path:
    """Permit only explicit, new .json reports, never inside the fixture tree."""
    requested = Path(output).expanduser()
    if requested.suffix != ".json":
        raise ValueError("Quality report must have a .json extension")
    if requested.exists() or requested.is_symlink():
        raise FileExistsError("Quality report already exists; overwrite forbidden")
    target = requested.resolve()
    if target == dataset or dataset in target.parents or target == evidence:
        raise ValueError("Quality report must not replace input evidence or dataset")
    repo = Path(__file__).resolve().parents[3]
    experiment_root = (repo / "data" / "experiments").resolve()
    if repo == target or repo in target.parents:
        if experiment_root not in target.parents:
            raise ValueError("Repository reports must stay under data/experiments/")
    if not target.parent.is_dir():
        raise ValueError("Quality report parent directory must already exist")
    return target


def _read_evidence(path: Path) -> list[dict]:
    if path.is_symlink() or not path.is_file():
        raise ValueError("Benchmark evidence must be a regular file")
    if path.suffix != ".jsonl" or path.stat().st_size > MAX_EVIDENCE_BYTES:
        raise ValueError("Unsupported or oversized benchmark evidence")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as exc:
        raise ValueError("Unable to read benchmark evidence") from exc
    if not 1 <= len(lines) <= MAX_WARMUPS + MAX_REPETITIONS:
        raise ValueError("Invalid benchmark attempt count")
    rows = []
    for line in lines:
        try:
            row = json.loads(line)
        except ValueError as exc:
            raise ValueError("Invalid benchmark JSONL") from exc
        if not isinstance(row, dict) or set(row) != EVIDENCE_FIELDS:
            raise ValueError("Unexpected benchmark result schema")
        rows.append(row)
    return rows


def _validate_row(row: dict, manifest: dict, index: int) -> None:
    """Reject malformed evidence; leave genuine outcome differences to comparison."""
    expected_identity = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "experiment_id": f"raw-silver-{manifest['profile']}-{manifest['scenario']}",
        "fixture_sha256": manifest["dataset_sha256"],
        "seed": manifest["seed"],
        "profile": manifest["profile"],
        "scenario": manifest["scenario"],
        "symbol_count": manifest["symbol_count"],
        "expected_unique_observations": manifest["expected_unique_observations"],
        "stage": "raw_to_silver",
    }
    if any(
        type(row.get(key)) is not type(value) or row[key] != value
        for key, value in expected_identity.items()
    ):
        raise ValueError("Benchmark fixture identity or schema mismatch")
    if row["git_sha"] is not None and (
        not isinstance(row["git_sha"], str) or not _GIT_SHA.fullmatch(row["git_sha"])
    ):
        raise ValueError("Invalid Git revision in evidence")
    if not isinstance(row["python_version"], str) or not _VERSION.fullmatch(
        row["python_version"]
    ):
        raise ValueError("Invalid Python version in evidence")
    if type(row["attempt"]) is not int or row["attempt"] != index + 1:
        raise ValueError("Benchmark attempts must be sequential")
    if type(row["warmup"]) is not bool:
        raise ValueError("Invalid warm-up marker")
    if row["status"] not in ("success", "failed"):
        raise ValueError("Invalid attempt status")
    elapsed = row["elapsed_ns"]
    if elapsed is not None:
        _count(elapsed, "elapsed_ns", minimum=1)
    if row["status"] == "failed":
        if (
            not isinstance(row["failure_category"], str)
            or row["failure_category"] not in FAILURE_CATEGORIES
        ):
            raise ValueError("Failed attempt lacks recognized failure category")
        if any(row[name] is not None for name in SUCCESS_FIELDS):
            raise ValueError("Failed attempts cannot report quality or throughput")
        return
    if elapsed is None or row["failure_category"] is not None:
        raise ValueError("Successful attempt requires timing and no failure category")
    total = _count(row["total_records"], "total_records")
    valid = _count(row["valid_count"], "valid_count")
    rejected = _count(row["invalid_count"], "invalid_count")
    computed = quality_metrics(
        total_records=total, valid_count=valid, invalid_count=rejected
    )
    codes = row["violation_counts"]
    if not isinstance(codes, dict) or len(codes) > 50:
        raise ValueError("Invalid violation occurrence mapping")
    for code, amount in codes.items():
        if not isinstance(code, str) or not _CODE.fullmatch(code):
            raise ValueError("Invalid violation code")
        _count(amount, "violation occurrence", minimum=1)
    for name in ("acceptance_rate", "rejection_rate"):
        actual = row[name]
        expected = getattr(computed, name)
        if expected is None:
            if actual is not None:
                raise ValueError("Empty batch must have undefined quality fraction")
        elif not math.isclose(
            _fraction(actual, name), expected, rel_tol=1e-12, abs_tol=1e-12
        ):
            raise ValueError("Reported quality fraction contradicts record counts")
    throughput = row["throughput_records_per_second"]
    if type(throughput) not in (float, int) or not math.isfinite(throughput):
        raise ValueError("Invalid throughput")
    if not math.isclose(
        throughput, total * 1_000_000_000 / elapsed, rel_tol=1e-9, abs_tol=1e-9
    ):
        raise ValueError("Throughput contradicts elapsed time and record count")


def evaluate_quality(
    *, dataset_dir: Path, benchmark_results: Path, output_path: Path
) -> dict:
    """Compare each measured attempt with generator expectations, writing once.

    A report's ``all_matched`` means *manifest-versus-evidence consistency*,
    not validation accuracy on real market observations or reproducible timing.
    """
    manifest, _ = load_verified_workload(dataset_dir)
    dataset = Path(dataset_dir).expanduser().resolve()
    requested_evidence = Path(benchmark_results).expanduser()
    if requested_evidence.is_symlink():
        raise ValueError("Benchmark evidence may not be a symlink")
    evidence = requested_evidence.resolve(strict=True)
    output = _result_path(output_path, dataset, evidence)
    rows = _read_evidence(evidence)
    for i, row in enumerate(rows):
        _validate_row(row, manifest, i)
    warmups = sum(row["warmup"] for row in rows)
    if not 1 <= len(rows) - warmups <= MAX_REPETITIONS or warmups > MAX_WARMUPS:
        raise ValueError("Invalid measured/warm-up attempt split")
    if [row["warmup"] for row in rows] != [True] * warmups + [False] * (
        len(rows) - warmups
    ):
        raise ValueError("Warm-up attempts must precede measured attempts")
    if len({(row["git_sha"], row["python_version"]) for row in rows}) != 1:
        raise ValueError(
            "Evidence must come from one source revision and Python version"
        )

    is_parser_case = manifest["scenario"] == "duplicate_date"
    expected = {
        "total_records": (
            manifest["expected_unique_observations"] if not is_parser_case else None
        ),
        "valid_count": manifest["expected_financial_valid"],
        "invalid_count": manifest["expected_financial_rejections"],
        "violation_counts": (
            manifest["expected_violation_occurrences_by_code"]
            if not is_parser_case
            else None
        ),
        "expected_status": "failed" if is_parser_case else "success",
        "expected_failure_category": "parser_error" if is_parser_case else None,
        "expected_parser_failed_batches_per_attempt": manifest[
            "expected_parser_failed_batches"
        ],
    }
    attempts = []
    for row in rows:
        differences = []
        if row["status"] != expected["expected_status"]:
            differences.append("status_mismatch")
        if is_parser_case:
            if row["failure_category"] != "parser_error":
                differences.append("parser_failure_mismatch")
        elif row["status"] == "success":
            for key in (
                "total_records",
                "valid_count",
                "invalid_count",
                "violation_counts",
            ):
                if row[key] != expected[key]:
                    differences.append(f"{key}_mismatch")
        else:
            differences.append("unexpected_processing_failure")
        attempts.append(
            {
                "attempt": row["attempt"],
                "warmup": row["warmup"],
                "status": row["status"],
                "failure_category": row["failure_category"],
                "elapsed_ns": row["elapsed_ns"],
                "observed_total_records": row["total_records"],
                "observed_valid_count": row["valid_count"],
                "observed_invalid_count": row["invalid_count"],
                "observed_violation_counts": row["violation_counts"],
                "observed_acceptance_rate": row["acceptance_rate"],
                "observed_rejection_rate": row["rejection_rate"],
                "matches_expected": not differences,
                "discrepancies": differences,
            }
        )
    measured = [row for row in attempts if not row["warmup"]]
    report = {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "benchmark_schema_version": RESULT_SCHEMA_VERSION,
        "fixture_sha256": manifest["dataset_sha256"],
        "seed": manifest["seed"],
        "profile": manifest["profile"],
        "scenario": manifest["scenario"],
        "git_sha": rows[0]["git_sha"],
        "python_version": rows[0]["python_version"],
        "expected_per_attempt": expected,
        "summary": {
            "warmup_attempts": warmups,
            "measured_attempts": len(measured),
            "measured_matching_attempts": sum(r["matches_expected"] for r in measured),
            "measured_mismatching_attempts": sum(
                not r["matches_expected"] for r in measured
            ),
            "measured_successes": sum(r["status"] == "success" for r in measured),
            "measured_failures": sum(r["status"] == "failed" for r in measured),
            "measured_parser_failures": sum(
                r["failure_category"] == "parser_error" for r in measured
            ),
            "measured_failure_rate": sum(r["status"] == "failed" for r in measured)
            / len(measured),
            "all_matched": all(r["matches_expected"] for r in measured),
        },
        "attempts": attempts,
    }
    # Exclusive creation prevents overwrites and concurrent write collisions.
    with output.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(report, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
    return report
