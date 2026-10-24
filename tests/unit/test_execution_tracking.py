"""Tests for execution-tracking validation and identity."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from financial_data_platform.orchestration.execution_tracking import (
    build_pipeline_counters,
    finish_pipeline_tracking,
    start_pipeline_tracking,
    tracking_run_id,
    update_pipeline_tracking_counters,
)


def test_same_airflow_run_has_stable_uuid():
    first = tracking_run_id(
        dag_id="financial_market_pipeline",
        airflow_run_id="manual__example",
    )
    second = tracking_run_id(
        dag_id="financial_market_pipeline",
        airflow_run_id="manual__example",
    )

    assert first == second


def test_different_airflow_runs_have_different_uuids():
    first = tracking_run_id(
        dag_id="financial_market_pipeline",
        airflow_run_id="manual__first",
    )
    second = tracking_run_id(
        dag_id="financial_market_pipeline",
        airflow_run_id="manual__second",
    )

    assert first != second


@pytest.mark.parametrize(
    "dag_id, airflow_run_id",
    [
        ("", "manual__example"),
        ("financial_market_pipeline", ""),
    ],
)
def test_rejects_missing_identity(dag_id, airflow_run_id):
    with pytest.raises(ValueError):
        tracking_run_id(
            dag_id=dag_id,
            airflow_run_id=airflow_run_id,
        )


def test_start_rejects_non_test_database(monkeypatch):
    monkeypatch.setenv("POSTGRES_DB", "financial_market")

    with patch(
        "financial_data_platform.orchestration.execution_tracking."
        "connect_to_database"
    ) as connection:
        with pytest.raises(ValueError, match="financial_market_test"):
            start_pipeline_tracking(
                dag_id="financial_market_pipeline",
                airflow_run_id="manual__example",
                started_at=datetime.now(timezone.utc),
            )

    connection.assert_not_called()


def test_start_rejects_naive_timestamp(monkeypatch):
    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    with pytest.raises(ValueError, match="timezone-aware"):
        start_pipeline_tracking(
            dag_id="financial_market_pipeline",
            airflow_run_id="manual__example",
            started_at=datetime(2026, 10, 25),
        )


def test_finish_rejects_invalid_status(monkeypatch):
    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    with pytest.raises(ValueError, match="Final status"):
        finish_pipeline_tracking(
            dag_id="financial_market_pipeline",
            airflow_run_id="manual__example",
            finished_at=datetime.now(timezone.utc),
            status="running",
        )


@pytest.mark.parametrize(
    "bad_counters",
    [
        {"records_loaded": -1},
        {"records_loaded": 2.5},
        {"unknown_count": 10},
    ],
)
def test_finish_rejects_invalid_counters(
    monkeypatch,
    bad_counters,
):
    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    with pytest.raises(ValueError):
        finish_pipeline_tracking(
            dag_id="financial_market_pipeline",
            airflow_run_id="manual__example",
            finished_at=datetime.now(timezone.utc),
            status="success",
            counters=bad_counters,
        )


def test_counters_for_successful_silver_and_gold_processing():
    counts = build_pipeline_counters(
        silver_result={
            "status": "success",
            "total_records": 30,
            "valid_count": 28,
            "invalid_count": 2,
        },
        gold_result={
            "status": "success",
            "inserted": 20,
            "updated": 3,
            "unchanged": 4,
            "rejected": 1,
        },
    )

    assert counts == {
        "records_extracted": 30,
        "records_validated": 28,
        "records_transformed": 28,
        "records_loaded": 23,
        "records_rejected": 3,
    }


def test_repeated_gold_load_does_not_count_unchanged_records():
    counts = build_pipeline_counters(
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

    assert counts["records_loaded"] == 0
    assert counts["records_transformed"] == 30


def test_disabled_stages_have_zero_counts():
    counts = build_pipeline_counters(
        ingestion_result={
            "status": "disabled",
            "files_written": 0,
        },
        silver_result={"status": "disabled"},
        gold_result={"status": "disabled"},
    )

    assert all(value == 0 for value in counts.values())


def test_silver_only_run_does_not_claim_gold_records():
    counts = build_pipeline_counters(
        silver_result={
            "status": "success",
            "total_records": 30,
            "valid_count": 30,
            "invalid_count": 0,
        },
    )

    assert counts["records_extracted"] == 30
    assert counts["records_loaded"] == 0


def test_rejects_negative_stage_counts():
    with pytest.raises(ValueError, match="records_loaded"):
        build_pipeline_counters(
            gold_result={
                "status": "success",
                "inserted": -1,
                "updated": 0,
                "rejected": 0,
            }
        )


def test_counter_snapshot_persists_actual_values(monkeypatch):
    """The database receives the complete metric snapshot."""
    from unittest.mock import MagicMock

    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.rowcount = 1

    counters = {
        "records_extracted": 30,
        "records_validated": 29,
        "records_transformed": 29,
        "records_loaded": 0,
        "records_rejected": 1,
    }

    with patch(
        "financial_data_platform.orchestration.execution_tracking."
        "connect_to_database",
        return_value=connection,
    ):
        update_pipeline_tracking_counters(
            dag_id="financial_market_pipeline",
            airflow_run_id="manual__snapshot_test",
            counters=counters,
        )

    sql, parameters = cursor.execute.call_args.args

    assert "UPDATE pipeline_run" in sql
    assert "status = 'running'" in sql
    assert parameters[:5] == (30, 29, 29, 0, 1)
    connection.commit.assert_called_once()
    connection.close.assert_called_once()


def test_counter_snapshot_requires_existing_running_record(monkeypatch):
    """Missing or completed runs must not accept metric updates."""
    from unittest.mock import MagicMock

    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.rowcount = 0

    counters = {
        "records_extracted": 30,
        "records_validated": 30,
        "records_transformed": 30,
        "records_loaded": 0,
        "records_rejected": 0,
    }

    with patch(
        "financial_data_platform.orchestration.execution_tracking."
        "connect_to_database",
        return_value=connection,
    ):
        with pytest.raises(
            RuntimeError, match="running tracking record"
        ):
            update_pipeline_tracking_counters(
                dag_id="financial_market_pipeline",
                airflow_run_id="manual__missing_test",
                counters=counters,
            )

    connection.rollback.assert_called_once()
    connection.close.assert_called_once()


def test_counter_snapshot_rejects_incomplete_metrics(monkeypatch):
    """Every snapshot must include all five counters."""
    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    with patch(
        "financial_data_platform.orchestration.execution_tracking."
        "connect_to_database"
    ) as connection:
        with pytest.raises(ValueError, match="complete metric snapshot"):
            update_pipeline_tracking_counters(
                dag_id="financial_market_pipeline",
                airflow_run_id="manual__incomplete_test",
                counters={"records_loaded": 5},
            )

    connection.assert_not_called()


def test_finalization_without_counters_preserves_existing_metrics(
    monkeypatch,
):
    """The DAG callback must not reset previously recorded metrics."""
    from unittest.mock import MagicMock

    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.rowcount = 1

    with patch(
        "financial_data_platform.orchestration.execution_tracking."
        "connect_to_database",
        return_value=connection,
    ):
        finish_pipeline_tracking(
            dag_id="financial_market_pipeline",
            airflow_run_id="manual__finalize_test",
            finished_at=datetime.now(timezone.utc),
            status="success",
        )

    sql, parameters = cursor.execute.call_args.args

    assert "COALESCE(%s, records_extracted)" in sql
    assert "COALESCE(%s, records_loaded)" in sql
    assert parameters[3:8] == (None, None, None, None, None)

    connection.commit.assert_called_once()