"""Unit tests for the financial-indicators Streamlit page."""

import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import psycopg

from financial_data_platform.analytics.queries import Asset, MarketObservation
from financial_data_platform.dashboard import app


def asset(source="twelve_data", symbol="AAPL"):
    return Asset(1, source, symbol, None, None, "USD", None)


def observation(day=date(2026, 10, 9), *, sma_7=None, price_change=None):
    return MarketObservation(
        day,
        Decimal("100"),
        Decimal("106"),
        Decimal("98"),
        Decimal("102"),
        100,
        datetime(2026, 10, 9, tzinfo=timezone.utc),
        price_change,
        None,
        sma_7,
        None,
    )


def ui():
    st = MagicMock()
    st.selectbox.side_effect = ["twelve_data", "AAPL"]
    st.checkbox.return_value = False
    return st


def test_navigation_renders_indicators():
    st = MagicMock()
    st.sidebar.radio.return_value = "Indicators"
    with (
        patch.dict(sys.modules, {"streamlit": st}),
        patch.object(app, "render_overview") as overview,
        patch.object(app, "render_market_charts") as market,
        patch.object(app, "render_indicator_charts") as indicators,
    ):
        app.main()
    indicators.assert_called_once_with(st)
    overview.assert_not_called()
    market.assert_not_called()


def test_indicators_reuse_read_only_market_query_and_show_three_figures():
    st = ui()
    history = [observation(sma_7=Decimal("101"))]
    with (
        patch.object(app, "list_assets", return_value=[asset()]) as list_query,
        patch.object(app, "get_market_history", return_value=history) as history_query,
        patch.object(app, "make_price_sma_chart", return_value="sma") as sma,
        patch.object(app, "make_price_change_chart", return_value="change") as change,
        patch.object(app, "make_daily_return_chart", return_value="return") as ret,
    ):
        app.render_indicator_charts(st)
    list_query.assert_called_once_with()
    history_query.assert_called_once_with(
        "twelve_data", "AAPL", start_date=None, end_date=None, limit=5000
    )
    sma.assert_called_once_with(history, "AAPL")
    change.assert_called_once_with(history, "AAPL")
    ret.assert_called_once_with(history, "AAPL")
    assert [call.args[0] for call in st.plotly_chart.call_args_list] == [
        "sma",
        "change",
        "return",
    ]


def test_indicators_keep_symbols_separate_by_source():
    st = ui()
    st.selectbox.side_effect = ["secondary", "AAPL"]
    with (
        patch.object(app, "list_assets", return_value=[asset(), asset("secondary")]),
        patch.object(app, "get_market_history", return_value=[]) as query,
    ):
        app.render_indicator_charts(st)
    query.assert_called_once_with(
        "secondary", "AAPL", start_date=None, end_date=None, limit=5000
    )


def test_indicators_apply_inclusive_date_filters():
    st = ui()
    st.checkbox.return_value = True
    st.date_input.side_effect = [date(2026, 10, 1), date(2026, 10, 9)]
    with (
        patch.object(app, "list_assets", return_value=[asset()]),
        patch.object(app, "get_market_history", return_value=[]) as query,
    ):
        app.render_indicator_charts(st)
    query.assert_called_once_with(
        "twelve_data",
        "AAPL",
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 9),
        limit=5000,
    )


def test_indicators_reject_reversed_date_range():
    st = ui()
    st.checkbox.return_value = True
    st.date_input.side_effect = [date(2026, 10, 9), date(2026, 10, 1)]
    with (
        patch.object(app, "list_assets", return_value=[asset()]),
        patch.object(app, "get_market_history") as query,
    ):
        app.render_indicator_charts(st)
    query.assert_not_called()
    st.warning.assert_called_once()


def test_indicators_reject_multi_date_widget_values():
    st = ui()
    st.checkbox.return_value = True
    st.date_input.side_effect = [
        (date(2026, 10, 1), date(2026, 10, 9)),
        date(2026, 10, 9),
    ]
    with (
        patch.object(app, "list_assets", return_value=[asset()]),
        patch.object(app, "get_market_history") as query,
    ):
        app.render_indicator_charts(st)
    query.assert_not_called()
    st.warning.assert_called_once()


def test_indicators_show_empty_asset_message():
    st = ui()
    with patch.object(app, "list_assets", return_value=[]):
        app.render_indicator_charts(st)
    st.info.assert_called_once()
    st.plotly_chart.assert_not_called()


def test_indicators_show_empty_history_message():
    st = ui()
    with (
        patch.object(app, "list_assets", return_value=[asset()]),
        patch.object(app, "get_market_history", return_value=[]),
    ):
        app.render_indicator_charts(st)
    st.info.assert_called_once()
    st.plotly_chart.assert_not_called()


def test_indicators_communicate_all_missing_indicators_but_keep_close_chart():
    st = ui()
    with (
        patch.object(app, "list_assets", return_value=[asset()]),
        patch.object(app, "get_market_history", return_value=[observation()]),
        patch.object(app, "make_price_sma_chart", return_value="sma"),
        patch.object(app, "make_price_change_chart", return_value="change"),
        patch.object(app, "make_daily_return_chart", return_value="return"),
    ):
        app.render_indicator_charts(st)
    st.info.assert_called_once()
    assert st.plotly_chart.call_count == 3


def test_indicators_handle_db_connection_failure_without_leaking_secrets():
    st = ui()
    with patch.object(app, "list_assets", side_effect=ValueError("password=secret")):
        app.render_indicator_charts(st)
    st.error.assert_called_once_with(app.DATABASE_UNAVAILABLE_MESSAGE)
    assert "secret" not in st.error.call_args.args[0]


def test_indicators_handle_query_failure():
    st = ui()
    with (
        patch.object(app, "list_assets", return_value=[asset()]),
        patch.object(
            app, "get_market_history", side_effect=psycopg.OperationalError("db")
        ),
    ):
        app.render_indicator_charts(st)
    st.error.assert_called_once_with(app.DATABASE_UNAVAILABLE_MESSAGE)
    st.plotly_chart.assert_not_called()


def test_indicators_warn_at_5000_row_boundary():
    st = ui()
    history = [observation(sma_7=Decimal("101"))] * 5000
    with (
        patch.object(app, "list_assets", return_value=[asset()]),
        patch.object(app, "get_market_history", return_value=history),
        patch.object(app, "make_price_sma_chart", return_value="sma"),
        patch.object(app, "make_price_change_chart", return_value="change"),
        patch.object(app, "make_daily_return_chart", return_value="return"),
    ):
        app.render_indicator_charts(st)
    assert "5,000" in st.warning.call_args.args[0]
