"""Indicator figure contracts using a Plotly fake (no UI extras required)."""

import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from types import ModuleType
from unittest.mock import MagicMock, patch

from financial_data_platform.analytics.queries import MarketObservation
from financial_data_platform.dashboard.indicator_charts import (
    has_persisted_indicators,
    make_price_sma_chart,
    make_price_change_chart,
    make_daily_return_chart,
)


def observation(day, **changes):
    fields = {
        "observation_date": day,
        "open": Decimal("100"),
        "high": Decimal("106"),
        "low": Decimal("98"),
        "close": Decimal("102.12345678"),
        "volume": 100,
        "extracted_at": datetime(2026, 10, 9, tzinfo=timezone.utc),
        "price_change": None,
        "daily_return_pct": None,
        "sma_7": None,
        "sma_30": None,
    }
    fields.update(changes)
    return MarketObservation(**fields)


def fake_plotly():
    graph_objects = MagicMock()
    plotly = ModuleType("plotly")
    plotly.graph_objects = graph_objects
    with patch.dict(
        sys.modules, {"plotly": plotly, "plotly.graph_objects": graph_objects}
    ):
        yield graph_objects


def test_missing_indicators_do_not_count_as_present():
    assert has_persisted_indicators([observation(date(2026, 10, 9))]) is False
    assert has_persisted_indicators([]) is False


def test_any_persisted_indicator_counts_as_present():
    row = observation(date(2026, 10, 9), price_change=Decimal("0"))
    assert has_persisted_indicators([row]) is True


def test_sma_chart_preserves_null_as_none_and_aligns_dates():
    rows = [
        observation(date(2026, 10, 8)),
        observation(
            date(2026, 10, 9), sma_7=Decimal("101.00000000"), sma_30=Decimal("100.5")
        ),
    ]
    for go in fake_plotly():
        fig = make_price_sma_chart(rows, "AAPL")
    calls = go.Scatter.call_args_list
    assert len(calls) == 3
    assert [call.kwargs["name"] for call in calls] == ["Close", "SMA 7", "SMA 30"]
    assert calls[0].kwargs["x"] == [date(2026, 10, 8), date(2026, 10, 9)]
    assert calls[0].kwargs["y"] == [102.12345678, 102.12345678]
    assert calls[1].kwargs["y"] == [None, 101.0]
    assert calls[2].kwargs["y"] == [None, 100.5]
    assert all(call.kwargs["connectgaps"] is False for call in calls)
    fig.update_layout.assert_called_once()


def test_price_change_keeps_null_and_zero_distinct():
    rows = [
        observation(date(2026, 10, 8)),
        observation(date(2026, 10, 9), price_change=Decimal("0")),
    ]
    for go in fake_plotly():
        fig = make_price_change_chart(rows, "AAPL")
    assert go.Bar.call_args.kwargs["y"] == [None, 0.0]
    assert go.Bar.call_args.kwargs["x"] == [date(2026, 10, 8), date(2026, 10, 9)]
    fig.update_layout.assert_called_once()


def test_return_chart_uses_persisted_percentage_not_fraction():
    rows = [
        observation(date(2026, 10, 8)),
        observation(date(2026, 10, 9), daily_return_pct=Decimal("2.50000000")),
    ]
    for go in fake_plotly():
        fig = make_daily_return_chart(rows, "AAPL")
    assert go.Bar.call_args.kwargs["y"] == [None, 2.5]
    assert go.Bar.call_args.kwargs["name"] == "Daily return (%)"
    assert fig.update_layout.call_args.kwargs["yaxis_title"] == "Return (%)"
