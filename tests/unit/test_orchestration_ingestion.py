"""Unit tests for the reusable orchestration ingestion adapter."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

from financial_data_platform.orchestration.ingestion import (
    ingest_market_symbols,
)


EXTRACTED_AT = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)


def test_ingestion_reuses_existing_components(tmp_path, monkeypatch):
    """The adapter must reuse the existing client, writer, and workflow."""
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "fake-test-key")

    expected_path = tmp_path / "twelve_data" / "AAPL" / "sample.json"

    with (
        patch(
            "financial_data_platform.orchestration.ingestion.TwelveDataClient"
        ) as mock_client,
        patch(
            "financial_data_platform.orchestration.ingestion.RawResponseWriter"
        ) as mock_writer,
        patch(
            "financial_data_platform.orchestration.ingestion.ingest_daily_market_data",
            return_value=expected_path,
        ) as mock_ingest,
    ):
        summary = ingest_market_symbols(
            symbols=("AAPL",),
            raw_base_dir=tmp_path,
            extracted_at=EXTRACTED_AT,
        )

    mock_client.assert_called_once_with(
        api_key="fake-test-key",
        max_retries=0,
    )
    mock_writer.assert_called_once_with(base_dir=tmp_path)
    mock_ingest.assert_called_once_with(
        symbol="AAPL",
        client=mock_client.return_value,
        raw_writer=mock_writer.return_value,
        extracted_at=EXTRACTED_AT,
    )

    assert summary == {
        "provider": "twelve_data",
        "status": "success",
        "symbols": ["AAPL"],
        "files_written": 1,
        "raw_paths": [str(expected_path)],
    }


def test_multiple_symbols_use_one_client(tmp_path, monkeypatch):
    """Multiple symbols should share the client and Raw writer."""
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "fake-test-key")

    with (
        patch(
            "financial_data_platform.orchestration.ingestion.TwelveDataClient"
        ) as mock_client,
        patch(
            "financial_data_platform.orchestration.ingestion.RawResponseWriter"
        ) as mock_writer,
        patch(
            "financial_data_platform.orchestration.ingestion.ingest_daily_market_data",
            side_effect=[
                Path("raw/AAPL.json"),
                Path("raw/MSFT.json"),
            ],
        ) as mock_ingest,
    ):
        summary = ingest_market_symbols(
            symbols=("AAPL", "MSFT"),
            raw_base_dir=tmp_path,
            extracted_at=EXTRACTED_AT,
        )

    mock_client.assert_called_once()
    mock_writer.assert_called_once()
    assert mock_ingest.call_count == 2
    assert summary["files_written"] == 2
    assert summary["symbols"] == ["AAPL", "MSFT"]


@pytest.mark.parametrize(
    "symbols",
    [
        (),
        ("",),
        ("AAPL", "AAPL"),
        ("AAPL", "  "),
    ],
)
def test_invalid_symbol_selection_is_rejected(tmp_path, symbols):
    """Reject invalid inputs before constructing an HTTP client."""
    with patch(
        "financial_data_platform.orchestration.ingestion.TwelveDataClient"
    ) as mock_client:
        with pytest.raises(ValueError):
            ingest_market_symbols(
                symbols=symbols,
                raw_base_dir=tmp_path,
                extracted_at=EXTRACTED_AT,
            )

    mock_client.assert_not_called()


def test_naive_timestamp_is_rejected(tmp_path):
    """Extraction timestamps must include a timezone."""
    with pytest.raises(ValueError, match="timezone-aware"):
        ingest_market_symbols(
            raw_base_dir=tmp_path,
            extracted_at=datetime(2026, 10, 24, 12, 0),
        )


def test_missing_api_key_fails_before_ingestion(tmp_path, monkeypatch):
    """A missing credential must stop ingestion."""
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)

    with patch(
        "financial_data_platform.orchestration.ingestion.ingest_daily_market_data"
    ) as mock_ingest:
        with pytest.raises(RuntimeError, match="TWELVE_DATA_API_KEY"):
            ingest_market_symbols(
                raw_base_dir=tmp_path,
                extracted_at=EXTRACTED_AT,
            )

    mock_ingest.assert_not_called()


def test_extraction_error_propagates(tmp_path, monkeypatch):
    """An extraction error must be visible to the orchestrator."""
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "fake-test-key")

    with patch(
        "financial_data_platform.orchestration.ingestion.ingest_daily_market_data",
        side_effect=RuntimeError("Simulated extraction failure"),
    ):
        with pytest.raises(
            RuntimeError,
            match="Simulated extraction failure",
        ):
            ingest_market_symbols(
                raw_base_dir=tmp_path,
                extracted_at=EXTRACTED_AT,
            )


def test_default_selection_is_single_symbol(tmp_path, monkeypatch):
    """The initial configuration must limit accidental API usage."""
    monkeypatch.setenv("TWELVE_DATA_API_KEY", "fake-test-key")

    with patch(
        "financial_data_platform.orchestration.ingestion.ingest_daily_market_data",
        return_value=Path("raw/AAPL.json"),
    ) as mock_ingest:
        summary = ingest_market_symbols(
            raw_base_dir=tmp_path,
            extracted_at=EXTRACTED_AT,
        )

    assert summary["symbols"] == ["AAPL"]
    mock_ingest.assert_called_once()