"""PostgreSQL execution tracking for Airflow DAG runs."""

import os
from datetime import datetime
from uuid import UUID, NAMESPACE_URL, uuid5

from financial_data_platform.warehouse.db import connect_to_database


COUNTER_NAMES = (
    "records_extracted",
    "records_validated",
    "records_transformed",
    "records_loaded",
    "records_rejected",
)


def tracking_run_id(*, dag_id: str, airflow_run_id: str) -> UUID:
    """Return a stable UUID for one Airflow DAG run."""
    if not dag_id or not airflow_run_id:
        raise ValueError("DAG ID and Airflow run ID are required")

    return uuid5(
        NAMESPACE_URL,
        f"financial-market-platform:{dag_id}:{airflow_run_id}",
    )


def _require_test_database() -> None:
    """Prevent tracking writes to the main Gold database."""
    if os.getenv("POSTGRES_DB") != "financial_market_test":
        raise ValueError(
            "Execution tracking is restricted to financial_market_test"
        )


def _require_aware_timestamp(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("Execution timestamps must be timezone-aware")


def start_pipeline_tracking(
    *,
    dag_id: str,
    airflow_run_id: str,
    started_at: datetime,
) -> UUID:
    """Create a running record, preserving it on repeated calls."""
    _require_test_database()
    _require_aware_timestamp(started_at)

    run_id = tracking_run_id(
        dag_id=dag_id,
        airflow_run_id=airflow_run_id,
    )

    connection = connect_to_database()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO pipeline_run (
                    run_id,
                    dag_id,
                    started_at,
                    status,
                    source
                )
                VALUES (%s, %s, %s, 'running', 'twelve_data')
                ON CONFLICT (run_id) DO NOTHING;
                """,
                (run_id, dag_id, started_at),
            )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

    return run_id


def finish_pipeline_tracking(
    *,
    dag_id: str,
    airflow_run_id: str,
    finished_at: datetime,
    status: str,
    counters: dict[str, int] | None = None,
) -> UUID:
    """Finalize a running execution without overwriting terminal records."""
    _require_test_database()
    _require_aware_timestamp(finished_at)

    if status not in {"success", "failed"}:
        raise ValueError("Final status must be success or failed")

    counts = {name: None for name in COUNTER_NAMES}

    if counters is not None:
        if set(counters) - set(COUNTER_NAMES):
            raise ValueError("Unknown execution counter")

        for name, value in counters.items():
            if type(value) is not int or value < 0:
                raise ValueError(
                    "Execution counters must be nonnegative integers"
                )
            counts[name] = value

    run_id = tracking_run_id(
        dag_id=dag_id,
        airflow_run_id=airflow_run_id,
    )

    connection = connect_to_database()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE pipeline_run
                SET
                    finished_at = %s,
                    status = %s,
                    duration_seconds = ROUND(
                        EXTRACT(EPOCH FROM (%s - started_at))::numeric,
                        3
                    ),
                    records_extracted = COALESCE(%s, records_extracted),
                    records_validated = COALESCE(%s, records_validated),
                    records_transformed = COALESCE(%s, records_transformed),
                    records_loaded = COALESCE(%s, records_loaded),
                    records_rejected = COALESCE(%s, records_rejected)
                WHERE run_id = %s
                  AND status = 'running'
                  AND started_at <= %s;
                """,
                (
                    finished_at,
                    status,
                    finished_at,
                    counts["records_extracted"],
                    counts["records_validated"],
                    counts["records_transformed"],
                    counts["records_loaded"],
                    counts["records_rejected"],
                    run_id,
                    finished_at,
                ),
            )

            if cursor.rowcount == 0:
                cursor.execute(
                    """
                    SELECT status
                    FROM pipeline_run
                    WHERE run_id = %s;
                    """,
                    (run_id,),
                )

                row = cursor.fetchone()

                if row is None:
                    raise RuntimeError(
                        "Tracking record does not exist"
                    )

                if row[0] != status:
                    raise RuntimeError(
                        "Tracking record is not in the expected state"
                    )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

    return run_id


def build_pipeline_counters(
    *,
    ingestion_result: dict[str, object] | None = None,
    silver_result: dict[str, object] | None = None,
    gold_result: dict[str, object] | None = None,
) -> dict[str, int]:
    """Build tracking counters from actual completed stage results.

    Missing or disabled stages contribute zero.
    """

    counts = {name: 0 for name in COUNTER_NAMES}

    if ingestion_result and ingestion_result.get("status") == "success":
        # Ingestion currently reports files_written, not the number of
        # observations extracted. Do not interpret file count as record count.
        pass

    if silver_result and silver_result.get("status") == "success":
        counts["records_extracted"] = silver_result["total_records"]
        counts["records_validated"] = silver_result["valid_count"]
        counts["records_transformed"] = silver_result["valid_count"]
        counts["records_rejected"] = silver_result["invalid_count"]

    if gold_result and gold_result.get("status") == "success":
        counts["records_loaded"] = (
            gold_result["inserted"] + gold_result["updated"]
        )
        counts["records_rejected"] += gold_result["rejected"]

    for name, value in counts.items():
        if type(value) is not int or value < 0:
            raise ValueError(
                f"{name} must be a nonnegative integer"
            )

    return counts


def update_pipeline_tracking_counters(
    *,
    dag_id: str,
    airflow_run_id: str,
    counters: dict[str, int],
) -> UUID:
    """Replace the latest metrics for a running DAG execution."""
    _require_test_database()

    if set(counters) != set(COUNTER_NAMES):
        raise ValueError("A complete metric snapshot is required")

    for name, value in counters.items():
        if type(value) is not int or value < 0:
            raise ValueError(
                f"{name} must be a nonnegative integer"
            )

    run_id = tracking_run_id(
        dag_id=dag_id,
        airflow_run_id=airflow_run_id,
    )

    connection = connect_to_database()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE pipeline_run
                SET
                    records_extracted = %s,
                    records_validated = %s,
                    records_transformed = %s,
                    records_loaded = %s,
                    records_rejected = %s
                WHERE run_id = %s
                  AND status = 'running';
                """,
                (
                    counters["records_extracted"],
                    counters["records_validated"],
                    counters["records_transformed"],
                    counters["records_loaded"],
                    counters["records_rejected"],
                    run_id,
                ),
            )

            if cursor.rowcount != 1:
                raise RuntimeError(
                    "A running tracking record is required"
                )

        connection.commit()

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()

    return run_id