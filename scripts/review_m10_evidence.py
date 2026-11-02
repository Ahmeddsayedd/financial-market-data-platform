"""Read-only cross-check of locally generated M10 experiment evidence.

This is a provenance/contract review, not an experiment runner or proof of DB rollback.
"""

import argparse
import hashlib
import json
import re
from pathlib import Path

_SHA = re.compile(r"[0-9a-f]{64}\Z")
_PROFILES = {"small": 100, "medium": 1000, "large": 10000}
_SCENARIOS = ("clean", "mixed", "invalid_only", "duplicate_date")
_GOLD = ("initial", "replay", "newer_update", "stale_replay", "equal_time_conflict")
_MAX_BYTES = 2_000_000


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _json(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > _MAX_BYTES:
        raise ValueError("Missing, unsafe, or oversized evidence file")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Expected JSON object")
    return data


def _hash(value: object) -> bool:
    return isinstance(value, str) and _SHA.fullmatch(value) is not None


def review_fixture(path: Path) -> dict:
    path = Path(path)
    if path.is_symlink() or not path.is_dir():
        raise ValueError("Fixture must be a regular directory")
    manifest = _json(path / "manifest.json")
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported fixture schema")
    profile = manifest.get("profile")
    if profile not in _PROFILES or manifest.get("scenario") not in _SCENARIOS:
        raise ValueError("Unsupported fixture profile or scenario")
    if manifest.get("expected_unique_observations") != _PROFILES[profile]:
        raise ValueError("Incorrect fixture observation count")
    hashes = manifest.get("file_sha256")
    if not isinstance(hashes, dict) or len(hashes) != manifest.get("symbol_count"):
        raise ValueError("Invalid fixture inventory")
    if not all(re.fullmatch(r"raw/SYN[0-9]{4,}\.json", key) for key in hashes):
        raise ValueError("Unsafe fixture file inventory")
    raw = path / "raw"
    if raw.is_symlink() or not raw.is_dir():
        raise ValueError("Missing or unsafe fixture raw directory")
    if {f"raw/{p.name}" for p in raw.iterdir()} != set(hashes):
        raise ValueError("Unexpected fixture raw files")
    for name, expected in hashes.items():
        item = path / name
        if not _hash(expected) or item.is_symlink() or not item.is_file():
            raise ValueError("Invalid fixture file or hash")
        if item.stat().st_size > _MAX_BYTES or _digest(item.read_bytes()) != expected:
            raise ValueError("Fixture file hash mismatch")
    aggregate = (
        json.dumps(hashes, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode()
    if _digest(aggregate) != manifest.get("dataset_sha256"):
        raise ValueError("Fixture inventory digest mismatch")
    return manifest


def review_benchmark(path: Path, manifest: dict) -> tuple[str, list[dict]]:
    path = Path(path)
    if path.suffix != ".jsonl" or path.is_symlink() or not path.is_file():
        raise ValueError("Benchmark must be a regular JSONL file")
    if path.stat().st_size > _MAX_BYTES:
        raise ValueError("Oversized benchmark")
    data = path.read_bytes()
    lines = data.decode("utf-8").splitlines()
    if not 1 <= len(lines) <= 25:
        raise ValueError("Invalid benchmark attempt count")
    rows = [json.loads(line) for line in lines]
    expected = {
        "schema_version": 1,
        "experiment_id": f"raw-silver-{manifest['profile']}-{manifest['scenario']}",
        "fixture_sha256": manifest["dataset_sha256"],
        "profile": manifest["profile"],
        "scenario": manifest["scenario"],
        "seed": manifest["seed"],
        "symbol_count": manifest["symbol_count"],
        "expected_unique_observations": manifest["expected_unique_observations"],
        "stage": "raw_to_silver",
    }
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict) or any(
            row.get(k) != v for k, v in expected.items()
        ):
            raise ValueError("Benchmark fixture identity mismatch")
        if type(row.get("attempt")) is not int or row["attempt"] != index:
            raise ValueError("Nonconsecutive benchmark attempts")
        if type(row.get("warmup")) is not bool or row.get("status") not in (
            "success",
            "failed",
        ):
            raise ValueError("Invalid attempt status")
        if row["status"] == "success":
            if type(row.get("elapsed_ns")) is not int or row["elapsed_ns"] <= 0:
                raise ValueError("Invalid successful attempt timing")
            if row.get("total_records") != manifest["expected_unique_observations"]:
                raise ValueError("Benchmark records inconsistent with fixture")
        else:
            if not row.get("failure_category"):
                raise ValueError("Failed attempt lacks category")
    warmups = sum(row["warmup"] for row in rows)
    if warmups > 5 or len(rows) - warmups not in range(1, 21):
        raise ValueError("Invalid warmup/measured split")
    if [r["warmup"] for r in rows] != [True] * warmups + [False] * (
        len(rows) - warmups
    ):
        raise ValueError("Warmups must precede measured attempts")
    if len({(r.get("git_sha"), r.get("python_version")) for r in rows}) != 1:
        raise ValueError("Inconsistent benchmark runtime identity")
    return _digest(data), rows


def review_quality(
    path: Path, manifests: list[dict], rows_by_digest: dict[str, list[dict]]
) -> None:
    report = _json(Path(path))
    if report.get("schema_version") != 1:
        raise ValueError("Unsupported quality schema")
    matches = [
        m for m in manifests if m["dataset_sha256"] == report.get("fixture_sha256")
    ]
    if len(matches) != 1:
        raise ValueError("Quality report must match exactly one fixture")
    manifest = matches[0]
    for field in ("seed", "profile", "scenario"):
        if report.get(field) != manifest[field]:
            raise ValueError("Quality report provenance mismatch")
    attempts = report.get("attempts")
    summary = report.get("summary")
    if not isinstance(attempts, list) or not isinstance(summary, dict):
        raise ValueError("Invalid quality report")
    candidates = [
        rows
        for rows in rows_by_digest.values()
        if rows[0]["fixture_sha256"] == manifest["dataset_sha256"]
    ]
    if len(candidates) != 1 or len(candidates[0]) != len(attempts):
        raise ValueError("Quality attempts do not match benchmark")
    rows = candidates[0]
    for original, evaluated in zip(rows, attempts):
        for a, b in (
            ("attempt", "attempt"),
            ("warmup", "warmup"),
            ("status", "status"),
            ("elapsed_ns", "elapsed_ns"),
            ("failure_category", "failure_category"),
        ):
            if original.get(a) != evaluated.get(b):
                raise ValueError("Quality attempt provenance mismatch")
    measured = [a for a in attempts if not a["warmup"]]
    matches_count = sum(a.get("matches_expected") is True for a in measured)
    if (
        summary.get("measured_attempts") != len(measured)
        or summary.get("measured_matching_attempts") != matches_count
        or summary.get("all_matched") != (matches_count == len(measured))
    ):
        raise ValueError("Quality summary contradicts attempts")


def review_performance(path: Path, input_digests: set[str]) -> None:
    report = _json(Path(path))
    if (
        report.get("schema_version") != 1
        or report.get("source_schema_version") != 1
        or report.get("measured_stage") != "raw_to_silver"
    ):
        raise ValueError("Unsupported performance analysis schema")
    if set(report.get("input_sha256", [])) != input_digests or len(
        report["input_sha256"]
    ) != len(input_digests):
        raise ValueError(
            "Performance report does not reference supplied benchmark evidence"
        )
    groups = report.get("groups")
    if not isinstance(groups, list) or not groups:
        raise ValueError("Performance report missing groups")
    if {
        digest for group in groups for digest in group.get("input_sha256", [])
    } != input_digests:
        raise ValueError("Performance group provenance mismatch")


def review_gold(path: Path) -> None:
    report = _json(Path(path))
    if (
        report.get("schema_version") != 1
        or report.get("experiment") != "gold_repeatability_rollback_only"
        or report.get("database") != "financial_market_test"
        or report.get("rolled_back") is not True
    ):
        raise ValueError("Gold report does not claim approved rollback-only experiment")
    rows = report.get("scenarios")
    if (
        not isinstance(rows, list)
        or tuple(r.get("scenario") for r in rows if isinstance(r, dict)) != _GOLD
    ):
        raise ValueError("Gold scenario sequence mismatch")
    expectations = (
        (2, 2, 0, 0, 0),
        (2, 0, 0, 2, 0),
        (1, 0, 1, 0, 0),
        (1, 0, 0, 1, 0),
        (1, 0, 0, 0, 1),
    )
    for row, expected in zip(rows, expectations):
        actual = tuple(
            row.get(k)
            for k in ("records_read", "inserted", "updated", "unchanged", "rejected")
        )
        if actual != expected or row.get("matches_expected") is not True:
            raise ValueError("Gold scenario counts mismatch")
        if not all(
            _hash(row.get(k)) for k in ("before_state_sha256", "after_state_sha256")
        ):
            raise ValueError("Invalid Gold state hashes")
        if (
            row["scenario"] in ("replay", "stale_replay", "equal_time_conflict")
            and row["before_state_sha256"] != row["after_state_sha256"]
        ):
            raise ValueError("Gold replay state changed")


def review(
    *,
    pairs: list[tuple[Path, Path]],
    quality: list[Path],
    performance: Path | None,
    gold: Path | None,
) -> dict:
    if not 1 <= len(pairs) <= 20:
        raise ValueError("Provide between 1 and 20 fixture/benchmark pairs")
    manifests = []
    rows_by_digest = {}
    for dataset, benchmark in pairs:
        manifest = review_fixture(dataset)
        digest, rows = review_benchmark(benchmark, manifest)
        if digest in rows_by_digest:
            raise ValueError("Duplicate benchmark evidence")
        manifests.append(manifest)
        rows_by_digest[digest] = rows
    for report in quality:
        review_quality(report, manifests, rows_by_digest)
    if performance is not None:
        review_performance(performance, set(rows_by_digest))
    if gold is not None:
        review_gold(gold)
    return {
        "fixture_benchmark_pairs": len(pairs),
        "quality_reports": len(quality),
        "performance_checked": performance is not None,
        "gold_report_checked": gold is not None,
        "benchmark_sha256": sorted(rows_by_digest),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pair",
        nargs=2,
        action="append",
        required=True,
        metavar=("FIXTURE_DIR", "BENCHMARK_JSONL"),
    )
    parser.add_argument("--quality", type=Path, action="append", default=[])
    parser.add_argument("--performance", type=Path)
    parser.add_argument("--gold", type=Path)
    args = parser.parse_args()
    try:
        result = review(
            pairs=[(Path(a), Path(b)) for a, b in args.pair],
            quality=args.quality,
            performance=args.performance,
            gold=args.gold,
        )
    except (ValueError, OSError, UnicodeError, KeyError, TypeError) as exc:
        parser.error(f"Evidence review failed ({type(exc).__name__}); inspect locally")
    print(
        f"PASS: reviewed {result['fixture_benchmark_pairs']} fixture/benchmark pairs, {result['quality_reports']} quality reports; performance={result['performance_checked']}; Gold={result['gold_report_checked']}"
    )


if __name__ == "__main__":
    main()
