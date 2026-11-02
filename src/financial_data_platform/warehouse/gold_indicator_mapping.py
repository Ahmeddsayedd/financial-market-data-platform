from decimal import Decimal, ROUND_HALF_UP, localcontext

from financial_data_platform.analytics.indicators import MarketIndicators


def to_gold_indicator_values(
    indicators: MarketIndicators,
) -> dict[str, Decimal | None]:
    """Map calculated indicators to Gold PostgreSQL column values."""

    values = {
        "price_change": indicators.price_change,
        "daily_return_pct": indicators.daily_return_pct,
        "sma_7": indicators.sma_7,
        "sma_30": indicators.sma_30,
        "period_return": indicators.period_return,
        "log_return": indicators.log_return,
        "sma_20": indicators.sma_20,
        "sma_50": indicators.sma_50,
        "rolling_volatility_20d": indicators.rolling_volatility_20d,
        "rsi_14": indicators.rsi_14,
        "drawdown": indicators.drawdown,
        "volume_zscore": indicators.volume_zscore,
    }

    # Match PostgreSQL NUMERIC(20,8) rounding before the null-safe comparison.
    # Without pre-rounding, a replay of high-precision log/RSI values would
    # compare unequal to the rounded database values and rewrite every row.
    with localcontext() as context:
        context.prec = 34
        return {
            name: (
                value.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
                if value is not None
                else None
            )
            for name, value in values.items()
        }
