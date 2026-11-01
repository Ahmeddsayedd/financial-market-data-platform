"""Streamlit entry point for the read-only Gold analytics dashboard."""

from datetime import date

from financial_data_platform.analytics.pipeline_health import assess_pipeline_health

import psycopg

from financial_data_platform.analytics.pipeline_monitoring import (
    list_pipeline_runs,
    list_pipeline_sources,
    summarize_pipeline_runs,
)

from financial_data_platform.analytics.queries import (
    get_market_history,
    list_assets,
)
from financial_data_platform.dashboard.indicator_charts import (
    has_persisted_indicators,
    make_price_sma_chart,
    make_price_change_chart,
    make_daily_return_chart,
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


def render_indicator_charts(st) -> None:
    """Visualize persisted Gold indicators without calculating or writing values."""
    st.header("Financial indicators")
    st.write("Historical closing prices and indicators persisted in Gold.")

    try:
        assets = list_assets()
    except (psycopg.Error, OSError, ValueError):
        st.error(DATABASE_UNAVAILABLE_MESSAGE)
        return

    if not assets:
        st.info("No assets are available yet. Load validated records into Gold first.")
        return

    sources = sorted({asset.source for asset in assets})
    source = st.selectbox("Indicator data source", sources)
    symbols = sorted({asset.symbol for asset in assets if asset.source == source})
    symbol = st.selectbox("Indicator financial instrument", symbols)
    if not source or not symbol:
        st.info("Select a source and instrument to view financial indicators.")
        return

    start_date: date | None = None
    end_date: date | None = None
    if st.checkbox("Filter indicator dates", value=False):
        start_date = st.date_input("Indicator start date", value=date(2000, 1, 1))
        end_date = st.date_input("Indicator end date", value=date.today())
        if (
            type(start_date) is not date
            or type(end_date) is not date
            or start_date > end_date
        ):
            st.warning("Start date must be on or before end date.")
            return

    try:
        # One read-only query returns closing prices and already-persisted indicators
        # from the same Gold rows, keeping the overlays aligned by observation date.
        observations = get_market_history(
            source, symbol, start_date=start_date, end_date=end_date, limit=5000
        )
    except (psycopg.Error, OSError, ValueError):
        st.error(DATABASE_UNAVAILABLE_MESSAGE)
        return

    if not observations:
        st.info("No observations match this asset and date range.")
        return

    if len(observations) == 5000:
        st.warning(
            "The query reached its 5,000-observation limit. "
            "Only the earliest matching dates are shown; narrow the date range "
            "before interpreting these charts as complete history."
        )

    st.caption(
        f"Showing {observations[0].observation_date} through "
        f"{observations[-1].observation_date}. "
        "Missing indicators are left blank; no values are recalculated."
    )
    if not has_persisted_indicators(observations):
        st.info(
            "No calculated indicators are available for this selection yet. "
            "The closing-price history is still shown."
        )

    st.plotly_chart(
        make_price_sma_chart(observations, symbol), use_container_width=True
    )
    st.plotly_chart(
        make_price_change_chart(observations, symbol), use_container_width=True
    )
    st.plotly_chart(
        make_daily_return_chart(observations, symbol), use_container_width=True
    )


def render_pipeline_monitoring(st) -> None:
    """Show persisted run history and recorded quality counters, read-only."""
    st.header("Pipeline monitoring")
    st.write("Execution history and recorded quality counters from PostgreSQL Gold.")

    try:
        sources = list_pipeline_sources()
    except (psycopg.Error, OSError, ValueError):
        st.error(DATABASE_UNAVAILABLE_MESSAGE)
        return

    selected_source = st.selectbox("Pipeline source", ["All sources", *sources])
    selected_status = st.selectbox(
        "Pipeline status", ("All statuses", "success", "failed", "running")
    )
    source = None if selected_source == "All sources" else selected_source
    status = None if selected_status == "All statuses" else selected_status

    start_date: date | None = None
    end_date: date | None = None
    if st.checkbox("Filter pipeline start dates (UTC)", value=False):
        start_date = st.date_input("Pipeline start date", value=date(2000, 1, 1))
        end_date = st.date_input("Pipeline end date", value=date.today())
        if (
            type(start_date) is not date
            or type(end_date) is not date
            or start_date > end_date
        ):
            st.warning("Start date must be on or before end date.")
            return

    try:
        runs = list_pipeline_runs(
            source=source,
            status=status,
            start_date=start_date,
            end_date=end_date,
            limit=500,
        )
    except (psycopg.Error, OSError, ValueError):
        st.error(DATABASE_UNAVAILABLE_MESSAGE)
        return

    # Health is always calculated from unfiltered run history. Otherwise a
    # "success" filter could conceal recent failed or stale-running executions.
    filtered = any(
        value is not None for value in (source, status, start_date, end_date)
    )
    health_runs = runs
    if filtered:
        try:
            health_runs = list_pipeline_runs(limit=500)
        except (psycopg.Error, OSError, ValueError):
            st.caption("Operational health: unavailable (history query failed).")
            health_runs = None

    if health_runs is not None:
        health = assess_pipeline_health(health_runs)
        st.subheader("Operational health (all sources and statuses)")
        st.caption(
            f"Status: {health.status.upper()} | "
            f"Assessed: {health.assessed_at.isoformat()} | "
            f"Runs examined: {health.examined_runs}"
        )
        for reason in health.reasons:
            st.caption(reason)
        st.caption(
            "Observed run history only; this does not verify Airflow service "
            "readiness or future scheduled runs."
        )

    if not runs:
        st.info("No pipeline runs match the selected filters.")
        return

    if len(runs) == 500:
        st.warning(
            "The 500-run query limit was reached. Only the most recent matching "
            "runs are displayed, and totals refer to this displayed selection."
        )

    summary = summarize_pipeline_runs(runs)
    st.metric("Displayed runs", summary.run_count)
    st.metric("Successful runs", summary.success_count)
    st.metric("Failed runs", summary.failed_count)
    st.metric("Running runs", summary.running_count)
    st.metric("Extracted records", summary.records_extracted)
    st.metric("Validated records", summary.records_validated)
    st.metric("Transformed records", summary.records_transformed)
    st.metric("Loaded records", summary.records_loaded)
    st.metric("Rejected records", summary.records_rejected)
    st.caption(
        "Counters are recorded by the pipeline, not inferred from raw files. "
        "Rejected-record counts do not identify individual quality violations. "
        "Totals describe only the displayed runs."
    )
    st.dataframe(
        [
            {
                "Run ID": str(run.run_id),
                "DAG": run.dag_id or "—",
                "Source": run.source or "—",
                "Status": run.status,
                "Started (UTC)": run.started_at,
                "Finished (UTC)": run.finished_at,
                "Duration (s)": run.duration_seconds,
                "Extracted": run.records_extracted,
                "Validated": run.records_validated,
                "Transformed": run.records_transformed,
                "Loaded": run.records_loaded,
                "Rejected": run.records_rejected,
            }
            for run in runs
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
    page = st.sidebar.radio(
        "Page", ("Overview", "Market charts", "Indicators", "Pipeline monitoring")
    )
    if page == "Overview":
        render_overview(st)
    elif page == "Market charts":
        render_market_charts(st)
    elif page == "Indicators":
        render_indicator_charts(st)
    elif page == "Pipeline monitoring":
        render_pipeline_monitoring(st)


if __name__ == "__main__":
    from pathlib import Path

    from dotenv import load_dotenv

    project_root = Path(__file__).resolve().parents[3]
    load_dotenv(project_root / ".env", override=False)

    main()
