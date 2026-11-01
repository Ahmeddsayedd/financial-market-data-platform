"""Monitoring health summaries use all runs, not the selected status filter."""

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

from financial_data_platform.analytics.pipeline_monitoring import PipelineRun
from financial_data_platform.dashboard import app


def run(status="success"):
    now = datetime(2026, 10, 9, tzinfo=timezone.utc)
    return PipelineRun(
        uuid4(),
        "market",
        now,
        now,
        status,
        10,
        9,
        9,
        9,
        1,
        Decimal("60"),
        "twelve_data",
    )


def mock_streamlit():
    st = MagicMock()
    st.selectbox.side_effect = ["All sources", "All statuses"]
    st.checkbox.return_value = False
    return st


def test_healthy_summary_does_not_change_original_nine_metrics():
    st = mock_streamlit()
    latest = run()
    now = datetime.now(timezone.utc)
    latest = replace(latest, started_at=now, finished_at=now)
    with (
        patch.object(app, "list_pipeline_sources", return_value=[]),
        patch.object(app, "list_pipeline_runs", return_value=[latest]) as query,
    ):
        app.render_pipeline_monitoring(st)
    query.assert_called_once()
    assert st.metric.call_count == 9
    assert any("HEALTHY" in c.args[0] for c in st.caption.call_args_list)


def test_filtered_history_checks_unfiltered_runs_for_failures():
    st = mock_streamlit()
    st.selectbox.side_effect = ["All sources", "success"]
    success = run("success")
    failure = run("failed")
    now = datetime.now(timezone.utc)
    failure = replace(failure, started_at=now, finished_at=now)
    with (
        patch.object(app, "list_pipeline_sources", return_value=[]),
        patch.object(
            app, "list_pipeline_runs", side_effect=[[success], [success, failure]]
        ) as query,
    ):
        app.render_pipeline_monitoring(st)
    assert query.call_count == 2
    assert any("DEGRADED" in c.args[0] for c in st.caption.call_args_list)


def test_empty_filtered_results_do_not_hide_overall_health():
    st = mock_streamlit()
    st.selectbox.side_effect = ["All sources", "failed"]
    with (
        patch.object(app, "list_pipeline_sources", return_value=[]),
        patch.object(app, "list_pipeline_runs", side_effect=[[], [run()]]),
    ):
        app.render_pipeline_monitoring(st)
    st.info.assert_called_once_with("No pipeline runs match the selected filters.")
    assert any("UNKNOWN" in c.args[0] for c in st.caption.call_args_list)


def test_health_query_failure_does_not_show_connection_details():
    st = mock_streamlit()
    st.selectbox.side_effect = ["All sources", "failed"]
    with (
        patch.object(app, "list_pipeline_sources", return_value=[]),
        patch.object(
            app,
            "list_pipeline_runs",
            side_effect=[[], ValueError("password=my-top-secret")],
        ),
    ):
        app.render_pipeline_monitoring(st)
    assert any("unavailable" in c.args[0] for c in st.caption.call_args_list)
    assert all("my-top-secret" not in c.args[0] for c in st.caption.call_args_list)
