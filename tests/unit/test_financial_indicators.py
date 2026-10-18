from decimal import Decimal
from datetime import date, datetime, timezone
from dataclasses import replace
from financial_data_platform.models.market_data import MarketDataRecord
from financial_data_platform.analytics.indicators import (
    calculate_price_change,
    calculate_daily_return_pct,
    calculate_sma,
    sort_market_records,
    calculate_market_indicators,
)

import pytest


def test_calculate_price_change_positive():
    """Calculate the absolute change between two closing prices."""

    previous_close = Decimal("250.00000000")
    current_close = Decimal("253.50000000")

    result = calculate_price_change(
        current_close=current_close,
        previous_close=previous_close,
    )

    assert result == Decimal("3.50000000")


def test_calculate_price_change_negative():
    """A falling closing price produces a negative change."""

    result = calculate_price_change(
        current_close=Decimal("247.00000000"),
        previous_close=Decimal("250.00000000"),
    )

    assert result == Decimal("-3.00000000")


def test_calculate_price_change_zero():
    """An unchanged closing price produces zero change."""

    result = calculate_price_change(
        current_close=Decimal("250.00000000"),
        previous_close=Decimal("250.00000000"),
    )

    assert result == Decimal("0.00000000")


def test_calculate_daily_return_pct_positive():
    """Calculate a positive daily return percentage using Decimal."""

    result = calculate_daily_return_pct(
        current_close=Decimal("210.00000000"),
        previous_close=Decimal("200.00000000"),
    )

    assert result == Decimal("5.00")


def test_calculate_daily_return_pct_negative():
    """A falling closing price produces a negative percentage return."""

    result = calculate_daily_return_pct(
        current_close=Decimal("190.00000000"),
        previous_close=Decimal("200.00000000"),
    )

    assert result == Decimal("-5.00")


def test_calculate_daily_return_pct_zero_previous_close():
    """An undefined return is represented by None."""

    result = calculate_daily_return_pct(
        current_close=Decimal("210.00000000"),
        previous_close=Decimal("0.00000000"),
    )

    assert result is None


def test_calculate_sma_7():
    """Calculate the average of seven closing prices."""

    closing_prices = [
        Decimal("100.00"),
        Decimal("102.00"),
        Decimal("104.00"),
        Decimal("106.00"),
        Decimal("108.00"),
        Decimal("110.00"),
        Decimal("112.00"),
    ]

    result = calculate_sma(
        closing_prices=closing_prices,
        window=7,
    )

    assert result == Decimal("106.00")


def test_calculate_sma_7_insufficient_history():
    """SMA 7 is unavailable with fewer than seven observations."""

    closing_prices = [
        Decimal("100.00"),
        Decimal("102.00"),
        Decimal("104.00"),
        Decimal("106.00"),
        Decimal("108.00"),
        Decimal("110.00"),
    ]

    result = calculate_sma(
        closing_prices=closing_prices,
        window=7,
    )

    assert result is None


def test_calculate_sma_30():
    """Calculate SMA 30 using thirty closing prices."""

    closing_prices = [
        Decimal(str(price))
        for price in range(1, 31)
    ]

    result = calculate_sma(
        closing_prices=closing_prices,
        window=30,
    )

    assert result == Decimal("15.5")


def test_calculate_sma_30_insufficient_history():
    """SMA 30 is unavailable with only 29 observations."""

    closing_prices = [
        Decimal(str(price))
        for price in range(1, 30)
    ]

    result = calculate_sma(
        closing_prices=closing_prices,
        window=30,
    )

    assert result is None


def test_calculate_sma_uses_latest_observations():
    """SMA uses the latest window, not the entire price history."""

    closing_prices = [
        Decimal(str(price))
        for price in range(1, 11)
    ]

    result = calculate_sma(
        closing_prices=closing_prices,
        window=7,
    )

    # The last seven prices are 4, 5, 6, 7, 8, 9, 10.
    assert result == Decimal("7")


@pytest.mark.parametrize("window", [0, -7])
def test_calculate_sma_rejects_invalid_window(window):
    """SMA must reject zero and negative window sizes."""

    closing_prices = [
        Decimal("100.00"),
        Decimal("102.00"),
        Decimal("104.00"),
    ]

    with pytest.raises(ValueError, match="SMA window must be positive"):
        calculate_sma(
            closing_prices=closing_prices,
            window=window,
        )


def test_sort_market_records_by_observation_date():
    """Market records are sorted chronologically, regardless of input order."""

    def make_record(day: int) -> MarketDataRecord:
        return MarketDataRecord(
            symbol="AAPL",
            observation_date=date(2026, 10, day),
            open=Decimal("100.00"),
            high=Decimal("105.00"),
            low=Decimal("98.00"),
            close=Decimal("102.00"),
            volume=1000,
            source="twelve_data",
            extracted_at=datetime(
                2026, 10, 10, 18, 0, tzinfo=timezone.utc
            ),
        )

    records = [
        make_record(9),
        make_record(7),
        make_record(8),
    ]

    result = sort_market_records(records)

    assert [record.observation_date for record in result] == [
        date(2026, 10, 7),
        date(2026, 10, 8),
        date(2026, 10, 9),
    ]

    # The original input must remain unchanged.
    assert records[0].observation_date == date(2026, 10, 9)


def test_calculate_market_indicators_first_observation():
    """The first observation has no previous close or moving averages."""

    record = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 9),
        open=Decimal("100.00"),
        high=Decimal("105.00"),
        low=Decimal("98.00"),
        close=Decimal("102.00"),
        volume=1000,
        source="twelve_data",
        extracted_at=datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    )

    result = calculate_market_indicators([record])

    assert len(result) == 1
    assert result[0].record == record
    assert result[0].price_change is None
    assert result[0].daily_return_pct is None
    assert result[0].sma_7 is None
    assert result[0].sma_30 is None


def test_calculate_market_indicators_second_observation():
    """Calculate price change and return from the previous close."""

    first = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 8),
        open=Decimal("99.00"),
        high=Decimal("102.00"),
        low=Decimal("98.00"),
        close=Decimal("100.00"),
        volume=1000,
        source="twelve_data",
        extracted_at=datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    )

    second = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 9),
        open=Decimal("101.00"),
        high=Decimal("106.00"),
        low=Decimal("100.00"),
        close=Decimal("105.00"),
        volume=1100,
        source="twelve_data",
        extracted_at=datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    )

    results = calculate_market_indicators([first, second])

    assert len(results) == 2

    assert results[0].price_change is None
    assert results[0].daily_return_pct is None

    assert results[1].record == second
    assert results[1].price_change == Decimal("5.00")
    assert results[1].daily_return_pct == Decimal("5.00")
    assert results[1].sma_7 is None
    assert results[1].sma_30 is None


def test_calculate_market_indicators_sma_7():
    """SMA 7 first becomes available on the seventh observation."""

    records = []

    for day in range(1, 8):
        closing_price = Decimal(100 + day)

        records.append(
            MarketDataRecord(
                symbol="AAPL",
                observation_date=date(2026, 10, day),
                open=closing_price,
                high=closing_price + Decimal("2"),
                low=closing_price - Decimal("2"),
                close=closing_price,
                volume=1000,
                source="twelve_data",
                extracted_at=datetime(
                    2026, 10, 8, 18, 0, tzinfo=timezone.utc
                ),
            )
        )

    results = calculate_market_indicators(records)

    assert len(results) == 7

    for result in results[:6]:
        assert result.sma_7 is None

    # Average of closing prices 101 through 107.
    assert results[6].sma_7 == Decimal("104")
    assert results[6].sma_30 is None


def test_calculate_market_indicators_sma_30():
    """SMA 30 becomes available on the thirtieth observation."""

    from datetime import timedelta

    start_date = date(2026, 9, 1)
    records = []

    for index in range(30):
        closing_price = Decimal(index + 1)

        records.append(
            MarketDataRecord(
                symbol="AAPL",
                observation_date=start_date + timedelta(days=index),
                open=closing_price,
                high=closing_price + Decimal("2"),
                low=closing_price,
                close=closing_price,
                volume=1000,
                source="twelve_data",
                extracted_at=datetime(
                    2026, 10, 1, 18, 0, tzinfo=timezone.utc
                ),
            )
        )

    results = calculate_market_indicators(records)

    assert len(results) == 30

    for result in results[:29]:
        assert result.sma_30 is None

    assert results[29].sma_30 == Decimal("15.5")


def test_calculate_market_indicators_separates_symbols():
    """Different symbols must have independent price histories."""

    base = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 8),
        open=Decimal("100.00"),
        high=Decimal("105.00"),
        low=Decimal("98.00"),
        close=Decimal("100.00"),
        volume=1000,
        source="twelve_data",
        extracted_at=datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    )

    records = [
        base,
        replace(
            base,
            symbol="MSFT",
            close=Decimal("200.00"),
            high=Decimal("205.00"),
        ),
        replace(
            base,
            observation_date=date(2026, 10, 9),
            close=Decimal("105.00"),
        ),
        replace(
            base,
            symbol="MSFT",
            observation_date=date(2026, 10, 9),
            close=Decimal("210.00"),
            high=Decimal("215.00"),
        ),
    ]

    results = calculate_market_indicators(records)

    by_identity = {
        (result.record.symbol, result.record.observation_date): result
        for result in results
    }

    assert by_identity["AAPL", date(2026, 10, 8)].price_change is None
    assert by_identity["MSFT", date(2026, 10, 8)].price_change is None

    assert by_identity["AAPL", date(2026, 10, 9)].price_change == Decimal("5.00")
    assert by_identity["MSFT", date(2026, 10, 9)].price_change == Decimal("10.00")

    assert by_identity["AAPL", date(2026, 10, 9)].daily_return_pct == Decimal("5.00")
    assert by_identity["MSFT", date(2026, 10, 9)].daily_return_pct == Decimal("5.00")


def test_calculate_market_indicators_separates_sources():
    """The same symbol from different sources has independent history."""

    base = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 8),
        open=Decimal("100.00"),
        high=Decimal("105.00"),
        low=Decimal("98.00"),
        close=Decimal("100.00"),
        volume=1000,
        source="twelve_data",
        extracted_at=datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    )

    records = [
        base,
        replace(
            base,
            source="alternative_source",
            close=Decimal("200.00"),
            high=Decimal("205.00"),
        ),
        replace(
            base,
            observation_date=date(2026, 10, 9),
            close=Decimal("105.00"),
        ),
        replace(
            base,
            source="alternative_source",
            observation_date=date(2026, 10, 9),
            close=Decimal("210.00"),
            high=Decimal("215.00"),
        ),
    ]

    results = calculate_market_indicators(records)

    by_identity = {
        (result.record.source, result.record.observation_date): result
        for result in results
    }

    assert by_identity["twelve_data", date(2026, 10, 8)].price_change is None
    assert by_identity["alternative_source", date(2026, 10, 8)].price_change is None

    assert by_identity["twelve_data", date(2026, 10, 9)].price_change == Decimal("5.00")
    assert by_identity["alternative_source", date(2026, 10, 9)].price_change == Decimal("10.00")

    assert by_identity["twelve_data", date(2026, 10, 9)].daily_return_pct == Decimal("5.00")
    assert by_identity["alternative_source", date(2026, 10, 9)].daily_return_pct == Decimal("5.00")


def test_calculate_market_indicators_rejects_duplicate_observations():
    """Reject duplicate source, symbol, and observation-date identities."""

    record = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 9),
        open=Decimal("100.00"),
        high=Decimal("105.00"),
        low=Decimal("98.00"),
        close=Decimal("102.00"),
        volume=1000,
        source="twelve_data",
        extracted_at=datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    )

    duplicate = replace(
        record,
        close=Decimal("103.00"),
    )

    with pytest.raises(ValueError, match="Duplicate market observation"):
        calculate_market_indicators([record, duplicate])


def test_calculate_market_indicators_independent_of_input_order():
    """Shuffling input records must not change calculated results."""

    base = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 7),
        open=Decimal("100.00"),
        high=Decimal("105.00"),
        low=Decimal("98.00"),
        close=Decimal("100.00"),
        volume=1000,
        source="twelve_data",
        extracted_at=datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    )

    first = base

    second = replace(
        base,
        observation_date=date(2026, 10, 8),
        close=Decimal("102.00"),
    )

    third = replace(
        base,
        observation_date=date(2026, 10, 9),
        close=Decimal("104.00"),
    )

    chronological = calculate_market_indicators(
        [first, second, third]
    )

    shuffled = calculate_market_indicators(
        [third, first, second]
    )

    assert shuffled == chronological


def test_calculate_market_indicators_empty_input():
    """An empty input produces no calculated indicators."""

    result = calculate_market_indicators([])

    assert result == []