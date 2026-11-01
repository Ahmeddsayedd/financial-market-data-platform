"""Populated dashboard review against financial_market_test only."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from financial_data_platform.analytics.pipeline_monitoring import (
    list_pipeline_runs,
    summarize_pipeline_runs,
)
from financial_data_platform.analytics.queries import get_market_history, list_assets
from financial_data_platform.dashboard import app
from financial_data_platform.dashboard.demo_data import (
    DEMO_DAYS,
    DEMO_SOURCE,
    _run_id,
    cleanup_demo_data,
    seed_demo_data,
)
from financial_data_platform.dashboard.indicator_charts import has_persisted_indicators
from financial_data_platform.dashboard.market_charts import summarize_market
from financial_data_platform.warehouse.db import get_database_config

pytestmark = pytest.mark.integration


@pytest.fixture
def populated_demo(monkeypatch):
    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")
    assert get_database_config()["dbname"] == "financial_market_test"
    symbol = "DEMO" + uuid4().hex[:12].upper()
    # No cleanup if seeding fails; the transaction rolls back on failure.
    seed_demo_data(symbol)
    try:
        yield symbol
    finally:
        cleanup_demo_data(symbol)


def test_populated_gold_history_and_nullable_indicators(populated_demo):
    symbol = populated_demo
    assert any(a.symbol == symbol for a in list_assets(source=DEMO_SOURCE))
    history = get_market_history(DEMO_SOURCE, symbol)
    assert len(history) == DEMO_DAYS
    assert history == sorted(history, key=lambda record: record.observation_date)
    assert history[0].sma_7 is None
    assert history[5].sma_7 is None
    assert history[6].sma_7 is not None
    assert history[28].sma_30 is None
    assert history[29].sma_30 is not None
    assert history[0].daily_return_pct is None
    assert history[1].daily_return_pct is not None
    assert history[0].volume == 1000
    assert history[-1].volume == 4400
    assert has_persisted_indicators(history)
    summary = summarize_market(history)
    assert summary.observation_count == 35
    assert summary.latest_close == history[-1].close
    assert summary.price_change == history[-1].close - history[0].close
    assert get_market_history(DEMO_SOURCE, symbol, start_date=date(2026, 10, 6)) == []
    filtered = get_market_history(
        DEMO_SOURCE,
        symbol,
        start_date=date(2026, 9, 10),
        end_date=date(2026, 9, 12),
    )
    assert len(filtered) == 3


def test_populated_monitoring_statuses_and_counters(populated_demo):
    expected_ids = {
        _run_id(populated_demo, status) for status in ("success", "failed", "running")
    }
    runs = [
        run
        for run in list_pipeline_runs(source=DEMO_SOURCE)
        if run.run_id in expected_ids
    ]
    summary = summarize_pipeline_runs(runs)
    assert summary.run_count == 3
    assert (
        summary.success_count,
        summary.failed_count,
        summary.running_count,
    ) == (1, 1, 1)
    assert summary.records_rejected == 6
    assert summary.records_loaded == 90
    assert any(r.duration_seconds == Decimal("45.000") for r in runs)
    assert any(r.duration_seconds is None for r in runs)
    failed = list_pipeline_runs(
        source=DEMO_SOURCE,
        status="failed",
        start_date=date(2026, 10, 11),
        end_date=date(2026, 10, 11),
    )
    assert any(run.run_id == _run_id(populated_demo, "failed") for run in failed)


def test_all_four_pages_render_populated_data_without_writing(populated_demo):
    st = MagicMock()
    st.checkbox.return_value = False
    with patch.object(app, "list_assets", wraps=list_assets):
        app.render_overview(st)
    assert st.dataframe.called
    st.reset_mock()

    st.selectbox.side_effect = [DEMO_SOURCE, populated_demo]
    with (
        patch.object(app, "make_candlestick_chart", return_value="candlestick"),
        patch.object(app, "make_volume_chart", return_value="volume"),
    ):
        app.render_market_charts(st)
    assert st.plotly_chart.call_count == 2
    assert st.metric.call_count == 3
    st.reset_mock()

    st.selectbox.side_effect = [DEMO_SOURCE, populated_demo]
    with (
        patch.object(app, "make_price_sma_chart", return_value="sma"),
        patch.object(app, "make_price_change_chart", return_value="change"),
        patch.object(app, "make_daily_return_chart", return_value="return"),
    ):
        app.render_indicator_charts(st)
    assert st.plotly_chart.call_count == 3
    st.reset_mock()

    st.selectbox.side_effect = [DEMO_SOURCE, "All statuses"]
    app.render_pipeline_monitoring(st)
    assert st.dataframe.called
    assert st.metric.call_count == 9
