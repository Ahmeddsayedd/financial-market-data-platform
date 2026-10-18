from decimal import Decimal

from financial_data_platform.analytics.indicators import MarketIndicators


def to_gold_indicator_values(
    indicators: MarketIndicators,
) -> dict[str, Decimal | None]:
    """Map calculated indicators to Gold PostgreSQL column values."""

    return {
        "price_change": indicators.price_change,
        "daily_return_pct": indicators.daily_return_pct,
        "sma_7": indicators.sma_7,
        "sma_30": indicators.sma_30,
    }