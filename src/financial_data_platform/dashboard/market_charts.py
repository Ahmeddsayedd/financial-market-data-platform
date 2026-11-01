"""Presentation-only OHLCV charts and summaries for Gold market observations."""

from dataclasses import dataclass
from decimal import Decimal

from financial_data_platform.analytics.queries import MarketObservation


@dataclass(frozen=True)
class MarketSummary:
    observation_count: int
    latest_close: Decimal
    price_change: Decimal
    price_change_pct: Decimal


def summarize_market(observations: list[MarketObservation]) -> MarketSummary | None:
    """Summarize the selected chronological observations, without recalculating Gold indicators."""
    if not observations:
        return None
    first_close = observations[0].close
    latest_close = observations[-1].close
    change = latest_close - first_close
    return MarketSummary(
        observation_count=len(observations),
        latest_close=latest_close,
        price_change=change,
        price_change_pct=(change / first_close) * Decimal("100"),
    )


def make_candlestick_chart(observations: list[MarketObservation], symbol: str):
    """Create an interactive candlestick figure using already persisted Gold OHLC values."""
    import plotly.graph_objects as go

    figure = go.Figure(
        data=[
            go.Candlestick(
                x=[record.observation_date for record in observations],
                open=[float(record.open) for record in observations],
                high=[float(record.high) for record in observations],
                low=[float(record.low) for record in observations],
                close=[float(record.close) for record in observations],
                name=symbol,
            )
        ]
    )
    figure.update_layout(
        title=f"{symbol} — daily OHLC",
        xaxis_title="Observation date",
        yaxis_title="Price",
        xaxis_rangeslider_visible=False,
    )
    return figure


def make_volume_chart(observations: list[MarketObservation], symbol: str):
    """Create a volume chart from the same selected Gold rows."""
    import plotly.graph_objects as go

    figure = go.Figure(
        data=[
            go.Bar(
                x=[record.observation_date for record in observations],
                y=[record.volume for record in observations],
                name=f"{symbol} volume",
            )
        ]
    )
    figure.update_layout(
        title=f"{symbol} — daily trading volume",
        xaxis_title="Observation date",
        yaxis_title="Volume",
    )
    return figure
