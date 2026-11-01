"""Deterministic synthetic Twelve Data-shaped workloads for offline evaluation.

No provider calls, database writes, implicit output directories, or wall-clock
values. Financial-rule-invalid records are distinct from parser failures.
"""

import hashlib
import json
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from financial_data_platform.providers.twelve_data.parser import parse_time_series
from financial_data_platform.validation.market_data import partition_market_data_records

GENERATOR_VERSION = 1
DEFAULT_SEED = 20261001
PROFILES = {"small": 100, "medium": 1_000, "large": 10_000}
SCENARIOS = ("clean", "mixed", "invalid_only", "duplicate_date")
INVALID_RULES = (
    "NEGATIVE_VOLUME",
    "NON_POSITIVE_CLOSE",
    "NON_FINITE_CLOSE",
    "HIGH_BELOW_LOW",
    "OPEN_OUTSIDE_RANGE",
    "CLOSE_OUTSIDE_RANGE",
)
EXTRACTED_AT = "2026-10-02T00:00:00+00:00"
START_DATE = date(2026, 10, 1)


def _canonical_bytes(value: object) -> bytes:
    body = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return (body + "\n").encode("utf-8")


def _check_int(value: int, name: str, *, minimum: int = 0) -> int:
    if type(value) is not int or value < minimum:
        raise ValueError(f"{name} must be an integer >= {minimum}")
    return value


def _make_observation(index: int, rng: random.Random) -> dict[str, str]:
    # Integer cents and bounded spreads avoid float-dependent financial values.
    base = rng.randint(2_000, 80_000)
    low = base - rng.randint(0, 200)
    high = base + rng.randint(0, 200)
    opening = rng.randint(low, high)
    closing = rng.randint(low, high)

    def price(cents: int) -> str:
        return f"{cents // 100}.{cents % 100:02d}"

    return {
        "datetime": (START_DATE - timedelta(days=index)).isoformat(),
        "open": price(opening),
        "high": price(high),
        "low": price(low),
        "close": price(closing),
        "volume": str(rng.randint(0, 5_000_000)),
    }


def _inject_invalid(observation: dict[str, str], rule: str) -> None:
    if rule == "NEGATIVE_VOLUME":
        observation["volume"] = "-1"
    elif rule == "NON_POSITIVE_CLOSE":
        observation["close"] = "0.00"
    elif rule == "NON_FINITE_CLOSE":
        observation["close"] = "NaN"
    elif rule == "HIGH_BELOW_LOW":
        observation["high"] = "1.00"
        observation["low"] = "2.00"
        observation["open"] = "1.50"
        observation["close"] = "1.50"
    elif rule == "OPEN_OUTSIDE_RANGE":
        observation["open"] = "0.01"
    elif rule == "CLOSE_OUTSIDE_RANGE":
        observation["close"] = "999999.00"
    else:
        raise ValueError("Unknown invalid rule")


def build_payloads(
    *,
    profile: str = "small",
    seed: int = DEFAULT_SEED,
    symbol_count: int = 4,
    scenario: str = "clean",
    invalid_count: int = 0,
) -> tuple[dict[str, dict], dict]:
    """Build deterministic provider-shaped payloads and expected outcomes.

    Each payload holds a unique date per symbol. `duplicate_date` is an
    intentional parser-error scenario, *not* a financial rejection.
    """
    if profile not in PROFILES:
        raise ValueError("Unknown workload profile")
    if scenario not in SCENARIOS:
        raise ValueError("Unknown workload scenario")
    _check_int(seed, "seed")
    _check_int(symbol_count, "symbol_count", minimum=1)
    _check_int(invalid_count, "invalid_count")
    total = PROFILES[profile]
    if symbol_count > total:
        raise ValueError("symbol_count may not exceed observation count")
    if scenario == "mixed" and not 0 < invalid_count < total:
        raise ValueError("mixed scenario requires 0 < invalid_count < total")
    if scenario != "mixed" and invalid_count:
        raise ValueError("invalid_count is only configurable for mixed scenario")
    rejected = total if scenario == "invalid_only" else invalid_count
    rng = random.Random(seed)
    payloads: dict[str, dict] = {}
    # Disperse injected errors across symbols and dates without influencing
    # generation of valid base observations.
    invalid_positions = set(random.Random(seed + 1).sample(range(total), rejected))
    assigned = {
        position: INVALID_RULES[index % len(INVALID_RULES)]
        for index, position in enumerate(sorted(invalid_positions))
    }
    cursor = 0
    for symbol_index in range(symbol_count):
        symbol = f"SYN{symbol_index + 1:04d}"
        values = []
        count = total // symbol_count + (symbol_index < total % symbol_count)
        for row_index in range(count):
            value = _make_observation(row_index, rng)
            if cursor in assigned:
                _inject_invalid(value, assigned[cursor])
            values.append(value)
            cursor += 1
        payloads[symbol] = {
            "meta": {"symbol": symbol},
            "values": values,
            "status": "ok",
        }
    # A duplicate date makes the first batch unparseable. It is *additional*
    # to the named unique observation count and never a valid rejection rate.
    if scenario == "duplicate_date":
        first_symbol = next(iter(payloads))
        first_value = payloads[first_symbol]["values"][0]
        payloads[first_symbol]["values"].append(dict(first_value))
    rule_counts: dict[str, int] = {}
    if scenario != "duplicate_date":
        for payload in payloads.values():
            partition = partition_market_data_records(
                parse_time_series(
                    payload, extracted_at=datetime(2026, 10, 2, tzinfo=timezone.utc)
                )
            )
            for invalid_record in partition.invalid_records:
                for violation in invalid_record.violations:
                    rule_counts[violation.code] = rule_counts.get(violation.code, 0) + 1
    manifest_fields = {
        "schema_version": 1,
        "generator_version": GENERATOR_VERSION,
        "seed": seed,
        "profile": profile,
        "scenario": scenario,
        "symbol_count": symbol_count,
        "expected_unique_observations": total,
        "expected_financial_rejections": (
            None if scenario == "duplicate_date" else rejected
        ),
        "expected_financial_valid": (
            None if scenario == "duplicate_date" else total - rejected
        ),
        "expected_violation_occurrences_by_code": dict(sorted(rule_counts.items())),
        "expected_parser_failed_batches": int(scenario == "duplicate_date"),
        "extracted_at": EXTRACTED_AT,
        "synthetic": True,
    }
    return payloads, manifest_fields


def _safe_output_path(destination: Path) -> Path:
    """Never write into repository source or operational Raw/Silver folders."""
    requested = Path(destination).expanduser()
    if requested.exists() or requested.is_symlink():
        raise FileExistsError("Output directory already exists; overwrite forbidden")
    target = requested.resolve()
    repo = Path(__file__).resolve().parents[3]
    safe_repo_output = repo / "data" / "experiments"
    if target == repo or repo in target.parents:
        if target != safe_repo_output and safe_repo_output not in target.parents:
            raise ValueError("Repository outputs must stay under data/experiments/")
    if target == target.parent:
        raise ValueError("Filesystem root is not a valid output directory")
    return target


def write_workload(
    *,
    output_dir: Path,
    profile: str = "small",
    seed: int = DEFAULT_SEED,
    symbol_count: int = 4,
    scenario: str = "clean",
    invalid_count: int = 0,
) -> dict:
    """Write a new dataset directory and provenance manifest, never overwrite."""
    payloads, manifest = build_payloads(
        profile=profile,
        seed=seed,
        symbol_count=symbol_count,
        scenario=scenario,
        invalid_count=invalid_count,
    )
    target = _safe_output_path(output_dir)
    # Compute manifest and payload hashes without machine paths or timestamps.
    hashes = {
        f"raw/{symbol}.json": hashlib.sha256(_canonical_bytes(payload)).hexdigest()
        for symbol, payload in payloads.items()
    }
    manifest = {**manifest, "file_sha256": dict(sorted(hashes.items()))}
    manifest["dataset_sha256"] = hashlib.sha256(
        _canonical_bytes(manifest["file_sha256"])
    ).hexdigest()
    target.mkdir(parents=True, exist_ok=False)
    raw_dir = target / "raw"
    raw_dir.mkdir()
    for symbol, payload in payloads.items():
        (raw_dir / f"{symbol}.json").write_bytes(_canonical_bytes(payload))
    (target / "manifest.json").write_bytes(_canonical_bytes(manifest))
    return manifest
