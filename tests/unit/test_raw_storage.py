import json
import pytest
from datetime import datetime, timedelta, timezone

from financial_data_platform.storage.raw import RawResponseWriter


def test_write_preserves_provider_payload(tmp_path):
    payload = {
        "meta": {
            "symbol": "AAPL",
            "interval": "1day",
        },
        "values": [
            {
                "datetime": "2026-09-25",
                "open": "100.00",
                "high": "105.00",
                "low": "99.00",
                "close": "104.00",
                "volume": "123456",
            }
        ],
        "status": "ok",
    }

    extracted_at = datetime(
        2026,
        10,
        6,
        18,
        30,
        45,
        tzinfo=timezone.utc,
    )

    writer = RawResponseWriter(base_dir=tmp_path)

    raw_path = writer.write(
        payload,
        provider="twelve_data",
        symbol="AAPL",
        extracted_at=extracted_at,
    )

    with raw_path.open("r", encoding="utf-8") as raw_file:
        stored_payload = json.load(raw_file)

    assert stored_payload == payload


def test_write_uses_deterministic_partitioned_path(tmp_path):
        payload = {
            "meta": {"symbol": "AAPL"},
            "values": [],
            "status": "ok",
        }

        extracted_at = datetime(
            2026,
            10,
            6,
            18,
            30,
            45,
            tzinfo=timezone.utc,
        )

        writer = RawResponseWriter(base_dir=tmp_path)

        raw_path = writer.write(
            payload,
            provider="twelve_data",
            symbol="AAPL",
            extracted_at=extracted_at,
        )

        expected_path = (
            tmp_path
            / "twelve_data"
            / "AAPL"
            / "2026"
            / "10"
            / "06"
            / "20261006T183045000000Z.json"
        )

        assert raw_path == expected_path


def test_write_rejects_naive_extraction_timestamp(tmp_path):
    writer = RawResponseWriter(base_dir=tmp_path)

    naive_extracted_at = datetime(
        2026,
        10,
        6,
        18,
        30,
        45,
    )

    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        writer.write(
            {"status": "ok"},
            provider="twelve_data",
            symbol="AAPL",
            extracted_at=naive_extracted_at,
        )


def test_write_normalizes_extraction_timestamp_to_utc(tmp_path):
    payload = {"status": "ok"}

    extracted_at = datetime(
        2026,
        10,
        6,
        20,
        30,
        45,
        tzinfo=timezone(timedelta(hours=2)),
    )

    writer = RawResponseWriter(base_dir=tmp_path)

    raw_path = writer.write(
        payload,
        provider="twelve_data",
        symbol="AAPL",
        extracted_at=extracted_at,
    )

    expected_path = (
        tmp_path
        / "twelve_data"
        / "AAPL"
        / "2026"
        / "10"
        / "06"
        / "20261006T183045000000Z.json"
    )

    assert raw_path == expected_path


def test_write_is_idempotent_for_same_extraction(tmp_path):
    payload = {
        "meta": {"symbol": "AAPL"},
        "values": [{"datetime": "2026-09-25"}],
        "status": "ok",
    }

    extracted_at = datetime(
        2026,
        10,
        6,
        18,
        30,
        45,
        tzinfo=timezone.utc,
    )

    writer = RawResponseWriter(base_dir=tmp_path)

    first_path = writer.write(
        payload,
        provider="twelve_data",
        symbol="AAPL",
        extracted_at=extracted_at,
    )

    second_path = writer.write(
        payload,
        provider="twelve_data",
        symbol="AAPL",
        extracted_at=extracted_at,
    )

    assert first_path == second_path

    with second_path.open("r", encoding="utf-8") as raw_file:
        stored_payload = json.load(raw_file)

    assert stored_payload == payload



@pytest.mark.parametrize(
    "symbol",
    [
        "../AAPL",
        "AAPL/../../secret",
        r"AAPL\secret",
    ],
)
def test_write_rejects_unsafe_symbol(tmp_path, symbol):
    writer = RawResponseWriter(base_dir=tmp_path)

    extracted_at = datetime(
        2026,
        10,
        6,
        18,
        30,
        45,
        tzinfo=timezone.utc,
    )

    with pytest.raises(
        ValueError,
        match="symbol",
    ):
        writer.write(
            {"status": "ok"},
            provider="twelve_data",
            symbol=symbol,
            extracted_at=extracted_at,
        )


@pytest.mark.parametrize(
    "provider",
    [
        "../twelve_data",
        "twelve/data",
        r"twelve\data",
    ],
)
def test_write_rejects_unsafe_provider(tmp_path, provider):
    writer = RawResponseWriter(base_dir=tmp_path)

    extracted_at = datetime(
        2026,
        10,
        6,
        18,
        30,
        45,
        tzinfo=timezone.utc,
    )

    with pytest.raises(
        ValueError,
        match="provider",
    ):
        writer.write(
            {"status": "ok"},
            provider=provider,
            symbol="AAPL",
            extracted_at=extracted_at,
        )


def test_write_rejects_empty_symbol(tmp_path):
    writer = RawResponseWriter(base_dir=tmp_path)

    with pytest.raises(ValueError, match="symbol"):
        writer.write(
            {"status": "ok"},
            provider="twelve_data",
            symbol="   ",
            extracted_at=datetime(
                2026,
                10,
                6,
                18,
                30,
                45,
                tzinfo=timezone.utc,
            ),
        )


def test_write_rejects_empty_provider(tmp_path):
    writer = RawResponseWriter(base_dir=tmp_path)

    with pytest.raises(ValueError, match="provider"):
        writer.write(
            {"status": "ok"},
            provider="   ",
            symbol="AAPL",
            extracted_at=datetime(
                2026,
                10,
                6,
                18,
                30,
                45,
                tzinfo=timezone.utc,
            ),
        )