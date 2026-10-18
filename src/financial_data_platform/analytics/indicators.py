from decimal import Decimal
from datetime import date
from financial_data_platform.models.market_data import MarketDataRecord
from dataclasses import dataclass


def calculate_price_change(
    current_close: Decimal,
    previous_close: Decimal,
) -> Decimal:
    """Calculate the absolute change between consecutive closing prices."""

    return current_close - previous_close


def calculate_daily_return_pct(
    current_close: Decimal,
    previous_close: Decimal,
) -> Decimal | None:
    """Calculate daily percentage return using Decimal arithmetic.

    Return None when the previous closing price is zero.
    """
    if previous_close == 0:
        return None

    return (
        (current_close - previous_close)
        / previous_close
    ) * Decimal("100")


def calculate_sma(
    closing_prices: list[Decimal],
    window: int,
) -> Decimal | None:
    """Calculate the SMA over the latest `window` closing prices.

    Return None when insufficient observations are available.
    """
    if window <= 0:
        raise ValueError("SMA window must be positive")

    if len(closing_prices) < window:
        return None

    recent_prices = closing_prices[-window:]

    return sum(recent_prices, Decimal("0")) / Decimal(window)


def sort_market_records(
    records: list[MarketDataRecord],
) -> list[MarketDataRecord]:
    """Return market records sorted by observation date.

    Do not modify the original input list.
    """
    return sorted(
        records,
        key=lambda record: record.observation_date,
    )


@dataclass(frozen=True)
class MarketIndicators:
    """Calculated indicators associated with one market observation."""

    record: MarketDataRecord
    price_change: Decimal | None
    daily_return_pct: Decimal | None
    sma_7: Decimal | None
    sma_30: Decimal | None


def calculate_market_indicators(
    records: list[MarketDataRecord],
) -> list[MarketIndicators]:
    """Calculate indicators independently for each source and symbol."""

    sorted_records = sorted(
        records,
        key=lambda record: (
            record.source,
            record.symbol,
            record.observation_date,
        ),
    )

    results: list[MarketIndicators] = []
    seen_observations: set[tuple[str, str, date]] = set()
    previous_closes: dict[tuple[str, str], Decimal] = {}
    closing_histories: dict[tuple[str, str], list[Decimal]] = {}

    for record in sorted_records:
        identity = (record.source, record.symbol)

        observation_identity = (
            record.source,
            record.symbol,
            record.observation_date,
        )

        if observation_identity in seen_observations:
            raise ValueError(
                f"Duplicate market observation: {observation_identity}"
            )

        seen_observations.add(observation_identity)

        previous_close = previous_closes.get(identity)

        if previous_close is None:
            price_change = None
            daily_return_pct = None
        else:
            price_change = calculate_price_change(
                current_close=record.close,
                previous_close=previous_close,
            )
            daily_return_pct = calculate_daily_return_pct(
                current_close=record.close,
                previous_close=previous_close,
            )

        closing_prices = closing_histories.setdefault(identity, [])
        closing_prices.append(record.close)

        sma_7 = calculate_sma(
            closing_prices=closing_prices,
            window=7,
        )
        sma_30 = calculate_sma(
            closing_prices=closing_prices,
            window=30,
        )

        results.append(
            MarketIndicators(
                record=record,
                price_change=price_change,
                daily_return_pct=daily_return_pct,
                sma_7=sma_7,
                sma_30=sma_30,
            )
        )

        previous_closes[identity] = record.close

    return results