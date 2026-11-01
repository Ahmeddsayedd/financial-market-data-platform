"""Plotly figure contract tests using a lightweight fake (no optional UI dependency)."""

import sys
from datetime import date, datetime, timezone
from decimal import Decimal
from types import ModuleType
from unittest.mock import MagicMock, patch

from financial_data_platform.analytics.queries import MarketObservation
from financial_data_platform.dashboard.market_charts import (
    make_candlestick_chart,
    make_volume_chart,
)


def observation():
    return MarketObservation(
        date(2026, 10, 9),
        Decimal("100.12345678"),
        Decimal("105.12345678"),
        Decimal("98.12345678"),
        Decimal("102.12345678"),
        1234567,
        datetime(2026, 10, 9, tzinfo=timezone.utc),
        None,
        None,
        None,
        None,
    )


def fake_plotly():
    graph_objects = MagicMock()
    plotly = ModuleType("plotly")
    plotly.graph_objects = graph_objects
    with patch.dict(
        sys.modules, {"plotly": plotly, "plotly.graph_objects": graph_objects}
    ):
        yield graph_objects


def test_candlestick_chart_maps_gold_ohlc_values():
    for go in fake_plotly():
        figure = make_candlestick_chart([observation()], "AAPL")
    kwargs = go.Candlestick.call_args.kwargs
    assert kwargs["x"] == [date(2026, 10, 9)]
    assert kwargs["open"] == [100.12345678]
    assert kwargs["high"] == [105.12345678]
    assert kwargs["low"] == [98.12345678]
    assert kwargs["close"] == [102.12345678]
    assert kwargs["name"] == "AAPL"
    figure.update_layout.assert_called_once()
    assert figure.update_layout.call_args.kwargs["xaxis_rangeslider_visible"] is False


def test_volume_chart_maps_gold_volume_values():
    for go in fake_plotly():
        figure = make_volume_chart([observation()], "AAPL")
    assert go.Bar.call_args.kwargs["x"] == [date(2026, 10, 9)]
    assert go.Bar.call_args.kwargs["y"] == [1234567]
    figure.update_layout.assert_called_once()
