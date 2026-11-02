"""Numerical and temporal contracts for issue #101 advanced Gold metrics."""

from dataclasses import replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from financial_data_platform.analytics.indicators import (
    calculate_drawdown,
    calculate_log_return,
    calculate_market_indicators,
    calculate_rolling_volatility,
    calculate_rsi,
    calculate_volume_zscore,
)
from financial_data_platform.models.market_data import MarketDataRecord
from financial_data_platform.warehouse.gold_indicator_mapping import (
    to_gold_indicator_values,
)

D = Decimal


def record(
    index: int,
    *,
    symbol: str = "AAPL",
    source: str = "twelve_data",
    close: str | None = None,
    volume: int = 1000,
) -> MarketDataRecord:
    price = D(close) if close is not None else D(100 + index)
    return MarketDataRecord(
        symbol=symbol,
        source=source,
        observation_date=date(2026, 1, 1) + timedelta(days=index),
        open=price,
        high=price + D(1),
        low=price - D(1),
        close=price,
        volume=volume,
        extracted_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
    )


def test_log_return_zero_and_positive_reference():
    assert calculate_log_return(D(100), D(100)) == D(0)
    result = calculate_log_return(D(110), D(100))
    assert abs(result - D("0.09531017980432486")) < D("1e-16")
    assert calculate_log_return(D(0), D(100)) is None
    assert calculate_log_return(D(100), D(-1)) is None


def test_sample_annualized_volatility_and_warmup():
    values = [D("0.01"), D("-0.01")]
    assert calculate_rolling_volatility(values[:1], 2) is None
    expected = D("0.02") / D(2).sqrt() * D(252).sqrt() * 100
    assert abs(calculate_rolling_volatility(values, 2) - expected) < D("1e-24")
    assert calculate_rolling_volatility([D(0)] * 20) == 0
    with pytest.raises(ValueError, match="Volatility"):
        calculate_rolling_volatility(values, 1)


def test_drawdown_high_water_mark_and_invalid_peak():
    assert calculate_drawdown(D(80), D(100)) == -20
    assert calculate_drawdown(D(100), D(100)) == 0
    assert calculate_drawdown(D(1), D(0)) is None


def test_rsi_known_monotonic_flat_and_wilder_smoothing():
    assert calculate_rsi([D(100)] * 14) is None
    assert calculate_rsi([D(100)] * 15) == 50
    assert calculate_rsi([D(v) for v in range(15)]) == 100
    assert calculate_rsi([D(v) for v in range(15, 0, -1)]) == 0
    # 14 gains and one loss: smoothed avg gain=13/14, loss=1/14, RSI=92.857...
    prices = [D(100 + v) for v in range(15)] + [D(113)]
    assert abs(calculate_rsi(prices) - D("92.857142857142857142857")) < D("1e-18")
    with pytest.raises(ValueError, match="RSI"):
        calculate_rsi(prices, 0)


def test_volume_zscore_constant_and_reference():
    assert calculate_volume_zscore([100] * 19) is None
    assert calculate_volume_zscore([100] * 20) == 0
    # [1,3] has mean=2, sample std=sqrt(2): latest z=1/sqrt(2)
    assert abs(calculate_volume_zscore([1, 3], 2) - D(1) / D(2).sqrt()) < D("1e-24")
    with pytest.raises(ValueError, match="Volume"):
        calculate_volume_zscore([100] * 20, 1)


def test_complete_history_warmup_and_no_cross_asset_leakage():
    aapl = [record(i, volume=1000 + i * 10) for i in range(55)]
    msft = [record(i, symbol="MSFT", close="100") for i in range(5)]
    other_source = [record(i, source="secondary", close="100") for i in range(3)]
    rows = calculate_market_indicators(list(reversed(aapl + msft + other_source)))
    by_identity = {}
    for row in rows:
        by_identity.setdefault((row.record.source, row.record.symbol), []).append(row)
    prices = by_identity["twelve_data", "AAPL"]
    assert len(prices) == 55
    assert prices[0].period_return is None
    assert prices[0].drawdown == 0
    assert prices[18].sma_20 is None
    assert prices[19].sma_20 is not None
    assert prices[48].sma_50 is None
    assert prices[49].sma_50 is not None
    assert prices[18].volume_zscore is None
    assert prices[19].volume_zscore is not None
    assert prices[19].rolling_volatility_20d is None
    assert prices[20].rolling_volatility_20d is not None
    assert prices[13].rsi_14 is None
    assert prices[14].rsi_14 == 100
    assert prices[-1].log_return > 0
    assert prices[-1].drawdown == 0
    assert by_identity["twelve_data", "MSFT"][0].period_return is None
    assert by_identity["twelve_data", "MSFT"][-1].rsi_14 is None
    assert by_identity["secondary", "AAPL"][0].period_return is None


def test_replay_is_deterministic_and_values_map_to_existing_gold_columns():
    records = [record(i, close=str(100 + i % 7), volume=1000 + i) for i in range(55)]
    forward = calculate_market_indicators(records)
    backward = calculate_market_indicators(list(reversed(records)))
    assert forward == backward
    mapped = to_gold_indicator_values(forward[-1])
    assert set(mapped) == {
        "price_change",
        "daily_return_pct",
        "sma_7",
        "sma_30",
        "period_return",
        "log_return",
        "sma_20",
        "sma_50",
        "rolling_volatility_20d",
        "rsi_14",
        "drawdown",
        "volume_zscore",
    }
    assert mapped["sma_20"] is not None
    assert mapped["rsi_14"] is not None
    assert mapped["volume_zscore"] is not None


def test_duplicate_observation_is_rejected_without_mutating_input():
    first = record(0)
    with pytest.raises(ValueError, match="Duplicate market observation"):
        calculate_market_indicators([first, replace(first, volume=900)])


def test_gold_mapping_rounds_to_numeric_scale_for_idempotent_replay():
    base = calculate_market_indicators([record(i) for i in range(55)])[-1]
    exact = replace(base, log_return=D("0.123456785"), rsi_14=D("52.1234567899"))
    values = to_gold_indicator_values(exact)
    assert values["log_return"] == D("0.12345679")
    assert values["rsi_14"] == D("52.12345679")
    assert all(v is None or v.as_tuple().exponent >= -8 for v in values.values())
