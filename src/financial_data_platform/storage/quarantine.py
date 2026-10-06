import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from financial_data_platform.validation.market_data import InvalidMarketDataRecord


def _validate_path_component(value: str) -> None:
    """Reject values that could escape the intended storage hierarchy."""
    if not value or "/" in value or "\\" in value or ".." in value:
        raise ValueError(
            "source and symbol must be safe path components"
        )

class QuarantineWriter:
    """Persist invalid market-data records to quarantine storage."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = base_dir

    def write(
        self,
        invalid_record: InvalidMarketDataRecord,
        *,
        detected_at: datetime,
    ) -> Path:
        """Persist one invalid record and return its quarantine path."""

        if detected_at.tzinfo is None or detected_at.utcoffset() is None:
            raise ValueError("detected_at must be timezone-aware")

        record = invalid_record.record

        _validate_path_component(record.source)
        _validate_path_component(record.symbol)

        detected_at = detected_at.astimezone(timezone.utc)

        timestamp = detected_at.strftime("%Y%m%dT%H%M%S%fZ")

        filename = (
            f"{timestamp}_{record.observation_date.isoformat()}.json"
        )

        path = (
            self.base_dir
            / record.source
            / record.symbol
            / detected_at.strftime("%Y")
            / detected_at.strftime("%m")
            / detected_at.strftime("%d")
            / filename
        )

        path.parent.mkdir(parents=True, exist_ok=True)

        payload = self._build_payload(
            invalid_record=invalid_record,
            detected_at=detected_at,
        )

        with path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, indent=2)

        return path

    @staticmethod
    def _build_payload(
        *,
        invalid_record: InvalidMarketDataRecord,
        detected_at: datetime,
    ) -> dict[str, Any]:
        """Build the JSON-serializable quarantine payload."""
        record = invalid_record.record

        return {
            "record": {
                "symbol": record.symbol,
                "observation_date": record.observation_date.isoformat(),
                "open": str(record.open),
                "high": str(record.high),
                "low": str(record.low),
                "close": str(record.close),
                "volume": record.volume,
                "source": record.source,
                "extracted_at": record.extracted_at.isoformat(),
            },
            "violations": [
                {
                    "code": violation.code,
                    "field": violation.field,
                    "message": violation.message,
                }
                for violation in invalid_record.violations
            ],
            "detected_at": detected_at.isoformat(),
        }