from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any
import re
from financial_data_platform.models import MarketDataRecord


class TwelveDataParseError(ValueError):
    """Raised when a Twelve Data response cannot be parsed safely."""

def _parse_volume(value: object) -> int:
    """Parse an exact integer volume without truncation or coercion."""
    if type(value) is int:
        return value

    if isinstance(value, str) and re.fullmatch(r"-?[0-9]+", value):
        return int(value)

    raise TwelveDataParseError(
        "Trading volume must be an integer or an integer string."
    )


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

    if not isinstance(payload, dict):
        raise TwelveDataParseError(
            "Twelve Data response must be a JSON object."
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
    seen_dates: set = set()

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
                volume=_parse_volume(value["volume"]),
                source="twelve_data",
                extracted_at=extracted_at,
            )
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise TwelveDataParseError(
                f"Invalid observation at index {index}."
            ) from exc


        if record.observation_date in seen_dates:
            raise TwelveDataParseError(
                "Duplicate observation date "
                f"{record.observation_date.isoformat()} "
                f"at index {index}."
            )

        seen_dates.add(record.observation_date)

        records.append(record)

    return records