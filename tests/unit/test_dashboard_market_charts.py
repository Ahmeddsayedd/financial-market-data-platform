"""Database-independent behavior tests for the market-charts Streamlit view."""

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import psycopg

from financial_data_platform.analytics.queries import Asset, MarketObservation
from financial_data_platform.dashboard import app
from financial_data_platform.dashboard.market_charts import summarize_market


def asset(source="twelve_data", symbol="AAPL"):
    return Asset(1, source, symbol, None, None, "USD", None)


def observation(day, close="102", volume=100):
    return MarketObservation(
        day,
        Decimal("100"),
        Decimal("106"),
        Decimal("98"),
        Decimal(close),
        volume,
        datetime(2026, 10, 9, tzinfo=timezone.utc),
        None,
        None,
        None,
        None,
    )


def streamlit_mock():
    st = MagicMock()
    st.selectbox.side_effect = ["twelve_data", "AAPL"]
    st.checkbox.return_value = False
    return st


def test_market_charts_selects_asset_and_draws_both_charts():
    st = streamlit_mock()
    history = [observation(date(2026, 10, 8), "100"), observation(date(2026, 10, 9))]
    with (
        patch.object(app, "list_assets", return_value=[asset()]) as list_query,
        patch.object(app, "get_market_history", return_value=history) as history_query,
        patch.object(app, "make_candlestick_chart", return_value="candles") as candle,
        patch.object(app, "make_volume_chart", return_value="volume") as volume,
    ):
        app.render_market_charts(st)

    list_query.assert_called_once_with()
    history_query.assert_called_once_with(
        "twelve_data", "AAPL", start_date=None, end_date=None, limit=5000
    )
    candle.assert_called_once_with(history, "AAPL")
    volume.assert_called_once_with(history, "AAPL")
    assert st.plotly_chart.call_count == 2
    assert st.plotly_chart.call_args_list[0].args == ("candles",)
    assert st.plotly_chart.call_args_list[1].args == ("volume",)
    assert st.metric.call_count == 3


def test_market_charts_disambiguates_identical_symbols_by_source():
    st = streamlit_mock()
    st.selectbox.side_effect = ["second_source", "AAPL"]
    with (
        patch.object(
            app, "list_assets", return_value=[asset(), asset("second_source")]
        ),
        patch.object(app, "get_market_history", return_value=[]) as query,
    ):
        app.render_market_charts(st)
    assert st.selectbox.call_args_list[0].args == (
        "Data source",
        ["second_source", "twelve_data"],
    )
    query.assert_called_once_with(
        "second_source", "AAPL", start_date=None, end_date=None, limit=5000
    )


def test_market_charts_applies_inclusive_date_filters():
    st = streamlit_mock()
    st.checkbox.return_value = True
    st.date_input.side_effect = [date(2026, 10, 1), date(2026, 10, 9)]
    with (
        patch.object(app, "list_assets", return_value=[asset()]),
        patch.object(app, "get_market_history", return_value=[]) as query,
    ):
        app.render_market_charts(st)
    query.assert_called_once_with(
        "twelve_data",
        "AAPL",
        start_date=date(2026, 10, 1),
        end_date=date(2026, 10, 9),
        limit=5000,
    )


def test_market_charts_rejects_reversed_date_range_before_query():
    st = streamlit_mock()
    st.checkbox.return_value = True
    st.date_input.side_effect = [date(2026, 10, 9), date(2026, 10, 1)]
    with (
        patch.object(app, "list_assets", return_value=[asset()]),
        patch.object(app, "get_market_history") as query,
    ):
        app.render_market_charts(st)
    query.assert_not_called()
    st.warning.assert_called_once()


def test_market_charts_handles_no_assets():
    st = streamlit_mock()
    with patch.object(app, "list_assets", return_value=[]):
        app.render_market_charts(st)
    st.info.assert_called_once()
    st.selectbox.assert_not_called()
    st.plotly_chart.assert_not_called()


def test_market_charts_handles_no_observations():
    st = streamlit_mock()
    with (
        patch.object(app, "list_assets", return_value=[asset()]),
        patch.object(app, "get_market_history", return_value=[]),
    ):
        app.render_market_charts(st)
    st.info.assert_called_once()
    st.plotly_chart.assert_not_called()


def test_market_charts_handles_database_error_without_leaking_password():
    st = streamlit_mock()
    with patch.object(app, "list_assets", side_effect=ValueError("password=private")):
        app.render_market_charts(st)
    st.error.assert_called_once_with(app.DATABASE_UNAVAILABLE_MESSAGE)
    assert "private" not in st.error.call_args.args[0]


def test_market_charts_handles_history_database_failure():
    st = streamlit_mock()
    with (
        patch.object(app, "list_assets", return_value=[asset()]),
        patch.object(
            app, "get_market_history", side_effect=psycopg.OperationalError("failed")
        ),
    ):
        app.render_market_charts(st)
    st.error.assert_called_once_with(app.DATABASE_UNAVAILABLE_MESSAGE)
    st.plotly_chart.assert_not_called()


def test_market_charts_warns_at_query_limit():
    st = streamlit_mock()
    history = [observation(date(2026, 10, 9))] * 5000
    with (
        patch.object(app, "list_assets", return_value=[asset()]),
        patch.object(app, "get_market_history", return_value=history),
        patch.object(app, "make_candlestick_chart", return_value=MagicMock()),
        patch.object(app, "make_volume_chart", return_value=MagicMock()),
    ):
        app.render_market_charts(st)
    assert "5,000" in st.warning.call_args.args[0]


def test_market_summary_preserves_decimal_accuracy():
    rows = [
        observation(date(2026, 10, 8), "100.01"),
        observation(date(2026, 10, 9), "101.02"),
    ]
    summary = summarize_market(rows)
    assert summary.observation_count == 2
    assert summary.latest_close == Decimal("101.02")
    assert summary.price_change == Decimal("1.01")
    assert summary.price_change_pct == Decimal("1.01") / Decimal("100.01") * 100


def test_market_summary_empty_history():
    assert summarize_market([]) is None


def test_main_navigates_to_market_charts():
    import sys

    st = MagicMock()
    st.sidebar.radio.return_value = "Market charts"
    with (
        patch.dict(sys.modules, {"streamlit": st}),
        patch.object(app, "render_overview") as overview,
        patch.object(app, "render_market_charts") as market,
    ):
        app.main()
    market.assert_called_once_with(st)
    overview.assert_not_called()
