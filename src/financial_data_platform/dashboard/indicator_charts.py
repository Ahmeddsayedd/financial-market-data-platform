"""Presentation-only figures for already-persisted Gold financial indicators."""

from financial_data_platform.analytics.queries import MarketObservation


def has_persisted_indicators(observations: list[MarketObservation]) -> bool:
    """Return whether any selected Gold row has a persisted indicator value."""
    return any(
        value is not None
        for record in observations
        for value in (
            record.price_change,
            record.daily_return_pct,
            record.sma_7,
            record.sma_30,
            record.log_return,
            record.sma_20,
            record.sma_50,
            record.rolling_volatility_20d,
            record.rsi_14,
            record.drawdown,
            record.volume_zscore,
        )
    )


def _values(observations: list[MarketObservation], field: str) -> list[float | None]:
    """Convert persisted Decimals only for rendering; preserve missing as None."""
    return [
        float(value) if (value := getattr(record, field)) is not None else None
        for record in observations
    ]


def make_price_sma_chart(observations: list[MarketObservation], symbol: str):
    """Plot stored closing prices with nullable SMA 7 and SMA 30 overlays."""
    import plotly.graph_objects as go

    dates = [record.observation_date for record in observations]
    figure = go.Figure(
        data=[
            go.Scatter(
                x=dates,
                y=_values(observations, "close"),
                mode="lines",
                name="Close",
                connectgaps=False,
            ),
            go.Scatter(
                x=dates,
                y=_values(observations, "sma_7"),
                mode="lines",
                name="SMA 7",
                connectgaps=False,
            ),
            go.Scatter(
                x=dates,
                y=_values(observations, "sma_30"),
                mode="lines",
                name="SMA 30",
                connectgaps=False,
            ),
        ]
    )
    figure.update_layout(
        title=f"{symbol} — close and moving averages",
        xaxis_title="Observation date",
        yaxis_title="Price (asset currency)",
    )
    return figure


def make_price_change_chart(observations: list[MarketObservation], symbol: str):
    """Plot persisted daily price changes (not recomputed)."""
    import plotly.graph_objects as go

    figure = go.Figure(
        data=[
            go.Bar(
                x=[record.observation_date for record in observations],
                y=_values(observations, "price_change"),
                name="Daily price change",
            )
        ]
    )
    figure.update_layout(
        title=f"{symbol} — daily price change",
        xaxis_title="Observation date",
        yaxis_title="Price change (asset currency)",
    )
    return figure


def make_daily_return_chart(observations: list[MarketObservation], symbol: str):
    """Plot persisted daily percentage returns (not recomputed)."""
    import plotly.graph_objects as go

    figure = go.Figure(
        data=[
            go.Bar(
                x=[record.observation_date for record in observations],
                y=_values(observations, "daily_return_pct"),
                name="Daily return (%)",
            )
        ]
    )
    figure.update_layout(
        title=f"{symbol} — daily return",
        xaxis_title="Observation date",
        yaxis_title="Return (%)",
    )
    return figure


def make_advanced_indicator_charts(observations: list[MarketObservation], symbol: str):
    """Return read-only plots for persisted advanced indicators."""
    import plotly.graph_objects as go

    dates = [record.observation_date for record in observations]
    specs = (
        ("rsi_14", "RSI 14", "Index (0–100)"),
        ("rolling_volatility_20d", "20-day annualized volatility", "Percent"),
        ("drawdown", "Running-peak drawdown", "Percent"),
        ("volume_zscore", "20-day volume z-score", "Standard deviations"),
        ("log_return", "Daily logarithmic return", "Log return"),
    )
    sma_figure = go.Figure(
        data=[
            go.Scatter(
                x=dates,
                y=_values(observations, field),
                mode="lines",
                name=label,
                connectgaps=False,
            )
            for field, label in (
                ("close", "Close"),
                ("sma_20", "SMA 20"),
                ("sma_50", "SMA 50"),
            )
        ]
    )
    sma_figure.update_layout(
        title=f"{symbol} — close and SMA 20/50",
        xaxis_title="Observation date",
        yaxis_title="Price (asset currency)",
    )
    charts = [sma_figure]
    for field, label, unit in specs:
        figure = go.Figure(
            data=[
                go.Scatter(
                    x=dates,
                    y=_values(observations, field),
                    mode="lines",
                    name=label,
                    connectgaps=False,
                )
            ]
        )
        figure.update_layout(
            title=f"{symbol} — {label}",
            xaxis_title="Observation date",
            yaxis_title=unit,
        )
        charts.append(figure)
    return charts
