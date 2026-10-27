"""Verify tracking persistence against the isolated test database."""

import os
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from financial_data_platform.orchestration.execution_tracking import (
    build_pipeline_counters,
    finish_pipeline_tracking,
    start_pipeline_tracking,
)
from financial_data_platform.warehouse.db import connect_to_database


if os.getenv("POSTGRES_DB") != "financial_market_test":
    raise RuntimeError("Refusing to use a non-test database")

dag_id = "financial_market_pipeline"
airflow_run_id = f"integration_test__{uuid4()}"
started_at = datetime.now(timezone.utc)
finished_at = started_at + timedelta(seconds=5)

run_id = start_pipeline_tracking(
    dag_id=dag_id,
    airflow_run_id=airflow_run_id,
    started_at=started_at,
)

try:
    # Repeating initialization must preserve the same tracking identity.
    repeated_id = start_pipeline_tracking(
        dag_id=dag_id,
        airflow_run_id=airflow_run_id,
        started_at=started_at,
    )
    assert repeated_id == run_id

    counters = build_pipeline_counters(
        silver_result={
            "status": "success",
            "total_records": 30,
            "valid_count": 30,
            "invalid_count": 0,
        },
        gold_result={
            "status": "success",
            "inserted": 0,
            "updated": 0,
            "unchanged": 30,
            "rejected": 0,
        },
    )

    finish_pipeline_tracking(
        dag_id=dag_id,
        airflow_run_id=airflow_run_id,
        finished_at=finished_at,
        status="success",
        counters=counters,
    )

    connection = connect_to_database()

    try:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    status,
                    records_extracted,
                    records_validated,
                    records_transformed,
                    records_loaded,
                    records_rejected,
                    duration_seconds
                FROM pipeline_run
                WHERE run_id = %s
                """,
                (run_id,),
            )
            row = cursor.fetchone()

        assert row is not None
        assert row[0] == "success"
        assert row[1:6] == (30, 30, 30, 0, 0)
        assert float(row[6]) == 5.0

        print("PASS: Tracking row persisted")
        print("PASS: Stable execution identity")
        print("PASS: Actual processing counters persisted")
        print("PASS: Execution duration persisted")
    finally:
        connection.close()

finally:
    # Clean up only the row created by this verification.
    connection = connect_to_database()
    try:
        with connection.cursor() as cursor:
            cursor.execute(
                "DELETE FROM pipeline_run WHERE run_id = %s",
                (run_id,),
            )
        connection.commit()
    finally:
        connection.close()

print("PASS: Tracking verification complete")
