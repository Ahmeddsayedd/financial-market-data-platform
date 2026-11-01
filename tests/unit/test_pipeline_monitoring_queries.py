"""Database-independent monitoring-query and summary contract tests."""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from financial_data_platform.analytics import pipeline_monitoring as monitoring


def run_row(**overrides):
    values = dict(
        run_id=uuid4(),
        dag_id="financial_market_pipeline",
        started_at=datetime(2026, 10, 9, 12, tzinfo=timezone.utc),
        finished_at=datetime(2026, 10, 9, 12, 1, tzinfo=timezone.utc),
        status="success",
        records_extracted=20,
        records_validated=18,
        records_transformed=18,
        records_loaded=18,
        records_rejected=2,
        duration_seconds=Decimal("60.000"),
        source="twelve_data",
    )
    values.update(overrides)
    return tuple(values[field] for field in monitoring.PipelineRun.__dataclass_fields__)


def test_list_sources_queries_read_only():
    connection = MagicMock()
    connection.__enter__.return_value = connection
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchall.return_value = [("alpha",), ("twelve_data",)]
    with patch.object(monitoring, "connect_to_database", return_value=connection):
        result = monitoring.list_pipeline_sources()
    assert result == ["alpha", "twelve_data"]
    assert cursor.execute.call_args_list[0].args == ("SET TRANSACTION READ ONLY",)
    assert "DISTINCT source" in cursor.execute.call_args_list[1].args[0]


def test_run_rows_map_to_typed_records():
    row = run_row()
    with patch.object(monitoring, "_read_rows", return_value=[row]) as read:
        result = monitoring.list_pipeline_runs()
    assert result == [monitoring.PipelineRun(*row)]
    sql, params = read.call_args.args
    assert "started_at DESC" in sql
    assert params == (500,)


def test_filters_are_parameterized_and_date_bounds_are_utc():
    with patch.object(monitoring, "_read_rows", return_value=[]) as read:
        monitoring.list_pipeline_runs(
            source="twelve_data",
            status="failed",
            start_date=date(2026, 10, 1),
            end_date=date(2026, 10, 9),
            limit=15,
        )
    sql, params = read.call_args.args
    assert "source = %s" in sql
    assert "status = %s" in sql
    assert sql.count("AT TIME ZONE 'UTC'") == 2
    assert params == ("twelve_data", "failed", date(2026, 10, 1), date(2026, 10, 9), 15)
    assert "twelve_data" not in sql


@pytest.mark.parametrize(
    "kwargs",
    [
        {"source": "  "},
        {"status": "unknown"},
        {"start_date": "2026-01-01"},
        {"end_date": datetime(2026, 10, 9)},
        {"start_date": date(2026, 10, 10), "end_date": date(2026, 10, 9)},
        {"limit": 0},
        {"limit": 501},
        {"limit": True},
    ],
)
def test_rejects_invalid_filters_without_connecting(kwargs):
    with patch.object(monitoring, "_read_rows") as query:
        with pytest.raises(ValueError):
            monitoring.list_pipeline_runs(**kwargs)
    query.assert_not_called()


def test_summary_aggregates_selected_rows_only():
    rows = [
        monitoring.PipelineRun(*run_row()),
        monitoring.PipelineRun(*run_row(status="failed", records_rejected=3)),
        monitoring.PipelineRun(*run_row(status="running", duration_seconds=None)),
    ]
    summary = monitoring.summarize_pipeline_runs(rows)
    assert (
        summary.run_count,
        summary.success_count,
        summary.failed_count,
        summary.running_count,
    ) == (3, 1, 1, 1)
    assert summary.records_extracted == 60
    assert summary.records_rejected == 7


def test_empty_summary_is_zero():
    summary = monitoring.summarize_pipeline_runs([])
    assert summary.run_count == 0
    assert summary.records_loaded == 0
