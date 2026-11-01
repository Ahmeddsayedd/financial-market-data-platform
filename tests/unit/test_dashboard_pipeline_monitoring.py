"""Streamlit monitoring-page behavior without Streamlit installation."""

import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import psycopg

from financial_data_platform.analytics.pipeline_monitoring import PipelineRun
from financial_data_platform.dashboard import app


def st_mock():
    st = MagicMock()
    st.selectbox.side_effect = ["All sources", "All statuses"]
    st.checkbox.return_value = False
    return st


def run(status="success"):
    return PipelineRun(
        uuid4(),
        "market",
        datetime(2026, 10, 9, tzinfo=timezone.utc),
        datetime(2026, 10, 9, 1, tzinfo=timezone.utc),
        status,
        10,
        9,
        9,
        9,
        1,
        Decimal("60.000"),
        "twelve_data",
    )


def test_monitoring_displays_run_history_and_counts():
    st = st_mock()
    with (
        patch.object(app, "list_pipeline_sources", return_value=["twelve_data"]),
        patch.object(app, "list_pipeline_runs", return_value=[run()]) as query,
    ):
        app.render_pipeline_monitoring(st)
    query.assert_called_once_with(
        source=None, status=None, start_date=None, end_date=None, limit=500
    )
    assert st.dataframe.call_count == 1
    assert st.metric.call_count == 9
    assert st.dataframe.call_args.args[0][0]["Rejected"] == 1


def test_monitoring_filters_are_passed_to_database():
    st = st_mock()
    st.selectbox.side_effect = ["twelve_data", "failed"]
    st.checkbox.return_value = True
    st.date_input.side_effect = [date(2026, 10, 1), date(2026, 10, 9)]
    with (
        patch.object(app, "list_pipeline_sources", return_value=["twelve_data"]),
        patch.object(app, "list_pipeline_runs", return_value=[]) as query,
    ):
        app.render_pipeline_monitoring(st)
    query.assert_called_once_with(
        source="twelve_data",
        status="failed",
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 9),
        limit=500,
    )


def test_invalid_date_range_prevents_query():
    st = st_mock()
    st.checkbox.return_value = True
    st.date_input.side_effect = [date(2026, 10, 10), date(2026, 10, 9)]
    with (
        patch.object(app, "list_pipeline_sources", return_value=[]),
        patch.object(app, "list_pipeline_runs") as query,
    ):
        app.render_pipeline_monitoring(st)
    query.assert_not_called()
    st.warning.assert_called_once()


def test_empty_history_displays_info():
    st = st_mock()
    with (
        patch.object(app, "list_pipeline_sources", return_value=[]),
        patch.object(app, "list_pipeline_runs", return_value=[]),
    ):
        app.render_pipeline_monitoring(st)
    st.info.assert_called_once()
    st.dataframe.assert_not_called()


def test_query_limit_warning():
    st = st_mock()
    with (
        patch.object(app, "list_pipeline_sources", return_value=[]),
        patch.object(app, "list_pipeline_runs", return_value=[run()] * 500),
    ):
        app.render_pipeline_monitoring(st)
    assert "500-run" in st.warning.call_args.args[0]


def test_errors_do_not_expose_secrets():
    st = st_mock()
    with patch.object(
        app, "list_pipeline_sources", side_effect=ValueError("password=secret")
    ):
        app.render_pipeline_monitoring(st)
    st.error.assert_called_once_with(app.DATABASE_UNAVAILABLE_MESSAGE)
    assert "secret" not in st.error.call_args.args[0]


def test_run_query_error():
    st = st_mock()
    with (
        patch.object(app, "list_pipeline_sources", return_value=[]),
        patch.object(
            app, "list_pipeline_runs", side_effect=psycopg.OperationalError("failure")
        ),
    ):
        app.render_pipeline_monitoring(st)
    st.error.assert_called_once_with(app.DATABASE_UNAVAILABLE_MESSAGE)


def test_main_navigates_to_monitoring():
    st = st_mock()
    st.sidebar.radio.return_value = "Pipeline monitoring"
    with (
        patch.dict(sys.modules, {"streamlit": st}),
        patch.object(app, "render_pipeline_monitoring") as monitor,
        patch.object(app, "render_overview") as overview,
    ):
        app.main()
    monitor.assert_called_once_with(st)
    overview.assert_not_called()
