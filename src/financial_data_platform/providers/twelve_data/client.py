import time
from collections.abc import Callable
from typing import Any

import requests


class TwelveDataClientError(RuntimeError):
    """Raised when Twelve Data cannot be queried successfully."""


class TwelveDataClient:
    """HTTP client for retrieving market data from Twelve Data."""

    BASE_URL = "https://api.twelvedata.com/time_series"

    def __init__(
        self,
        api_key: str,
        session: requests.Session | None = None,
        max_retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key.strip():
            raise ValueError("Twelve Data API key must not be empty.")

        if max_retries < 0:
            raise ValueError("max_retries must not be negative.")

        self.api_key = api_key
        self.session = session or requests.Session()
        self.max_retries = max_retries
        self.sleep = sleep

    def fetch_daily_time_series(self, symbol: str) -> dict[str, Any]:
        """Fetch daily time-series data for a symbol."""

        for attempt in range(self.max_retries + 1):
            try:
                response = self.session.get(
                    self.BASE_URL,
                    params={
                        "symbol": symbol,
                        "interval": "1day",
                        "apikey": self.api_key,
                    },
                    timeout=10,
                )
            except (requests.Timeout, requests.ConnectionError) as exc:
                if attempt < self.max_retries:
                    self.sleep(2**attempt)
                    continue

                raise TwelveDataClientError(
                    "Twelve Data request failed after network retries."
                ) from exc

            if response.status_code == 429 or 500 <= response.status_code < 600:
                if attempt < self.max_retries:
                    self.sleep(2**attempt)
                    continue

                raise TwelveDataClientError(
                    f"Twelve Data request failed after retries "
                    f"with HTTP {response.status_code}."
                )

            if 400 <= response.status_code < 500:
                raise TwelveDataClientError(
                    f"Twelve Data request failed with HTTP {response.status_code}."
                )

            try:
                payload = response.json()
            except ValueError as exc:
                raise TwelveDataClientError(
                    "Twelve Data returned invalid JSON."
                ) from exc

            if payload.get("status") == "error":
                raise TwelveDataClientError(
                    "Twelve Data provider returned an error."
                )

            return payload

        raise TwelveDataClientError("Twelve Data request failed unexpectedly.")
