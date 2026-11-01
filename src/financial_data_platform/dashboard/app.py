"""Streamlit entry point for the read-only Gold analytics dashboard."""

from datetime import date

import psycopg

from financial_data_platform.analytics.queries import (
    get_market_history,
    list_assets,
)
from financial_data_platform.dashboard.market_charts import (
    make_candlestick_chart,
    make_volume_chart,
    summarize_market,
)


DATABASE_UNAVAILABLE_MESSAGE = (
    "The Gold warehouse is unavailable. Check that PostgreSQL is running "
    "and the database connection settings are configured."
)


def render_overview(st) -> None:
    """Show the available assets without modifying warehouse data."""
    st.header("Gold warehouse overview")
    st.write("Available financial instruments in the Gold warehouse.")

    try:
        assets = list_assets()
    except (psycopg.Error, OSError, ValueError):
        # Never display exception details: connection errors can expose settings.
        st.error(DATABASE_UNAVAILABLE_MESSAGE)
        return

    if not assets:
        st.info(
            "No assets are available yet. Once the data pipeline loads Gold "
            "market records, instruments will appear here."
        )
        return

    st.metric("Available assets", len(assets))
    st.dataframe(
        [
            {
                "Source": asset.source,
                "Symbol": asset.symbol,
                "Company": asset.company_name or "—",
                "Exchange": asset.exchange or "—",
                "Currency": asset.currency or "—",
                "Sector": asset.sector or "—",
            }
            for asset in assets
        ],
        use_container_width=True,
        hide_index=True,
    )


def render_market_charts(st) -> None:
    """Render selected OHLCV observations without changing Gold warehouse data."""
    st.header("Market charts")
    st.write("Daily OHLC prices and trading volume from the Gold warehouse.")

    try:
        assets = list_assets()
    except (psycopg.Error, OSError, ValueError):
        st.error(DATABASE_UNAVAILABLE_MESSAGE)
        return

    if not assets:
        st.info("No assets are available yet. Load validated records into Gold first.")
        return

    sources = sorted({asset.source for asset in assets})
    source = st.selectbox("Data source", sources)
    symbols = sorted({asset.symbol for asset in assets if asset.source == source})
    symbol = st.selectbox("Financial instrument", symbols)
    if not source or not symbol:
        st.info("Select a source and financial instrument to view its market history.")
        return

    start_date: date | None = None
    end_date: date | None = None
    if st.checkbox("Filter observation dates", value=False):
        start_date = st.date_input("Start date", value=date(2000, 1, 1))
        end_date = st.date_input("End date", value=date.today())
        if (
            not isinstance(start_date, date)
            or not isinstance(end_date, date)
            or start_date > end_date
        ):
            st.warning("Start date must be on or before end date.")
            return

    try:
        observations = get_market_history(
            source, symbol, start_date=start_date, end_date=end_date, limit=5000
        )
    except (psycopg.Error, OSError, ValueError):
        st.error(DATABASE_UNAVAILABLE_MESSAGE)
        return

    if not observations:
        st.info("No market observations match this asset and date range.")
        return

    if len(observations) == 5000:
        st.warning(
            "The query reached its 5,000-observation limit. "
            "Only the earliest matching dates are shown; narrow the date range "
            "before interpreting these charts as complete history."
        )

    summary = summarize_market(observations)
    st.metric("Observations", summary.observation_count)
    st.metric("Latest close in selection", f"{summary.latest_close:,.2f}")
    st.metric(
        "Selected-period price change",
        f"{summary.price_change:+,.2f}",
        delta=f"{summary.price_change_pct:+.2f}%",
    )
    st.caption(
        f"Showing {observations[0].observation_date} through "
        f"{observations[-1].observation_date}. "
        "Charts convert Decimal values to floating point for visualization only."
    )
    st.plotly_chart(
        make_candlestick_chart(observations, symbol), use_container_width=True
    )
    st.plotly_chart(make_volume_chart(observations, symbol), use_container_width=True)


def main() -> None:
    """Configure and render the initial Streamlit dashboard page."""
    # Import the UI only when launched: existing CI installs [dev], not [dashboard].
    import streamlit as st

    st.set_page_config(
        page_title="Financial Market Data Platform",
        page_icon="📈",
        layout="wide",
    )
    st.title("Financial Market Data Platform")
    st.caption("Read-only analytics from the PostgreSQL Gold warehouse")

    st.sidebar.title("Navigation")
    page = st.sidebar.radio("Page", ("Overview", "Market charts"))
    if page == "Overview":
        render_overview(st)
    elif page == "Market charts":
        render_market_charts(st)


if __name__ == "__main__":
    from pathlib import Path

    from dotenv import load_dotenv

    project_root = Path(__file__).resolve().parents[3]
    load_dotenv(project_root / ".env", override=False)

    main()
