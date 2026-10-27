import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from copy import deepcopy
import pytest

from financial_data_platform.models import MarketDataRecord
from financial_data_platform.providers.twelve_data.parser import (
    TwelveDataParseError,
    parse_time_series,
)


FIXTURE_DIR = Path(__file__).parent.parent / "fixtures" / "twelve_data"


def load_fixture(filename: str) -> dict:
    with (FIXTURE_DIR / filename).open(encoding="utf-8") as file:
        return json.load(file)


def test_parse_valid_time_series_returns_canonical_records():
    payload = load_fixture("valid_time_series.json")
    extracted_at = datetime(2026, 9, 26, 20, 30, tzinfo=timezone.utc)

    records = parse_time_series(payload, extracted_at=extracted_at)

    assert len(records) == 2
    assert all(isinstance(record, MarketDataRecord) for record in records)

    first = records[0]

    assert first.symbol == "AAPL"
    assert first.observation_date == date(2026, 9, 25)
    assert first.open == Decimal("227.79000")
    assert first.high == Decimal("229.30000")
    assert first.low == Decimal("225.45000")
    assert first.close == Decimal("227.10000")
    assert first.volume == 48765000
    assert first.source == "twelve_data"
    assert first.extracted_at == extracted_at


def test_parse_time_series_maps_multiple_observations():
    payload = load_fixture("valid_time_series.json")
    extracted_at = datetime(2026, 9, 26, 20, 30, tzinfo=timezone.utc)

    records = parse_time_series(payload, extracted_at=extracted_at)

    assert [record.observation_date for record in records] == [
        date(2026, 9, 25),
        date(2026, 9, 24),
    ]


def test_parse_time_series_rejects_missing_values():
    payload = {
        "meta": {"symbol": "AAPL"},
        "status": "ok",
    }
    extracted_at = datetime(2026, 9, 26, 20, 30, tzinfo=timezone.utc)

    with pytest.raises(TwelveDataParseError):
        parse_time_series(payload, extracted_at=extracted_at)


def test_parse_time_series_rejects_provider_error_response():
    payload = {
        "code": 404,
        "message": "Symbol not found",
        "status": "error",
    }
    extracted_at = datetime(2026, 9, 26, 20, 30, tzinfo=timezone.utc)

    with pytest.raises(TwelveDataParseError):
        parse_time_series(payload, extracted_at=extracted_at)


def test_parse_time_series_rejects_empty_values():
    payload = {
        "meta": {"symbol": "AAPL"},
        "values": [],
        "status": "ok",
    }
    extracted_at = datetime(2026, 9, 26, 20, 30, tzinfo=timezone.utc)

    with pytest.raises(TwelveDataParseError):
        parse_time_series(payload, extracted_at=extracted_at)


def test_parse_time_series_rejects_missing_symbol():
    payload = {
        "meta": {},
        "values": [
            {
                "datetime": "2026-09-25",
                "open": "227.79000",
                "high": "229.30000",
                "low": "225.45000",
                "close": "227.10000",
                "volume": "48765000",
            }
        ],
        "status": "ok",
    }
    extracted_at = datetime(2026, 9, 26, 20, 30, tzinfo=timezone.utc)

    with pytest.raises(TwelveDataParseError):
        parse_time_series(payload, extracted_at=extracted_at)


def test_parse_time_series_rejects_missing_observation_field():
    payload = {
        "meta": {"symbol": "AAPL"},
        "values": [
            {
                "datetime": "2026-09-25",
                "open": "227.79000",
                "high": "229.30000",
                "low": "225.45000",
                "volume": "48765000",
            }
        ],
        "status": "ok",
    }
    extracted_at = datetime(2026, 9, 26, 20, 30, tzinfo=timezone.utc)

    with pytest.raises(TwelveDataParseError):
        parse_time_series(payload, extracted_at=extracted_at)


def test_parse_time_series_rejects_invalid_numeric_value():
    payload = {
        "meta": {"symbol": "AAPL"},
        "values": [
            {
                "datetime": "2026-09-25",
                "open": "not-a-number",
                "high": "229.30000",
                "low": "225.45000",
                "close": "227.10000",
                "volume": "48765000",
            }
        ],
        "status": "ok",
    }
    extracted_at = datetime(2026, 9, 26, 20, 30, tzinfo=timezone.utc)

    with pytest.raises(TwelveDataParseError):
        parse_time_series(payload, extracted_at=extracted_at)


def test_parse_time_series_rejects_invalid_date():
    payload = {
        "meta": {"symbol": "AAPL"},
        "values": [
            {
                "datetime": "not-a-date",
                "open": "227.79000",
                "high": "229.30000",
                "low": "225.45000",
                "close": "227.10000",
                "volume": "48765000",
            }
        ],
        "status": "ok",
    }
    extracted_at = datetime(2026, 9, 26, 20, 30, tzinfo=timezone.utc)

    with pytest.raises(TwelveDataParseError):
        parse_time_series(payload, extracted_at=extracted_at)


def test_parse_time_series_rejects_naive_extraction_timestamp():
    payload = load_fixture("valid_time_series.json")
    extracted_at = datetime(2026, 9, 26, 20, 30)

    with pytest.raises(TwelveDataParseError):
        parse_time_series(payload, extracted_at=extracted_at)


@pytest.mark.parametrize(
    "invalid_volume",
    [
        "1.5",
        1.5,
        True,
        False,
        None,
        "not-a-number",
        "1e3",
        "",
    ],
)
def test_parser_rejects_non_integer_volumes(invalid_volume):
    """Volume must never be silently truncated or coerced."""
    payload = deepcopy(load_fixture("valid_time_series.json"))
    payload["values"][0]["volume"] = invalid_volume

    with pytest.raises(TwelveDataParseError):
        parse_time_series(
            payload,
            extracted_at=datetime(2026, 9, 26, 20, 30, tzinfo=timezone.utc),
        )


@pytest.mark.parametrize(
    "valid_volume, expected",
    [
        ("1000", 1000),
        (1000, 1000),
        ("0", 0),
        ("-100", -100),
    ],
)
def test_parser_preserves_exact_integer_volumes(
    valid_volume,
    expected,
):
    payload = deepcopy(load_fixture("valid_time_series.json"))
    payload["values"][0]["volume"] = valid_volume

    records = parse_time_series(
        payload,
        extracted_at=datetime(2026, 9, 26, 20, 30, tzinfo=timezone.utc),
    )

    assert records[0].volume == expected


def test_parser_rejects_duplicate_observation_dates():
    """A single response cannot contain two observations for one date."""
    payload = deepcopy(load_fixture("valid_time_series.json"))
    payload["values"].append(deepcopy(payload["values"][0]))

    with pytest.raises(
        TwelveDataParseError,
        match="Duplicate observation date",
    ):
        parse_time_series(
            payload,
            extracted_at=datetime(2026, 9, 26, 20, 30, tzinfo=timezone.utc),
        )


@pytest.mark.parametrize(
    "invalid_payload",
    [
        None,
        [],
        "invalid",
    ],
)
def test_parser_rejects_non_object_payloads(invalid_payload):
    with pytest.raises(
        TwelveDataParseError,
        match="JSON object",
    ):
        parse_time_series(
            invalid_payload,
            extracted_at=datetime(2026, 9, 26, 20, 30, tzinfo=timezone.utc),
        )
