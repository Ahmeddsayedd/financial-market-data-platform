"""Offline Issue #103 tests: no provider calls or real database writes."""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from financial_data_platform.experiments import live_market_verification as verification
from financial_data_platform.providers.twelve_data.client import TwelveDataClient
from financial_data_platform.storage.raw import RawResponseWriter


EXTRACTED = datetime(2026, 10, 9, 12, 0, tzinfo=timezone.utc)


def payload(symbol="AAPL"):
    return {
        "meta": {"symbol": symbol, "interval": "1day"},
        "values": [
            {
                "datetime": "2026-10-08",
                "open": "100",
                "high": "103",
                "low": "99",
                "close": "102",
                "volume": "2000",
            }
        ],
        "status": "ok",
    }


def create_raw(root: Path, symbol="AAPL") -> Path:
    return RawResponseWriter(root / "raw").write(
        payload(symbol), provider="twelve_data", symbol=symbol, extracted_at=EXTRACTED
    )


@pytest.mark.parametrize("symbol", ["", "aapl", "../AAPL", "AAPL/US", "A" * 16])
def test_rejects_unsafe_symbols(symbol):
    with pytest.raises(verification.VerificationError):
        verification.validate_symbol(symbol)


@pytest.mark.parametrize("size", [0, 59, 201, 10000])
def test_outputsize_bound(size):
    with pytest.raises(verification.VerificationError):
        verification.validate_outputsize(size)


def test_gold_preflight_refuses_main_database(monkeypatch):
    monkeypatch.setenv("POSTGRES_DB", "financial_market")
    with patch.object(verification, "_connect_test_database") as connect:
        with pytest.raises(verification.VerificationError, match="POSTGRES_DB"):
            verification.require_isolated_database(confirmation="financial_market_test")
        connect.assert_not_called()


def test_gold_preflight_validates_actual_database(monkeypatch):
    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")
    cursor = Mock()
    cursor.fetchone.return_value = ("financial_market",)
    connection = Mock()
    connection.cursor.return_value.__enter__ = Mock(return_value=cursor)
    connection.cursor.return_value.__exit__ = Mock(return_value=None)
    with patch.object(
        verification,
        "_connect_test_database",
        return_value=connection,
    ):
        with pytest.raises(verification.VerificationError, match="Connected"):
            verification.require_isolated_database(confirmation="financial_market_test")
    connection.close.assert_called_once()


def test_live_mode_bounded_request_and_evidence(tmp_path):
    raw = create_raw(tmp_path)
    client = Mock(spec=TwelveDataClient)
    silver_result = {
        "valid_count": 1,
        "silver_paths": [str(tmp_path / "silver" / "data.parquet")],
        "quality_report": {
            "total_records": 1,
            "valid_count": 1,
            "invalid_count": 0,
            "acceptance_rate": 1.0,
            "rejection_rate": 0.0,
            "violation_counts": {},
        },
    }
    with (
        patch.object(
            verification, "ingest_daily_market_data", return_value=raw
        ) as ingest,
        patch.object(verification, "_process_to_silver", return_value=silver_result),
    ):
        summary = verification.verify_market_data(
            experiment_root=tmp_path,
            symbol="AAPL",
            live_client=client,
        )
    assert ingest.call_count == 1
    assert ingest.call_args.kwargs["outputsize"] == 100
    assert summary["api_requests"] == 1
    assert summary["gold_write_enabled"] is False
    assert summary["raw_sha256"]
    assert (tmp_path / "last-live-summary.json").exists()


def test_replay_uses_zero_requests_and_same_raw_hash(tmp_path):
    raw = create_raw(tmp_path)
    with patch.object(verification, "_process_to_silver") as process:
        process.return_value = {
            "valid_count": 1,
            "silver_paths": [str(tmp_path / "silver.parquet")],
            "quality_report": {
                "total_records": 1,
                "valid_count": 1,
                "invalid_count": 0,
                "acceptance_rate": 1.0,
                "rejection_rate": 0.0,
                "violation_counts": {},
            },
        }
        result = verification.verify_market_data(
            experiment_root=tmp_path, symbol="AAPL", replay_raw=raw
        )
    assert result["mode"] == "replay"
    assert result["api_requests"] == 0
    assert (
        json.loads((tmp_path / "last-replay-summary.json").read_text())["raw_sha256"]
        == result["raw_sha256"]
    )


def test_replay_rejects_symbol_mismatch_before_transformation(tmp_path):
    raw = create_raw(tmp_path, "MSFT")
    with patch.object(verification, "_process_to_silver") as process:
        with pytest.raises(verification.VerificationError, match="symbol"):
            verification.verify_market_data(
                experiment_root=tmp_path, symbol="AAPL", replay_raw=raw
            )
        process.assert_not_called()


def test_replay_rejects_external_input(tmp_path):
    external = tmp_path.parent / "outside.json"
    with pytest.raises(verification.VerificationError, match="within"):
        verification.verify_market_data(
            experiment_root=tmp_path, symbol="AAPL", replay_raw=external
        )


def test_write_gold_denied_before_any_fetch_or_write(tmp_path, monkeypatch):
    monkeypatch.setenv("POSTGRES_DB", "financial_market")
    client = Mock(spec=TwelveDataClient)
    with patch.object(verification, "ingest_daily_market_data") as ingest:
        with pytest.raises(verification.VerificationError):
            verification.verify_market_data(
                experiment_root=tmp_path,
                symbol="AAPL",
                live_client=client,
                write_gold=True,
                confirm_test_db="financial_market_test",
            )
    ingest.assert_not_called()


def test_replay_gold_requires_preflight_and_records_counts(tmp_path):
    raw = create_raw(tmp_path)
    silver_result = {
        "valid_count": 1,
        "silver_paths": [str(tmp_path / "silver" / "data.parquet")],
        "quality_report": {
            "total_records": 1,
            "valid_count": 1,
            "invalid_count": 0,
            "acceptance_rate": 1.0,
            "rejection_rate": 0.0,
            "violation_counts": {},
        },
    }
    counts = {
        "market": {"inserted": 1, "updated": 0, "unchanged": 0, "rejected": 0},
        "indicators": {"updated": 1, "unchanged": 0},
    }
    with (
        patch.object(verification, "require_isolated_database") as preflight,
        patch.object(verification, "_process_to_silver", return_value=silver_result),
        patch.object(verification, "_load_gold_records", return_value=counts) as load,
    ):
        summary = verification.verify_market_data(
            experiment_root=tmp_path,
            symbol="AAPL",
            replay_raw=raw,
            write_gold=True,
            confirm_test_db="financial_market_test",
        )
    assert preflight.call_count == 2
    load.assert_called_once_with(silver_result["silver_paths"])
    assert summary["gold_database"] == "financial_market_test"
    assert summary["gold_counts"] == counts
    assert summary["api_requests"] == 0
