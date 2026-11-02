"""Read-only, run-specific evidence for local Airflow and Gold demonstration."""

import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5


TEST_DATABASE = "financial_market_test"
DAG_ID = "financial_market_pipeline"
_RUN_ID = re.compile(r"[A-Za-z0-9_.:+-]{1,200}\Z")
_SYMBOL = re.compile(r"[A-Z][A-Z0-9.-]{0,14}\Z")
INDICATORS = (
    "log_return",
    "sma_20",
    "sma_50",
    "rolling_volatility_20d",
    "rsi_14",
    "drawdown",
    "volume_zscore",
)


class EvidenceError(ValueError):
    """Missing evidence or unsafe read configuration."""


def validate_inputs(*, airflow_run_id: str, symbol: str, confirmation: str) -> None:
    if not isinstance(airflow_run_id, str) or not _RUN_ID.fullmatch(airflow_run_id):
        raise EvidenceError("A bounded Airflow run ID is required.")
    if not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol):
        raise EvidenceError("An uppercase ticker symbol is required.")
    if confirmation != TEST_DATABASE or os.getenv("POSTGRES_DB") != TEST_DATABASE:
        raise EvidenceError("Explicit financial_market_test selection is required.")


def _source_commit() -> str | None:
    root = Path(__file__).resolve().parents[3]
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            timeout=3,
            text=True,
            capture_output=True,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    value = completed.stdout.strip()
    return value if re.fullmatch(r"[0-9a-f]{40}", value) else None


def _connect_database():
    from financial_data_platform.warehouse.db import connect_to_database

    return connect_to_database()


def collect_orchestration_evidence(
    *, airflow_run_id: str, symbol: str, confirmation: str
) -> dict:
    """Inspect the exact run and current Gold snapshot; make no writes.

    A tracking row is not independently verified Airflow task-instance evidence.
    Operators must cross-check the run in Airflow's own UI.
    """
    validate_inputs(
        airflow_run_id=airflow_run_id, symbol=symbol, confirmation=confirmation
    )
    # Same deterministic key as execution_tracking.tracking_run_id; keep this
    # module importable in lightweight unit-test jobs without Psycopg.
    identifier = uuid5(
        NAMESPACE_URL, f"financial-market-platform:{DAG_ID}:{airflow_run_id}"
    )
    connection = _connect_database()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute("SELECT current_database()")
            row = cursor.fetchone()
            if row is None or row[0] != TEST_DATABASE:
                raise EvidenceError("Actual PostgreSQL database identity mismatch.")
            cursor.execute(
                """
                SELECT dag_id, status, started_at, finished_at, duration_seconds,
                       records_extracted, records_validated, records_transformed,
                       records_loaded, records_rejected, source
                FROM pipeline_run WHERE run_id = %s
                """,
                (identifier,),
            )
            run = cursor.fetchone()
            if run is None or run[0] != DAG_ID:
                raise EvidenceError("No tracking row for the specified Airflow run.")
            cursor.execute(
                """
                SELECT COUNT(*), COUNT(DISTINCT d.full_date),
                       MIN(d.full_date), MAX(d.full_date),
                       COUNT(*) FILTER (WHERE f.log_return IS NOT NULL),
                       COUNT(*) FILTER (WHERE f.sma_20 IS NOT NULL),
                       COUNT(*) FILTER (WHERE f.sma_50 IS NOT NULL),
                       COUNT(*) FILTER (WHERE f.rolling_volatility_20d IS NOT NULL),
                       COUNT(*) FILTER (WHERE f.rsi_14 IS NOT NULL),
                       COUNT(*) FILTER (WHERE f.drawdown IS NOT NULL),
                       COUNT(*) FILTER (WHERE f.volume_zscore IS NOT NULL)
                FROM fact_market_metrics AS f
                JOIN dim_asset AS a ON a.asset_key = f.asset_key
                JOIN dim_date AS d ON d.date_key = f.date_key
                WHERE a.source = %s AND a.symbol = %s
                """,
                ("twelve_data", symbol),
            )
            gold = cursor.fetchone()
        connection.rollback()
    finally:
        connection.close()

    if gold is None:
        raise EvidenceError("Gold audit did not return a summary.")
    (
        dag_id,
        status,
        started,
        finished,
        duration,
        extracted,
        validated,
        transformed,
        loaded,
        rejected,
        source,
    ) = run
    count, distinct, earliest, latest, *non_null = gold
    counts = {
        "records_extracted": extracted,
        "records_validated": validated,
        "records_transformed": transformed,
        "records_loaded": loaded,
        "records_rejected": rejected,
    }
    if status not in {"running", "success", "failed"}:
        raise EvidenceError("Unexpected tracking status.")
    if any(type(value) is not int or value < 0 for value in counts.values()):
        raise EvidenceError("Invalid recorded pipeline counters.")
    if count < 0 or distinct < 0 or distinct > count:
        raise EvidenceError("Invalid Gold audit row counts.")

    return {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "git_sha": _source_commit(),
        "database": TEST_DATABASE,
        "airflow_tracking": {
            "dag_id": dag_id,
            "airflow_run_id": airflow_run_id,
            "tracking_uuid": str(identifier),
            "status": status,
            "started_at": started.isoformat(),
            "finished_at": finished.isoformat() if finished else None,
            "duration_seconds": float(duration) if duration is not None else None,
            "source": source,
            "counters": counts,
        },
        "gold_snapshot": {
            "source": "twelve_data",
            "symbol": symbol,
            "row_count": count,
            "distinct_dates": distinct,
            "earliest_date": earliest.isoformat() if earliest else None,
            "latest_date": latest.isoformat() if latest else None,
            "indicator_non_null_counts": dict(zip(INDICATORS, non_null)),
        },
        "interpretation": {
            "tracking_terminal_success": status == "success",
            "gold_has_rows": count > 0,
            "warning": (
                "Pipeline tracking and Gold are separate database observations. "
                "This report does not prove which individual Airflow tasks ran, "
                "or that these Gold rows were written by this run. "
                "Confirm task states in the Airflow UI and screenshot the dashboard."
            ),
        },
        "api_requests": 0,
        "database_writes": 0,
    }
