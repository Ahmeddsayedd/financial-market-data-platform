"""Database-independent tests for the Streamlit application foundation."""

import sys
from unittest.mock import MagicMock, patch

import psycopg

from financial_data_platform.analytics.queries import Asset
from financial_data_platform.dashboard import app


def _streamlit_mock():
    st = MagicMock()
    st.sidebar.radio.return_value = "Overview"
    return st


def _asset(**changes):
    values = {
        "asset_key": 1,
        "source": "twelve_data",
        "symbol": "AAPL",
        "company_name": "Apple Inc.",
        "exchange": "NASDAQ",
        "currency": "USD",
        "sector": "Technology",
    }
    values.update(changes)
    return Asset(**values)


def test_main_configures_page_and_navigation():
    st = _streamlit_mock()
    with (
        patch.dict(sys.modules, {"streamlit": st}),
        patch.object(app, "render_overview") as render_overview,
    ):
        app.main()

    st.set_page_config.assert_called_once_with(
        page_title="Financial Market Data Platform",
        page_icon="📈",
        layout="wide",
    )
    st.sidebar.radio.assert_called_once_with(
        "Page", ("Overview", "Market charts", "Indicators")
    )
    render_overview.assert_called_once_with(st)


def test_overview_reads_assets_and_displays_metadata():
    st = _streamlit_mock()
    with patch.object(app, "list_assets", return_value=[_asset()]) as query:
        app.render_overview(st)

    query.assert_called_once_with()
    st.metric.assert_called_once_with("Available assets", 1)
    rows = st.dataframe.call_args.args[0]
    assert rows == [
        {
            "Source": "twelve_data",
            "Symbol": "AAPL",
            "Company": "Apple Inc.",
            "Exchange": "NASDAQ",
            "Currency": "USD",
            "Sector": "Technology",
        }
    ]
    assert st.dataframe.call_args.kwargs == {
        "use_container_width": True,
        "hide_index": True,
    }
    st.error.assert_not_called()


def test_overview_keeps_same_symbol_from_different_sources():
    st = _streamlit_mock()
    assets = [_asset(), _asset(asset_key=2, source="secondary")]
    with patch.object(app, "list_assets", return_value=assets):
        app.render_overview(st)

    rows = st.dataframe.call_args.args[0]
    assert [(r["Source"], r["Symbol"]) for r in rows] == [
        ("twelve_data", "AAPL"),
        ("secondary", "AAPL"),
    ]


def test_overview_handles_optional_metadata():
    st = _streamlit_mock()
    with patch.object(
        app,
        "list_assets",
        return_value=[
            _asset(company_name=None, exchange=None, currency=None, sector=None)
        ],
    ):
        app.render_overview(st)

    row = st.dataframe.call_args.args[0][0]
    assert row["Company"] == "—"
    assert row["Exchange"] == "—"
    assert row["Currency"] == "—"
    assert row["Sector"] == "—"


def test_overview_handles_empty_warehouse():
    st = _streamlit_mock()
    with patch.object(app, "list_assets", return_value=[]):
        app.render_overview(st)

    st.info.assert_called_once()
    st.metric.assert_not_called()
    st.dataframe.assert_not_called()


def test_overview_handles_missing_db_configuration_without_leaking_details():
    st = _streamlit_mock()
    with patch.object(
        app, "list_assets", side_effect=ValueError("POSTGRES_PASSWORD=secret-value")
    ):
        app.render_overview(st)

    st.error.assert_called_once_with(app.DATABASE_UNAVAILABLE_MESSAGE)
    assert "secret-value" not in st.error.call_args.args[0]
    st.dataframe.assert_not_called()


def test_overview_handles_postgres_connection_failure():
    st = _streamlit_mock()
    with patch.object(
        app, "list_assets", side_effect=psycopg.OperationalError("connection refused")
    ):
        app.render_overview(st)

    st.error.assert_called_once_with(app.DATABASE_UNAVAILABLE_MESSAGE)
    st.dataframe.assert_not_called()


def test_overview_does_not_swallow_unexpected_programming_errors():
    st = _streamlit_mock()
    with patch.object(app, "list_assets", side_effect=RuntimeError("unexpected bug")):
        try:
            app.render_overview(st)
        except RuntimeError as exc:
            assert str(exc) == "unexpected bug"
        else:
            raise AssertionError("Unexpected programming errors should propagate")
