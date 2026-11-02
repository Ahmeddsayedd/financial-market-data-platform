"""Bounded real-market offline replay experiment with optional read-only Gold audit."""

import hashlib
import json
import os
import platform
import statistics
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from financial_data_platform.experiments.live_market_verification import (
    TEST_DATABASE,
    VerificationError,
    require_isolated_database,
    validate_symbol,
    verify_market_data,
)


def _git_sha() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
            check=True,
            cwd=Path(__file__).resolve().parents[3],
        )
    except (OSError, subprocess.SubprocessError):
        return None
    sha = result.stdout.strip()
    return sha if len(sha) == 40 and all(c in "0123456789abcdef" for c in sha) else None


def _distribution(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        "min": round(ordered[0], 6),
        "median": round(statistics.median(ordered), 6),
        "mean": round(statistics.mean(ordered), 6),
        "max": round(ordered[-1], 6),
        "population_stddev": round(statistics.pstdev(ordered), 6),
    }


def audit_test_gold(*, symbol: str, confirmation: str) -> dict:
    """Run a single parameterized analytical query in a read-only transaction."""
    validate_symbol(symbol)
    if confirmation != TEST_DATABASE or os.getenv("POSTGRES_DB") != TEST_DATABASE:
        raise VerificationError("Gold audit requires financial_market_test.")
    require_isolated_database(confirmation=confirmation)
    from financial_data_platform.warehouse.db import connect_to_database

    connection = connect_to_database()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute("SELECT current_database()")
            if cursor.fetchone()[0] != TEST_DATABASE:
                raise VerificationError("Connected to an unexpected database.")
            start = time.perf_counter()
            cursor.execute(
                """
                SELECT COUNT(*), MIN(d.full_date), MAX(d.full_date),
                       COUNT(DISTINCT d.full_date),
                       COUNT(*) FILTER (WHERE f.drawdown IS NOT NULL),
                       COUNT(*) FILTER (WHERE f.sma_20 IS NOT NULL),
                       COUNT(*) FILTER (WHERE f.sma_50 IS NOT NULL),
                       COUNT(*) FILTER (WHERE f.rsi_14 IS NOT NULL),
                       COUNT(*) FILTER (WHERE f.log_return IS NOT NULL),
                       COUNT(*) FILTER (WHERE f.rolling_volatility_20d IS NOT NULL),
                       COUNT(*) FILTER (WHERE f.volume_zscore IS NOT NULL)
                FROM fact_market_metrics AS f
                JOIN dim_asset AS a ON a.asset_key = f.asset_key
                JOIN dim_date AS d ON d.date_key = f.date_key
                WHERE a.source = %s AND a.symbol = %s
                """,
                ("twelve_data", symbol),
            )
            values = cursor.fetchone()
            elapsed = round(time.perf_counter() - start, 6)
        connection.rollback()
    finally:
        connection.close()
    count, first, last, distinct, *indicator_counts = values
    return {
        "database": TEST_DATABASE,
        "source": "twelve_data",
        "symbol": symbol,
        "row_count": count,
        "distinct_dates": distinct,
        "earliest_date": first.isoformat() if first else None,
        "latest_date": last.isoformat() if last else None,
        "query_seconds": elapsed,
        "indicator_non_null_counts": dict(
            zip(
                (
                    "drawdown",
                    "sma_20",
                    "sma_50",
                    "rsi_14",
                    "log_return",
                    "rolling_volatility_20d",
                    "volume_zscore",
                ),
                indicator_counts,
            )
        ),
    }


def run_replay_experiment(
    *,
    root: Path,
    raw_path: Path,
    symbol: str,
    report_path: Path,
    repetitions: int = 5,
    warmups: int = 1,
    audit_gold: bool = False,
    confirmation: str = "",
) -> dict:
    """Collect measured Raw replays without network or database writes."""
    validate_symbol(symbol)
    if type(repetitions) is not int or not 2 <= repetitions <= 10:
        raise VerificationError("repetitions must be between 2 and 10.")
    if type(warmups) is not int or not 0 <= warmups <= 3:
        raise VerificationError("warmups must be between 0 and 3.")
    root = root.resolve()
    safe = (Path(__file__).resolve().parents[3] / "data/experiments").resolve()
    report = report_path.resolve()
    if not root.is_relative_to(safe) or not report.is_relative_to(safe):
        raise VerificationError("Artifacts must stay below data/experiments.")
    if report.suffix != ".json" or report.exists() or report.is_symlink():
        raise VerificationError("Report must be a new .json file; never overwrite.")
    if not report.parent.is_dir():
        raise VerificationError("Report parent directory does not exist.")
    raw = raw_path.resolve(strict=True)
    if not raw.is_file() or not raw.is_relative_to((root / "raw").resolve()):
        raise VerificationError("Raw input must stay within experiment/raw.")
    raw_rel = raw.relative_to(root).as_posix()
    raw_hash = hashlib.sha256(raw.read_bytes()).hexdigest()
    if audit_gold and (
        confirmation != TEST_DATABASE or os.getenv("POSTGRES_DB") != TEST_DATABASE
    ):
        raise VerificationError("Explicit test database configuration is required.")

    trials = []
    baseline = None
    for n in range(warmups + repetitions):
        summary = verify_market_data(
            experiment_root=root,
            symbol=symbol,
            replay_raw=raw,
            write_gold=False,
        )
        if (
            summary["api_requests"] != 0
            or summary["gold_write_enabled"]
            or summary["raw_sha256"] != raw_hash
            or summary["raw_file"] != raw_rel
        ):
            raise VerificationError("Raw provenance or replay safety mismatch.")
        identity = (
            summary["records_parsed"],
            summary["earliest_date"],
            summary["latest_date"],
            summary["quality"],
            summary["silver_files"],
        )
        if baseline is None:
            baseline = identity
        elif baseline != identity:
            raise VerificationError("Inconsistent quality results across repetitions.")
        trials.append(
            {
                "attempt": n + 1,
                "warmup": n < warmups,
                "fetch_or_replay_seconds": summary["fetch_or_replay_seconds"],
                "raw_to_silver_seconds": summary["raw_to_silver_seconds"],
            }
        )

    measured = [t for t in trials if not t["warmup"]]
    result = {
        "schema_version": 1,
        "experiment": "issue104_real_data_replay",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": _git_sha(),
        "python_version": platform.python_version(),
        "platform": platform.system(),
        "symbol": symbol,
        "provider": "twelve_data",
        "mode": "offline_replay",
        "api_requests": 0,
        "gold_writes": 0,
        "raw_file": raw_rel,
        "raw_sha256": raw_hash,
        "records_parsed": baseline[0],
        "earliest_date": baseline[1],
        "latest_date": baseline[2],
        "quality": baseline[3],
        "silver_files": baseline[4],
        "warmups": warmups,
        "repetitions": repetitions,
        "trials": trials,
        "fetch_or_replay_seconds": _distribution(
            [t["fetch_or_replay_seconds"] for t in measured]
        ),
        "raw_to_silver_seconds": _distribution(
            [t["raw_to_silver_seconds"] for t in measured]
        ),
        "gold_audit": (
            audit_test_gold(symbol=symbol, confirmation=confirmation)
            if audit_gold
            else None
        ),
        "limitations": [
            "Offline real-provider-data replay; does not measure live API latency.",
            "Gold audit reads existing test data; it does not time Gold loading.",
            "Does not execute Airflow tasks or establish production throughput.",
        ],
    }
    report.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return result
