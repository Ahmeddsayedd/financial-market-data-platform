"""Validate and summarize M10 Raw-to-Silver JSONL benchmark evidence offline.

Only the benchmark's timed stage is measured. Reports never estimate substage
bottlenecks, and no wall-clock timestamps are added to reproducible artifacts.
"""

import hashlib
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path

# Frozen Issue #85 / #83 schema-v1 contract; no runtime ETL imports.
RESULT_SCHEMA_VERSION = 1
PROFILES = {"small": 100, "medium": 1_000, "large": 10_000}
SCENARIOS = ("clean", "mixed", "invalid_only", "duplicate_date")

ANALYSIS_SCHEMA_VERSION = 1
MAX_INPUTS = 20
MAX_BYTES_PER_INPUT = 2_000_000
MAX_ROWS_PER_INPUT = 100
SHA_CHARS = set("0123456789abcdef")


def _integer(value: object, field: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"Invalid {field}: expected integer >= {minimum}")
    return value


def _number(value: object, field: str, *, positive: bool = False) -> float:
    if type(value) not in (int, float) or not math.isfinite(value):
        raise ValueError(f"Invalid {field}: expected finite number")
    if value < 0 or (positive and value == 0):
        raise ValueError(f"Invalid {field}: expected nonnegative measurement")
    return float(value)


def _sha(value: object, field: str) -> str:
    if not isinstance(value, str) or len(value) != 64 or set(value) - SHA_CHARS:
        raise ValueError(f"Invalid {field}: expected lowercase SHA-256")
    return value


def _metadata(row: dict) -> tuple:
    if (
        row.get("schema_version") != RESULT_SCHEMA_VERSION
        or type(row.get("schema_version")) is not int
    ):
        raise ValueError("Unsupported benchmark result schema")
    profile = row.get("profile")
    scenario = row.get("scenario")
    if (
        not isinstance(profile, str)
        or not isinstance(scenario, str)
        or profile not in PROFILES
        or scenario not in SCENARIOS
    ):
        raise ValueError("Unsupported workload profile or scenario")
    _sha(row.get("fixture_sha256"), "fixture_sha256")
    revision = row.get("git_sha")
    if revision is not None and (
        not isinstance(revision, str)
        or len(revision) not in (40, 64)
        or set(revision) - SHA_CHARS
    ):
        raise ValueError("Invalid git_sha")
    version = row.get("python_version")
    if not isinstance(version, str) or not version or len(version) > 40:
        raise ValueError("Invalid python_version")
    _integer(row.get("seed"), "seed")
    symbols = _integer(row.get("symbol_count"), "symbol_count", minimum=1)
    expected = _integer(
        row.get("expected_unique_observations"),
        "expected_unique_observations",
        minimum=1,
    )
    if expected != PROFILES[profile] or symbols > expected:
        raise ValueError("Workload count does not match supported tier")
    if row.get("experiment_id") != f"raw-silver-{profile}-{scenario}":
        raise ValueError("Invalid experiment_id")
    if row.get("stage") != "raw_to_silver":
        raise ValueError("Unsupported measured stage")
    return (
        profile,
        scenario,
        row["seed"],
        symbols,
        row["fixture_sha256"],
        revision,
        version,
        expected,
    )


def _validate_row(row: object) -> tuple:
    if not isinstance(row, dict):
        raise ValueError("Benchmark rows must be JSON objects")
    required = {
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
        "total_records",
        "valid_count",
        "invalid_count",
        "violation_counts",
        "acceptance_rate",
        "rejection_rate",
        "throughput_records_per_second",
        "failure_category",
    }
    if not required.issubset(row):
        raise ValueError("Missing required benchmark schema fields")
    identity = _metadata(row)
    _integer(row.get("attempt"), "attempt", minimum=1)
    if type(row.get("warmup")) is not bool:
        raise ValueError("warmup must be boolean")
    status = row.get("status")
    if status not in ("success", "failed"):
        raise ValueError("Unknown benchmark status")
    elapsed = row.get("elapsed_ns")
    if elapsed is not None:
        _integer(elapsed, "elapsed_ns", minimum=1)
    metric_fields = (
        "total_records",
        "valid_count",
        "invalid_count",
        "violation_counts",
        "acceptance_rate",
        "rejection_rate",
        "throughput_records_per_second",
    )
    if status == "failed":
        if any(row.get(field) is not None for field in metric_fields):
            raise ValueError("Failed attempts must not contain successful metrics")
        category = row.get("failure_category")
        if not isinstance(category, str) or not category or len(category) > 80:
            raise ValueError("Failed attempt requires bounded failure category")
        return identity
    if row.get("failure_category") is not None or elapsed is None:
        raise ValueError("Successful attempt requires elapsed_ns and no failure")
    total = _integer(row.get("total_records"), "total_records")
    valid = _integer(row.get("valid_count"), "valid_count")
    invalid = _integer(row.get("invalid_count"), "invalid_count")
    if total != valid + invalid or total != identity[-1]:
        raise ValueError("Inconsistent successful observation counts")
    violations = row.get("violation_counts")
    if not isinstance(violations, dict) or any(
        not isinstance(key, str)
        or not key
        or len(key) > 80
        or type(value) is not int
        or value < 0
        for key, value in violations.items()
    ):
        raise ValueError("Invalid violation_counts")
    for field, calculated in (
        ("acceptance_rate", valid / total if total else None),
        ("rejection_rate", invalid / total if total else None),
        ("throughput_records_per_second", total * 1_000_000_000 / elapsed),
    ):
        actual = row.get(field)
        if calculated is None:
            if actual is not None:
                raise ValueError(f"Unexpected {field} for empty batch")
        elif not math.isclose(
            _number(actual, field), calculated, rel_tol=1e-10, abs_tol=1e-12
        ):
            raise ValueError(f"Inconsistent {field}")
    return identity


def load_benchmark_evidence(path: Path) -> tuple[str, tuple, list[dict]]:
    """Read one bounded JSONL file and verify attempts and metadata consistency."""
    source = Path(path).expanduser()
    if source.is_symlink() or not source.is_file() or source.suffix != ".jsonl":
        raise ValueError("Benchmark input must be an existing non-symlink JSONL file")
    size = source.stat().st_size
    if not 0 < size <= MAX_BYTES_PER_INPUT:
        raise ValueError("Benchmark input exceeds size limit or is empty")
    content = source.read_bytes()
    if len(content) > MAX_BYTES_PER_INPUT:
        raise ValueError("Benchmark input exceeds size limit")
    try:
        lines = content.decode("utf-8").splitlines()
    except UnicodeError as exc:
        raise ValueError("Benchmark input is not UTF-8") from exc
    if not 0 < len(lines) <= MAX_ROWS_PER_INPUT:
        raise ValueError("Unsupported number of benchmark attempts")
    rows = []
    identity = None
    seen_measured = False
    for index, line in enumerate(lines, start=1):
        try:
            row = json.loads(
                line, parse_constant=lambda _: (_ for _ in ()).throw(ValueError())
            )
        except (ValueError, TypeError) as exc:
            raise ValueError("Invalid benchmark JSONL row") from exc
        observed = _validate_row(row)
        if identity is None:
            identity = observed
        elif observed != identity:
            raise ValueError("Mixed workload or runtime metadata within one input")
        if row["attempt"] != index:
            raise ValueError("Attempt numbers must be contiguous and one-based")
        if row["warmup"]:
            if seen_measured:
                raise ValueError("Warm-ups must precede measured attempts")
        else:
            seen_measured = True
        rows.append(row)
    if not seen_measured:
        raise ValueError("Benchmark must include a measured attempt")
    return hashlib.sha256(content).hexdigest(), identity, rows


def _summary(values: list[float]) -> dict | None:
    if not values:
        return None
    ordered = sorted(values)
    return {
        "minimum": ordered[0],
        "median": statistics.median(ordered),
        "mean": statistics.fmean(ordered),
        "maximum": ordered[-1],
        "population_stddev": statistics.pstdev(ordered),
        "p95_nearest_rank": ordered[math.ceil(0.95 * len(ordered)) - 1],
    }


def analyze_performance(inputs: list[Path]) -> dict:
    """Derive deterministic descriptive metrics without rerunning ETL."""
    if not 1 <= len(inputs) <= MAX_INPUTS:
        raise ValueError("Provide between 1 and 20 benchmark inputs")
    seen_digests: set[str] = set()
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    manifests: dict[tuple, set[str]] = defaultdict(set)
    for path in inputs:
        digest, identity, rows = load_benchmark_evidence(path)
        if digest in seen_digests:
            raise ValueError("Duplicate input evidence would double-count trials")
        seen_digests.add(digest)
        grouped[identity].extend(rows)
        manifests[identity].add(digest)
    groups = []
    for identity in sorted(grouped, key=lambda key: tuple(str(v) for v in key)):
        profile, scenario, seed, symbols, fixture_sha, revision, version, expected = (
            identity
        )
        rows = grouped[identity]
        measured = [row for row in rows if not row["warmup"]]
        successes = [row for row in measured if row["status"] == "success"]
        failures = [row for row in measured if row["status"] == "failed"]
        seconds = [row["elapsed_ns"] / 1e9 for row in successes]
        throughputs = [row["throughput_records_per_second"] for row in successes]
        groups.append(
            {
                "profile": profile,
                "scenario": scenario,
                "seed": seed,
                "symbol_count": symbols,
                "expected_unique_observations": expected,
                "fixture_sha256": fixture_sha,
                "git_sha": revision,
                "python_version": version,
                "input_sha256": sorted(manifests[identity]),
                "warmup_attempts": sum(row["warmup"] for row in rows),
                "measured_attempts": len(measured),
                "successful_attempts": len(successes),
                "failed_attempts": len(failures),
                "failure_categories": dict(
                    sorted(Counter(row["failure_category"] for row in failures).items())
                ),
                "elapsed_seconds": _summary(seconds),
                "throughput_records_per_second": _summary(throughputs),
                "seconds_per_record": _summary(
                    [elapsed / expected for elapsed in seconds]
                ),
            }
        )
    # Compare only results with the same code, interpreter, scenario, seed and
    # symbol fan-out. Distinct fixture digests in one profile are not comparable.
    by_environment: dict[tuple, list[dict]] = defaultdict(list)
    for group in groups:
        key = (
            group["scenario"],
            group["seed"],
            group["symbol_count"],
            group["git_sha"],
            group["python_version"],
        )
        by_environment[key].append(group)
    comparisons = []
    for candidates in by_environment.values():
        candidates.sort(key=lambda group: group["expected_unique_observations"])
        tier_counts = Counter(group["profile"] for group in candidates)
        # If a profile has multiple fixture identities, choosing one for a
        # comparison would silently cherry-pick. Omit ambiguous tiers.
        candidates = [
            group for group in candidates if tier_counts[group["profile"]] == 1
        ]
        for smaller, larger in zip(candidates, candidates[1:]):
            if smaller["profile"] == larger["profile"]:
                continue
            if not smaller["successful_attempts"] or not larger["successful_attempts"]:
                continue
            old = smaller["elapsed_seconds"]["median"]
            new = larger["elapsed_seconds"]["median"]
            old_rate = smaller["throughput_records_per_second"]["median"]
            new_rate = larger["throughput_records_per_second"]["median"]
            comparisons.append(
                {
                    "scenario": smaller["scenario"],
                    "seed": smaller["seed"],
                    "symbol_count": smaller["symbol_count"],
                    "git_sha": smaller["git_sha"],
                    "python_version": smaller["python_version"],
                    "smaller_fixture_sha256": smaller["fixture_sha256"],
                    "larger_fixture_sha256": larger["fixture_sha256"],
                    "from_profile": smaller["profile"],
                    "to_profile": larger["profile"],
                    "record_ratio": larger["expected_unique_observations"]
                    / smaller["expected_unique_observations"],
                    "median_elapsed_ratio": new / old,
                    "median_throughput_ratio": new_rate / old_rate
                    if old_rate
                    else None,
                }
            )
    comparisons.sort(
        key=lambda row: (
            row["scenario"],
            row["seed"],
            row["symbol_count"],
            str(row["git_sha"]),
            row["python_version"],
            PROFILES[row["from_profile"]],
            PROFILES[row["to_profile"]],
        )
    )
    return {
        "schema_version": ANALYSIS_SCHEMA_VERSION,
        "source_schema_version": RESULT_SCHEMA_VERSION,
        "measured_stage": "raw_to_silver",
        "input_sha256": sorted(seen_digests),
        "metrics_definition": {
            "elapsed_seconds": "elapsed_ns / 1e9; successful measured attempts only",
            "throughput_records_per_second": "parsed observations / timed seconds; successful measured attempts only",
            "seconds_per_record": "elapsed seconds / parsed observations; successful measured attempts only",
            "population_stddev": "population standard deviation (ddof=0)",
            "p95_nearest_rank": "sorted measurement at ceil(0.95 * n), one-based",
            "comparisons": "ratio of group medians, larger / smaller; same scenario, seed, symbol count, code revision and Python version",
        },
        "groups": groups,
        "comparisons": comparisons,
        "limitations": [
            "Only Raw-to-Silver execution is timed; no substage bottlenecks can be identified.",
            "Host hardware, load, filesystem cache and dependency versions are not captured by benchmark JSONL.",
            "Warm-ups and failed attempts are excluded from timing and throughput distributions.",
            "Runtime measurements are host-dependent, not deterministic or production performance claims.",
            "Different fixture hashes and unrecorded host conditions may limit cross-tier comparability.",
        ],
    }


def render_markdown(report: dict) -> str:
    """Render descriptive results; do not infer unmeasured bottlenecks."""
    lines = [
        "# M10 — Offline Raw-to-Silver performance analysis",
        "",
        "Measured stage: `raw_to_silver` only. Evidence is synthetic and offline.",
        "",
        "| Profile | Scenario | Records | Success / measured | Median seconds | Median records/s |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for group in report["groups"]:
        duration = group["elapsed_seconds"]
        throughput = group["throughput_records_per_second"]
        lines.append(
            f"| {group['profile']} | {group['scenario']} | "
            f"{group['expected_unique_observations']} | "
            f"{group['successful_attempts']} / {group['measured_attempts']} | "
            f"{duration['median']:.6f} | {throughput['median']:.3f} |"
            if duration and throughput
            else f"| {group['profile']} | {group['scenario']} | "
            f"{group['expected_unique_observations']} | "
            f"{group['successful_attempts']} / {group['measured_attempts']} | n/a | n/a |"
        )
    lines.extend(["", "## Cross-tier comparisons", ""])
    if report["comparisons"]:
        lines.extend(
            [
                "| Scenario | From → to | Records ratio | Median elapsed ratio | Median throughput ratio |",
                "| --- | --- | ---: | ---: | ---: |",
            ]
        )
        for item in report["comparisons"]:
            rate = item["median_throughput_ratio"]
            lines.append(
                f"| {item['scenario']} | {item['from_profile']} → {item['to_profile']} | "
                f"{item['record_ratio']:.2f}× | "
                f"{item['median_elapsed_ratio']:.3f}× | "
                f"{rate:.3f}× |"
                if rate is not None
                else f"| {item['scenario']} | {item['from_profile']} → {item['to_profile']} | "
                f"{item['record_ratio']:.2f}× | "
                f"{item['median_elapsed_ratio']:.3f}× | n/a |"
            )
    else:
        lines.append("No eligible cross-tier comparisons with successful measurements.")
    lines.extend(["", "## Interpretation and limitations", ""])
    lines.extend(f"- {limitation}" for limitation in report["limitations"])
    lines.extend(
        [
            "",
            "Statistics (minimum, median, mean, maximum, population standard deviation,",
            "nearest-rank p95) and failure-category counts are in the JSON report.",
            "Warm-ups are excluded; failed measured attempts remain counted.",
            "Ratios compare medians, not sums or unobserved end-to-end duration.",
            "",
            "## Evidence provenance",
            "",
        ]
    )
    lines.extend(f"- Input SHA-256: `{digest}`" for digest in report["input_sha256"])
    lines.append("")
    return "\n".join(lines)


def write_performance_analysis(
    *, inputs: list[Path], json_output: Path, markdown_output: Path
) -> dict:
    """Validate all inputs and output destinations before exclusive creation."""
    report = analyze_performance(inputs)
    destinations = (Path(json_output).expanduser(), Path(markdown_output).expanduser())
    if destinations[0].suffix != ".json" or destinations[1].suffix != ".md":
        raise ValueError("Outputs must end in .json and .md respectively")
    resolved = [path.resolve() for path in destinations]
    if resolved[0] == resolved[1]:
        raise ValueError("JSON and Markdown output must be distinct")
    repo = Path(__file__).resolve().parents[3]
    root = (repo / "data" / "experiments").resolve()
    input_paths = {Path(path).expanduser().resolve() for path in inputs}
    for requested, target in zip(destinations, resolved):
        if requested.exists() or requested.is_symlink():
            raise FileExistsError("Output exists; overwrite forbidden")
        if not target.parent.is_dir():
            raise ValueError("Output parent directory must already exist")
        if target in input_paths:
            raise ValueError("Outputs must not replace input evidence")
        if repo == target or repo in target.parents:
            if root not in target.parents:
                raise ValueError("Repository outputs must stay under data/experiments/")
    payloads = (
        json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n",
        render_markdown(report),
    )
    created = []
    try:
        for target, payload in zip(resolved, payloads):
            with target.open("x", encoding="utf-8", newline="\n") as file:
                created.append(target)
                file.write(payload)
    except OSError:
        for target in created:
            target.unlink(missing_ok=True)
        raise
    return report
