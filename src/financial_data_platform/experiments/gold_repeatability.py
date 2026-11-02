"""Opt-in, rollback-only Gold experiment on the isolated PostgreSQL test DB.

Existing loader transaction wrappers are deliberately NOT used: their commit
would persist experiment data. The caller owns one transaction and rolls it back.
"""

import hashlib
import json
import os
import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from financial_data_platform.experiments.metrics import gold_outcome_metrics
from financial_data_platform.experiments.workloads import DEFAULT_SEED, build_payloads
from financial_data_platform.providers.twelve_data.parser import parse_time_series
from financial_data_platform.validation.market_data import partition_market_data_records
from financial_data_platform.warehouse.db import (
    connect_to_database,
    get_database_config,
)
from financial_data_platform.warehouse.gold_loader import load_market_batch
from financial_data_platform.warehouse.gold_market_history import (
    read_gold_market_records,
)

TEST_DB = "financial_market_test"
SOURCE = "m10_experiment"
SCENARIOS = ("initial", "replay", "newer_update", "stale_replay", "equal_time_conflict")


def _canonical(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n"
    ).encode("utf-8")


def _fixture(seed: int, symbol: str):
    if type(seed) is not int or seed < 0:
        raise ValueError("seed must be a nonnegative integer")
    payloads, manifest = build_payloads(profile="small", seed=seed, symbol_count=4)
    first = next(iter(payloads.values()))
    records = parse_time_series(
        first, extracted_at=datetime.fromisoformat(manifest["extracted_at"])
    )
    partition = partition_market_data_records(records[:2])
    if len(partition.valid_records) != 2 or partition.invalid_records:
        raise RuntimeError("Synthetic Gold fixture is not fully valid")
    records = [
        replace(record, symbol=symbol, source=SOURCE)
        for record in partition.valid_records
    ]
    # Hash the original generator payload, not the randomized namespace.
    digest = hashlib.sha256(_canonical(first)).hexdigest()
    return records, digest


def _state(cursor, symbol: str) -> tuple[str, int, list]:
    records = read_gold_market_records(cursor, SOURCE, symbol)
    rows = [
        {
            "date": record.observation_date.isoformat(),
            "open": str(record.open),
            "high": str(record.high),
            "low": str(record.low),
            "close": str(record.close),
            "volume": record.volume,
            "extracted_at": record.extracted_at.astimezone(timezone.utc).isoformat(),
        }
        for record in records
    ]
    return hashlib.sha256(_canonical(rows)).hexdigest(), len(rows), records


def _output_path(path: Path) -> Path:
    requested = Path(path).expanduser()
    if requested.suffix != ".json":
        raise ValueError("Evidence filename must end with .json")
    if requested.exists() or requested.is_symlink():
        raise FileExistsError("Evidence file already exists")
    target = requested.resolve()
    repo = Path(__file__).resolve().parents[3]
    allowed = (repo / "data" / "experiments").resolve()
    if target == repo or repo in target.parents:
        if allowed not in target.parents:
            raise ValueError("Repository evidence must be under data/experiments/")
    if not target.parent.is_dir():
        raise ValueError("Evidence parent directory must already exist")
    return target


def _ensure_test_database(authorized: bool) -> None:
    if authorized is not True:
        raise ValueError("Explicit test database authorization required")
    if os.getenv("POSTGRES_DB") != TEST_DB:
        raise ValueError("POSTGRES_DB must explicitly equal financial_market_test")
    if get_database_config()["dbname"] != TEST_DB:
        raise ValueError("Configured database is not the isolated test database")


def run_gold_repeatability(
    *, output: Path, authorize_test_db: bool = False, seed: int = DEFAULT_SEED
) -> dict:
    """Measure five deterministic Gold scenarios, then ALWAYS rollback.

    No destructive SQL, migration application or persistence is performed.
    Failure before successful rollback never creates a success report.
    """
    _ensure_test_database(authorize_test_db)
    evidence_path = _output_path(output)
    symbol = "M10" + uuid4().hex[:16].upper()
    initial, fixture_hash = _fixture(seed, symbol)
    original = initial[0]
    updated = replace(
        original,
        close=original.close + (original.high - original.close) / 2,
        extracted_at=original.extracted_at + timedelta(minutes=1),
    )
    # Ensure different financial values, even when close == high.
    if updated.close == original.close:
        updated = replace(updated, volume=updated.volume + 1)
    equal_conflict = replace(updated, volume=updated.volume + 1)
    batches = (
        ("initial", initial, (2, 0, 0, 0)),
        ("replay", initial, (0, 0, 2, 0)),
        ("newer_update", [updated], (0, 1, 0, 0)),
        ("stale_replay", [original], (0, 0, 1, 0)),
        ("equal_time_conflict", [equal_conflict], (0, 0, 0, 1)),
    )
    connection = None
    completed = False
    rows = []
    try:
        connection = connect_to_database()
        if connection.autocommit:
            raise ValueError("Gold experiment requires a rollback-capable transaction")
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            if cursor.fetchone()[0] != TEST_DB:
                raise ValueError(
                    "Server-side database identity is not financial_market_test"
                )
            cursor.execute("SET LOCAL lock_timeout = '3s'")
            cursor.execute("SET LOCAL statement_timeout = '15s'")
            cursor.execute(
                "SELECT COUNT(*) FROM dim_asset WHERE source = %s AND symbol = %s",
                (SOURCE, symbol),
            )
            if cursor.fetchone()[0] != 0:
                raise RuntimeError("Experiment namespace already exists")
            empty_digest, empty_count, _ = _state(cursor, symbol)
            if empty_count:
                raise RuntimeError("Experiment Gold state is not empty")
            for name, records, expected in batches:
                before_hash, before_count, _ = _state(cursor, symbol)
                start = time.perf_counter_ns()
                counts = load_market_batch(cursor, records)
                elapsed_ns = time.perf_counter_ns() - start
                if elapsed_ns <= 0:
                    raise RuntimeError("Nonpositive Gold timing")
                outcomes = gold_outcome_metrics(records_read=len(records), **counts)
                actual = (
                    outcomes.inserted,
                    outcomes.updated,
                    outcomes.unchanged,
                    outcomes.rejected,
                )
                if actual != expected:
                    raise RuntimeError("Gold outcome mismatch")
                after_hash, after_count, current = _state(cursor, symbol)
                if after_count != 2:
                    raise RuntimeError("Gold fact cardinality mismatch")
                if name in {"replay", "stale_replay", "equal_time_conflict"}:
                    if before_hash != after_hash:
                        raise RuntimeError("Gold replay changed logical state")
                if name == "newer_update":
                    updated_state = next(
                        (
                            record
                            for record in current
                            if record.observation_date == updated.observation_date
                        ),
                        None,
                    )
                    if (
                        updated_state is None
                        or updated_state.extracted_at != updated.extracted_at
                    ):
                        raise RuntimeError(
                            "Gold update did not persist newer observation"
                        )
                rows.append(
                    {
                        "scenario": name,
                        "records_read": outcomes.records_read,
                        "inserted": outcomes.inserted,
                        "updated": outcomes.updated,
                        "unchanged": outcomes.unchanged,
                        "rejected": outcomes.rejected,
                        "applied": outcomes.applied,
                        "elapsed_ns": elapsed_ns,
                        "before_state_sha256": before_hash,
                        "after_state_sha256": after_hash,
                        "before_count": before_count,
                        "after_count": after_count,
                        "matches_expected": True,
                    }
                )
        # Rollback even on success. All Gold inserts and updates are temporary.
        connection.rollback()
        completed = True
    finally:
        if connection is not None:
            if not completed:
                connection.rollback()
            connection.close()
    # The experiment-owned symbol is not included in report; no identifiers of
    # existing DB data, passwords or raw payloads are serialized.
    report = {
        "schema_version": 1,
        "experiment": "gold_repeatability_rollback_only",
        "database": TEST_DB,
        "seed": seed,
        "synthetic_fixture_sha256": fixture_hash,
        "scenarios": rows,
        "rolled_back": True,
        "pre_experiment_empty_state_sha256": empty_digest,
        "limitations": "Rollback-only, two synthetic observations; no committed Gold persistence claim",
    }
    with evidence_path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(_canonical(report).decode("utf-8"))
    return report
