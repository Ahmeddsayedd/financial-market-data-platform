"""Read-only cross-check of Issue #105/#107/#109 local thesis evidence.

Does not connect to PostgreSQL, access the Twelve Data API, or rewrite evidence.
"""

import argparse
import json
from pathlib import Path

MAX_BYTES = 2_000_000
INDICATORS = (
    "drawdown",
    "log_return",
    "rolling_volatility_20d",
    "rsi_14",
    "sma_20",
    "sma_50",
    "volume_zscore",
)


def load(path: Path) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError("Missing, linked, or oversized evidence input")
    record = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(record, dict) or record.get("schema_version") != 1:
        raise ValueError("Expected schema-version-1 JSON report")
    return record


def review(replay: dict, audited: dict, orchestration: dict, full: dict) -> dict:
    for report in (replay, audited):
        if report.get("mode") != "offline_replay" or report.get("api_requests") != 0:
            raise ValueError("Replay must be offline with zero API requests")
        if report.get("gold_writes") != 0 or report.get("symbol") != "AAPL":
            raise ValueError("Unexpected replay mutation or symbol")
        if report.get("repetitions") != 5 or report.get("warmups") != 1:
            raise ValueError("Unsupported measurement counts")
        measured = [t for t in report["trials"] if not t["warmup"]]
        warmups = [t for t in report["trials"] if t["warmup"]]
        if len(measured) != 5 or len(warmups) != 1:
            raise ValueError("Warm-up and measured trial counts do not match")
        if (
            report["quality"]["valid_count"] != 100
            or report["quality"]["invalid_count"] != 0
        ):
            raise ValueError("Unexpected quality counts")
        if report["records_parsed"] != 100:
            raise ValueError("Unexpected processed record count")
    shared = ("raw_sha256", "earliest_date", "latest_date", "raw_file")
    for field in shared:
        if replay[field] != audited[field]:
            raise ValueError(f"Replay evidence disagrees on {field}")
    gold = audited.get("gold_audit")
    if not isinstance(gold, dict) or gold.get("database") != "financial_market_test":
        raise ValueError("Gold audit database was not isolated")
    if gold.get("row_count") != 100 or gold.get("distinct_dates") != 100:
        raise ValueError("Unexpected audited Gold row counts")
    if any(
        not isinstance(gold["indicator_non_null_counts"].get(k), int)
        for k in INDICATORS
    ):
        raise ValueError("Missing Gold indicator counts")
    for record in (orchestration, full):
        if record.get("database") != "financial_market_test":
            raise ValueError("Orchestration DB was not isolated")
        if record.get("api_requests") != 0 or record.get("database_writes") != 0:
            raise ValueError("Evidence collector must be read-only")
        if record["airflow_tracking"]["status"] != "success":
            raise ValueError("Airflow tracking did not report success")
        if record["gold_snapshot"]["row_count"] != 100:
            raise ValueError("Gold snapshot row count mismatch")
        if (
            record["gold_snapshot"]["indicator_non_null_counts"]
            != gold["indicator_non_null_counts"]
        ):
            raise ValueError("Indicator coverage differs across reports")
    first = orchestration["airflow_tracking"]["counters"]
    latest = full["airflow_tracking"]["counters"]
    if any(
        first[key] != 0
        for key in ("records_extracted", "records_transformed", "records_loaded")
    ):
        raise ValueError("Guarded orchestration run counters changed")
    if any(
        latest[key] != 100
        for key in ("records_extracted", "records_validated", "records_transformed")
    ):
        raise ValueError("Controlled Airflow run did not process 100 records")
    if latest["records_loaded"] != 0 or latest["records_rejected"] != 0:
        raise ValueError("Unexpected controlled replay loading counts")
    return {
        "status": "PASS",
        "symbol": "AAPL",
        "raw_sha256": replay["raw_sha256"],
        "valid_records": 100,
        "replay_median_ms": round(replay["raw_to_silver_seconds"]["median"] * 1000, 3),
        "audited_replay_median_ms": round(
            audited["raw_to_silver_seconds"]["median"] * 1000, 3
        ),
        "gold_audit_query_ms": round(gold["query_seconds"] * 1000, 3),
        "gold_rows": gold["row_count"],
        "indicator_coverage": gold["indicator_non_null_counts"],
        "controlled_run_id": full["airflow_tracking"]["airflow_run_id"],
        "controlled_records_transformed": latest["records_transformed"],
        "limitations": "Read-only report consistency review, not an independent DAG or SQL execution",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("replay", "audit", "guarded", "controlled"):
        parser.add_argument(f"--{name}", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = review(
            *(
                load(getattr(args, name))
                for name in ("replay", "audit", "guarded", "controlled")
            )
        )
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        parser.exit(1, f"FAIL: {exc}\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
