from decimal import Decimal, localcontext
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

    return ((current_close - previous_close) / previous_close) * Decimal("100")


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


def calculate_log_return(
    current_close: Decimal, previous_close: Decimal
) -> Decimal | None:
    """Natural log of the close ratio; undefined for nonpositive prices."""
    if current_close <= 0 or previous_close <= 0:
        return None
    with localcontext() as context:
        context.prec = 34
        return (current_close / previous_close).ln()


def calculate_rolling_volatility(
    daily_returns: list[Decimal], window: int = 20
) -> Decimal | None:
    """Annualized sample standard deviation of decimal daily returns, in percent.

    Uses sqrt(252) trading days; requires `window` valid consecutive returns.
    """
    if window < 2:
        raise ValueError("Volatility window must be at least two")
    if len(daily_returns) < window:
        return None
    values = daily_returns[-window:]
    with localcontext() as context:
        context.prec = 34
        mean = sum(values, Decimal(0)) / Decimal(window)
        variance = sum(((value - mean) ** 2 for value in values), Decimal(0)) / Decimal(
            window - 1
        )
        return variance.sqrt() * Decimal(252).sqrt() * Decimal(100)


def calculate_drawdown(current_close: Decimal, running_peak: Decimal) -> Decimal | None:
    """Drawdown from the maximum observed close, in percent (nonpositive)."""
    if running_peak <= 0:
        return None
    return (current_close / running_peak - Decimal(1)) * Decimal(100)


def calculate_volume_zscore(volumes: list[int], window: int = 20) -> Decimal | None:
    """Current volume vs trailing `window` volumes, using sample deviation.

    Constant-volume windows yield zero (rather than division by zero).
    """
    if window < 2:
        raise ValueError("Volume window must be at least two")
    if len(volumes) < window:
        return None
    with localcontext() as context:
        context.prec = 34
        values = [Decimal(v) for v in volumes[-window:]]
        mean = sum(values, Decimal(0)) / Decimal(window)
        variance = sum(((v - mean) ** 2 for v in values), Decimal(0)) / Decimal(
            window - 1
        )
        if not variance:
            return Decimal(0)
        return (values[-1] - mean) / variance.sqrt()


def calculate_rsi(closes: list[Decimal], period: int = 14) -> Decimal | None:
    """Wilder-smoothed RSI: first value after `period` close-to-close changes.

    Empty gain/loss windows: flat=50; only gains=100; only losses=0.
    """
    if period < 1:
        raise ValueError("RSI period must be positive")
    if len(closes) <= period:
        return None
    changes = [b - a for a, b in zip(closes, closes[1:])]
    gains = [max(Decimal(0), change) for change in changes]
    losses = [max(Decimal(0), -change) for change in changes]
    with localcontext() as context:
        context.prec = 34
        average_gain = sum(gains[:period], Decimal(0)) / Decimal(period)
        average_loss = sum(losses[:period], Decimal(0)) / Decimal(period)
        for gain, loss in zip(gains[period:], losses[period:]):
            average_gain = (average_gain * (period - 1) + gain) / Decimal(period)
            average_loss = (average_loss * (period - 1) + loss) / Decimal(period)
        if not average_loss:
            return Decimal(50) if not average_gain else Decimal(100)
        if not average_gain:
            return Decimal(0)
        rs = average_gain / average_loss
        return Decimal(100) - Decimal(100) / (Decimal(1) + rs)


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
    period_return: Decimal | None = None
    log_return: Decimal | None = None
    sma_20: Decimal | None = None
    sma_50: Decimal | None = None
    rolling_volatility_20d: Decimal | None = None
    rsi_14: Decimal | None = None
    drawdown: Decimal | None = None
    volume_zscore: Decimal | None = None


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
    volume_histories: dict[tuple[str, str], list[int]] = {}
    return_histories: dict[tuple[str, str], list[Decimal]] = {}
    running_peaks: dict[tuple[str, str], Decimal] = {}
    rsi_wilder_state: dict[tuple[str, str], tuple[Decimal, Decimal]] = {}
    rsi_seed_gains: dict[tuple[str, str], list[Decimal]] = {}
    rsi_seed_losses: dict[tuple[str, str], list[Decimal]] = {}

    for record in sorted_records:
        identity = (record.source, record.symbol)

        observation_identity = (
            record.source,
            record.symbol,
            record.observation_date,
        )

        if observation_identity in seen_observations:
            raise ValueError(f"Duplicate market observation: {observation_identity}")

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

        volume_history = volume_histories.setdefault(identity, [])
        volume_history.append(record.volume)
        peak = max(running_peaks.get(identity, record.close), record.close)
        running_peaks[identity] = peak
        return_history = return_histories.setdefault(identity, [])
        if daily_return_pct is not None:
            return_history.append(daily_return_pct / Decimal(100))
        else:
            # An invalid previous price breaks a contiguous return window.
            return_history.clear()

        # Incremental Wilder smoothing avoids rescanning all historical closes
        # for each observation (linear instead of quadratic work per asset).
        rsi: Decimal | None = None
        if previous_close is not None:
            gain = max(record.close - previous_close, Decimal(0))
            loss = max(previous_close - record.close, Decimal(0))
            with localcontext() as context:
                context.prec = 34
                if identity in rsi_wilder_state:
                    previous_gain, previous_loss = rsi_wilder_state[identity]
                    avg_gain = (previous_gain * 13 + gain) / Decimal(14)
                    avg_loss = (previous_loss * 13 + loss) / Decimal(14)
                    rsi_wilder_state[identity] = (avg_gain, avg_loss)
                else:
                    gains = rsi_seed_gains.setdefault(identity, [])
                    losses = rsi_seed_losses.setdefault(identity, [])
                    gains.append(gain)
                    losses.append(loss)
                    if len(gains) == 14:
                        avg_gain = sum(gains, Decimal(0)) / Decimal(14)
                        avg_loss = sum(losses, Decimal(0)) / Decimal(14)
                        rsi_wilder_state[identity] = (avg_gain, avg_loss)
                if identity in rsi_wilder_state:
                    avg_gain, avg_loss = rsi_wilder_state[identity]
                    if not avg_loss:
                        rsi = Decimal(50) if not avg_gain else Decimal(100)
                    elif not avg_gain:
                        rsi = Decimal(0)
                    else:
                        rsi = Decimal(100) - Decimal(100) / (
                            Decimal(1) + avg_gain / avg_loss
                        )

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
                period_return=daily_return_pct,
                log_return=(
                    calculate_log_return(record.close, previous_close)
                    if previous_close is not None
                    else None
                ),
                sma_20=calculate_sma(closing_prices, 20),
                sma_50=calculate_sma(closing_prices, 50),
                rolling_volatility_20d=calculate_rolling_volatility(return_history),
                rsi_14=rsi,
                drawdown=calculate_drawdown(record.close, peak),
                volume_zscore=calculate_volume_zscore(volume_history),
            )
        )

        previous_closes[identity] = record.close

    return results
