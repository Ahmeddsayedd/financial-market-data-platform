from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class MarketDataRecord:
    """Canonical representation of one daily market observation."""

    symbol: str
    observation_date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: int
    source: str
    extracted_at: datetime