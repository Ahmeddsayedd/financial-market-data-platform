import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class RawResponseWriter:
    """Persist unmodified provider JSON payloads to the raw data layer."""

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)

    def write(
        self,
        payload: dict[str, Any],
        *,
        provider: str,
        symbol: str,
        extracted_at: datetime,
    ) -> Path:
        if not provider.strip():
            raise ValueError("provider must not be empty.")

        if "/" in provider or "\\" in provider or ".." in provider:
            raise ValueError("provider contains unsafe path characters.")
        
        if not symbol.strip():
            raise ValueError("symbol must not be empty.")

        if "/" in symbol or "\\" in symbol or ".." in symbol:
            raise ValueError("symbol contains unsafe path characters.")
        
        if extracted_at.tzinfo is None or extracted_at.utcoffset() is None:
            raise ValueError("extracted_at must be timezone-aware.")

        extracted_at_utc = extracted_at.astimezone(timezone.utc)

        timestamp = extracted_at_utc.strftime("%Y%m%dT%H%M%S%fZ")

        raw_directory = (
            self.base_dir
            / provider
            / symbol
            / extracted_at.strftime("%Y")
            / extracted_at.strftime("%m")
            / extracted_at.strftime("%d")
        )

        raw_path = raw_directory / f"{timestamp}.json"

        raw_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        with raw_path.open("w", encoding="utf-8") as raw_file:
            json.dump(payload, raw_file)

        return raw_path
