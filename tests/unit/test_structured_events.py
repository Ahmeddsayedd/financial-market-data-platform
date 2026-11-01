"""Offline tests for safe structured operational logs."""

import json
import logging
from datetime import datetime
from uuid import UUID

import pytest

from financial_data_platform.observability.events import log_event


def _payload(caplog):
    return json.loads(caplog.records[-1].message)


def test_standard_event_fields_and_utc(caplog):
    with caplog.at_level(logging.INFO, logger="financial_data_platform.airflow_task"):
        log_event(
            "airflow_task",
            "ingestion_disabled",
            stage="ingestion",
            status="disabled",
            dag_id="financial_market_pipeline",
            airflow_run_id="manual__2026-11-01T12:00:00+00:00",
        )
    data = _payload(caplog)
    assert data["severity"] == "INFO"
    assert data["subsystem"] == "airflow_task"
    assert data["event"] == "ingestion_disabled"
    assert data["status"] == "disabled"
    assert (
        datetime.fromisoformat(data["timestamp_utc"]).utcoffset().total_seconds() == 0
    )


def test_run_uuid_is_serialized(caplog):
    with caplog.at_level(
        logging.INFO, logger="financial_data_platform.airflow_tracking"
    ):
        log_event(
            "airflow_tracking",
            "pipeline_execution_finalized",
            pipeline_run_id=UUID("00000000-0000-0000-0000-000000000001"),
        )
    assert _payload(caplog)["pipeline_run_id"] == "00000000-0000-0000-0000-000000000001"


@pytest.mark.parametrize(
    "secret",
    [
        "password=super-secret",
        "api_key=abc123",
        "Bearer abc123",
        "postgresql://user:secret@db:5432/database",
        "one\nother",
        "x" * 200,
    ],
)
def test_suspicious_values_redacted(caplog, secret):
    with caplog.at_level(logging.INFO, logger="financial_data_platform.airflow_task"):
        log_event("airflow_task", "task_checked", airflow_run_id=secret)
    assert secret not in caplog.records[-1].message
    assert _payload(caplog)["airflow_run_id"] == "[REDACTED]"


def test_unsupported_fields_rejected(caplog):
    with pytest.raises(ValueError, match="Unsupported diagnostic field"):
        log_event("airflow_task", "task_checked", password="topsecret")
    assert not caplog.records


def test_invalid_event_rejected():
    with pytest.raises(ValueError, match="Invalid diagnostic event"):
        log_event("airflow_task", "token=123")


def test_counter_is_numeric(caplog):
    with caplog.at_level(logging.INFO, logger="financial_data_platform.gold"):
        log_event("gold", "gold_loading_completed", records_read=30)
    assert _payload(caplog)["records_read"] == 30


def test_negative_counter_rejected():
    with pytest.raises(ValueError, match="nonnegative"):
        log_event("gold", "gold_loading_completed", records_read=-1)


def test_error_type_is_safe(caplog):
    with caplog.at_level(
        logging.ERROR, logger="financial_data_platform.airflow_tracking"
    ):
        log_event(
            "airflow_tracking",
            "pipeline_execution_finalized",
            level="ERROR",
            status="failed",
            error_type="OperationalError",
        )
    assert _payload(caplog)["severity"] == "ERROR"
    assert _payload(caplog)["error_type"] == "OperationalError"
