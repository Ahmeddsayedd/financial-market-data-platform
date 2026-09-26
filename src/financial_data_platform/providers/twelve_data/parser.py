from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from financial_data_platform.models import MarketDataRecord


class TwelveDataParseError(ValueError):
    """Raised when a Twelve Data response cannot be parsed safely."""


def parse_time_series(
    payload: dict[str, Any],
    *,
    extracted_at: datetime,
) -> list[MarketDataRecord]:
    """Convert a Twelve Data time-series response to canonical records."""

    if extracted_at.tzinfo is None or extracted_at.utcoffset() is None:
        raise TwelveDataParseError(
            "extracted_at must be timezone-aware."
    )

    values = payload.get("values")
    meta = payload.get("meta")

    if not isinstance(values, list):
        raise TwelveDataParseError(
            "Twelve Data response does not contain a valid 'values' list."
        )

    if not values:
        raise TwelveDataParseError(
        "Twelve Data response contains no observations."
    )

    if not isinstance(meta, dict):
        raise TwelveDataParseError(
            "Twelve Data response does not contain valid 'meta' data."
        )

    symbol = meta.get("symbol")

    if not isinstance(symbol, str) or not symbol.strip():
        raise TwelveDataParseError(
            "Twelve Data response does not contain a valid symbol."
        )

    records: list[MarketDataRecord] = []

    for index, value in enumerate(values):
        if not isinstance(value, dict):
            raise TwelveDataParseError(
                f"Observation at index {index} is not a valid object."
            )

        try:
            record = MarketDataRecord(
                symbol=symbol,
                observation_date=datetime.strptime(
                    value["datetime"], "%Y-%m-%d"
                ).date(),
                open=Decimal(value["open"]),
                high=Decimal(value["high"]),
                low=Decimal(value["low"]),
                close=Decimal(value["close"]),
                volume=int(value["volume"]),
                source="twelve_data",
                extracted_at=extracted_at,
            )
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise TwelveDataParseError(
                f"Invalid observation at index {index}."
            ) from exc

        records.append(record)

    return records