"""Offline, bounded Raw-to-Silver benchmark; no provider or database calls.

Only `process_raw_market_data` is timed. Fixture validation, temporary file
copying, aggregation and JSONL persistence are deliberately outside the clock.
"""

import hashlib
import json
import platform
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path

from financial_data_platform.experiments.metrics import (
    quality_metrics,
    throughput_records_per_second,
)
from financial_data_platform.experiments.workloads import (
    EXTRACTED_AT,
    GENERATOR_VERSION,
    PROFILES,
    SCENARIOS,
    build_payloads,
)
from financial_data_platform.processing.raw_market_data import process_raw_market_data
from financial_data_platform.providers.twelve_data.parser import TwelveDataParseError
from financial_data_platform.storage.quarantine import QuarantineWriter
from financial_data_platform.storage.silver import SilverWriter

RESULT_SCHEMA_VERSION = 1
MAX_REPETITIONS = 20
MAX_WARMUPS = 5
SHA256_PATTERN = re.compile(r"[a-f0-9]{64}\Z")
RAW_NAME_PATTERN = re.compile(r"raw/SYN[0-9]{4,}.json\Z")


def _canonical_bytes(obj: object) -> bytes:
    return (
        json.dumps(obj, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode("utf-8")


def _nonnegative_int(value: object, label: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{label} must be an integer >= {minimum}")
    return value


def _safe_result_path(output: Path, dataset: Path) -> Path:
    """Prevent writes to the checkout except ignored experiment artifacts."""
    requested = Path(output).expanduser()
    if requested.suffix != ".jsonl":
        raise ValueError("Result path must end in .jsonl")
    if requested.exists() or requested.is_symlink():
        raise FileExistsError("Result file already exists; overwrite forbidden")
    target = requested.resolve()
    if target == dataset or dataset in target.parents:
        raise ValueError("Results must not be written inside the input dataset")
    repo = Path(__file__).resolve().parents[3]
    experiment_root = (repo / "data" / "experiments").resolve()
    if repo == target or repo in target.parents:
        if experiment_root not in target.parents:
            raise ValueError("Repository results must stay under data/experiments/")
    if not target.parent.is_dir():
        raise ValueError("Result parent directory must already exist")
    return target


def load_verified_workload(dataset_dir: Path) -> tuple[dict, list[Path]]:
    """Verify schema, generator expectations, all file hashes and their inventory."""
    dataset = Path(dataset_dir).expanduser().resolve(strict=True)
    if not dataset.is_dir():
        raise ValueError("Input dataset must be a directory")
    manifest_path = dataset / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("Missing or unsafe workload manifest")
    if manifest_path.stat().st_size > 1_000_000:
        raise ValueError("Workload manifest exceeds size limit")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ValueError("Invalid workload manifest") from exc
    if not isinstance(manifest, dict):
        raise ValueError("Workload manifest must be a JSON object")
    if (
        type(manifest.get("schema_version")) is not int
        or manifest["schema_version"] != 1
        or type(manifest.get("generator_version")) is not int
        or manifest["generator_version"] != GENERATOR_VERSION
    ):
        raise ValueError("Unsupported workload manifest or generator version")
    if (
        manifest.get("synthetic") is not True
        or manifest.get("extracted_at") != EXTRACTED_AT
    ):
        raise ValueError("Workload is not a supported fixed-time synthetic fixture")
    profile, scenario = manifest.get("profile"), manifest.get("scenario")
    if profile not in PROFILES or scenario not in SCENARIOS:
        raise ValueError("Unsupported workload profile or scenario")
    seed = _nonnegative_int(manifest.get("seed"), "seed")
    symbols = _nonnegative_int(manifest.get("symbol_count"), "symbol_count", minimum=1)
    invalid = manifest.get("expected_financial_rejections")
    if scenario == "mixed":
        invalid = _nonnegative_int(invalid, "expected_financial_rejections", minimum=1)
    else:
        invalid = 0
    try:
        payloads, expected = build_payloads(
            profile=profile,
            seed=seed,
            symbol_count=symbols,
            scenario=scenario,
            invalid_count=invalid,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid workload generation parameters") from exc
    if any(manifest.get(key) != value for key, value in expected.items()):
        raise ValueError("Manifest expectation does not match generator configuration")
    hashes = manifest.get("file_sha256")
    if not isinstance(hashes, dict) or len(hashes) != symbols:
        raise ValueError("Invalid workload file inventory")
    expected_names = {f"raw/{symbol}.json" for symbol in payloads}
    if set(hashes) != expected_names:
        raise ValueError("Workload file inventory does not match expected symbols")
    if not all(RAW_NAME_PATTERN.fullmatch(name) for name in hashes):
        raise ValueError("Unsafe workload file name")
    if not all(
        isinstance(h, str) and SHA256_PATTERN.fullmatch(h) for h in hashes.values()
    ):
        raise ValueError("Invalid workload file checksum")
    digest = manifest.get("dataset_sha256")
    if not isinstance(digest, str) or not SHA256_PATTERN.fullmatch(digest):
        raise ValueError("Invalid aggregate workload checksum")
    if hashlib.sha256(_canonical_bytes(hashes)).hexdigest() != digest:
        raise ValueError("Dataset checksum mismatch")
    raw_dir = dataset / "raw"
    if raw_dir.is_symlink() or not raw_dir.is_dir():
        raise ValueError("Missing or unsafe raw directory")
    paths = []
    for filename in sorted(hashes):
        file = dataset / filename
        if file.is_symlink() or not file.is_file():
            raise ValueError("Missing or unsafe workload file")
        if hashlib.sha256(file.read_bytes()).hexdigest() != hashes[filename]:
            raise ValueError("Workload file checksum mismatch")
        paths.append(file)
    if {p.name for p in raw_dir.iterdir()} != {p.name for p in paths}:
        raise ValueError("Unexpected files in raw dataset")
    return manifest, paths


def _git_revision() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--verify", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
            cwd=Path(__file__).resolve().parents[3],
        )
    except (OSError, subprocess.SubprocessError):
        return None
    revision = result.stdout.strip()
    return revision if re.fullmatch(r"[0-9a-f]{40,64}", revision) else None


def _error_category(exc: Exception) -> str:
    # Never store exception messages or tracebacks: they can contain sensitive paths.
    if isinstance(exc, TwelveDataParseError):
        return "parser_error"
    if isinstance(exc, json.JSONDecodeError):
        return "invalid_json"
    if isinstance(exc, (OSError, UnicodeError)):
        return "file_io_error"
    if isinstance(exc, ValueError):
        return "validation_error"
    return "processing_error"


def run_benchmark(
    *, dataset_dir: Path, result_path: Path, repetitions: int = 5, warmups: int = 1
) -> list[dict]:
    """Execute isolated attempts and write JSONL once, refusing existing results.

    Exceptions from an attempted stage produce a failed row, never fabricated
    quality counts or throughput. Failed attempts do not prevent later trials.
    """
    repetitions = _nonnegative_int(repetitions, "repetitions", minimum=1)
    warmups = _nonnegative_int(warmups, "warmups")
    if repetitions > MAX_REPETITIONS or warmups > MAX_WARMUPS:
        raise ValueError("Benchmark repetition or warm-up limit exceeded")
    manifest, inputs = load_verified_workload(dataset_dir)
    dataset = Path(dataset_dir).expanduser().resolve()
    output = _safe_result_path(result_path, dataset)
    extracted_at = datetime.fromisoformat(manifest["extracted_at"])
    revision = _git_revision()
    rows = []
    for trial in range(warmups + repetitions):
        is_warmup = trial < warmups
        row = {
            "schema_version": RESULT_SCHEMA_VERSION,
            "experiment_id": f"raw-silver-{manifest['profile']}-{manifest['scenario']}",
            "git_sha": revision,
            "fixture_sha256": manifest["dataset_sha256"],
            "seed": manifest["seed"],
            "profile": manifest["profile"],
            "scenario": manifest["scenario"],
            "symbol_count": manifest["symbol_count"],
            "expected_unique_observations": manifest["expected_unique_observations"],
            "python_version": platform.python_version(),
            "stage": "raw_to_silver",
            "attempt": trial + 1,
            "warmup": is_warmup,
            "status": "failed",
            "elapsed_ns": None,
            "total_records": None,
            "valid_count": None,
            "invalid_count": None,
            "violation_counts": None,
            "acceptance_rate": None,
            "rejection_rate": None,
            "throughput_records_per_second": None,
            "failure_category": None,
        }
        with tempfile.TemporaryDirectory(prefix="market-benchmark-") as temp:
            root = Path(temp)
            raw = root / "raw"
            raw.mkdir()
            # Copying fixture files is outside the timed ETL stage.
            copies = []
            for source in inputs:
                dest = raw / source.name
                shutil.copyfile(source, dest)
                copies.append(dest)
            silver_writer = SilverWriter(root / "silver")
            quarantine_writer = QuarantineWriter(root / "quarantine")
            start = time.perf_counter_ns()
            try:
                results = [
                    process_raw_market_data(
                        raw_path=path,
                        silver_writer=silver_writer,
                        quarantine_writer=quarantine_writer,
                        extracted_at=extracted_at,
                        detected_at=extracted_at,
                    )
                    for path in copies
                ]
            except Exception as exc:
                elapsed = time.perf_counter_ns() - start
                if elapsed > 0:
                    row["elapsed_ns"] = elapsed
                row["failure_category"] = _error_category(exc)
            else:
                elapsed = time.perf_counter_ns() - start
                if elapsed <= 0:
                    row["failure_category"] = "invalid_clock"
                else:
                    total = sum(result.total_records for result in results)
                    valid = sum(result.valid_count for result in results)
                    invalid = sum(result.invalid_count for result in results)
                    violations: dict[str, int] = {}
                    for result in results:
                        if len(result.quarantine_paths) != result.invalid_count:
                            raise RuntimeError("Invalid quarantine record count")
                        for key, count in result.quality_report[
                            "violation_counts"
                        ].items():
                            violations[key] = violations.get(key, 0) + count
                    quality = quality_metrics(
                        total_records=total, valid_count=valid, invalid_count=invalid
                    )
                    if (
                        total != manifest["expected_unique_observations"]
                        or valid != manifest["expected_financial_valid"]
                        or invalid != manifest["expected_financial_rejections"]
                        or dict(sorted(violations.items()))
                        != manifest["expected_violation_occurrences_by_code"]
                    ):
                        row["failure_category"] = "outcome_mismatch"
                    else:
                        row.update(
                            status="success",
                            elapsed_ns=elapsed,
                            total_records=total,
                            valid_count=valid,
                            invalid_count=invalid,
                            violation_counts=dict(sorted(violations.items())),
                            acceptance_rate=quality.acceptance_rate,
                            rejection_rate=quality.rejection_rate,
                            throughput_records_per_second=throughput_records_per_second(
                                records=total, elapsed_seconds=elapsed / 1_000_000_000
                            ),
                        )
            rows.append(row)
    # Exclusive creation protects existing files, including concurrent writers.
    with output.open("x", encoding="utf-8", newline="\n") as file:
        for row in rows:
            file.write(_canonical_bytes(row).decode("utf-8"))
    return rows
