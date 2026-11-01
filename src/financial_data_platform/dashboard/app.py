"""Streamlit entry point for the read-only Gold analytics dashboard."""

import psycopg

from financial_data_platform.analytics.queries import list_assets


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
    page = st.sidebar.radio("Page", ("Overview",))
    if page == "Overview":
        render_overview(st)


if __name__ == "__main__":
    main()
