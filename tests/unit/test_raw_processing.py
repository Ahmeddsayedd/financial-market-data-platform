import json
import pytest
from datetime import date, datetime, timezone
from decimal import Decimal
from financial_data_platform.providers.twelve_data.parser import (
    TwelveDataParseError,
)

import pyarrow.parquet as pq

from financial_data_platform.processing.raw_market_data import (
    process_raw_market_data,
)
from financial_data_platform.storage.quarantine import QuarantineWriter
from financial_data_platform.storage.silver import SilverWriter


def test_processes_valid_raw_observation_into_silver(tmp_path):
    raw_path = tmp_path / "raw" / "aapl.json"
    raw_path.parent.mkdir(parents=True)

    payload = {
        "meta": {"symbol": "AAPL"},
        "values": [
            {
                "datetime": "2026-10-05",
                "open": "250.00",
                "high": "255.00",
                "low": "249.00",
                "close": "254.00",
                "volume": "1000000",
            }
        ],
    }

    raw_path.write_text(json.dumps(payload), encoding="utf-8")

    silver_writer = SilverWriter(tmp_path / "silver")
    quarantine_writer = QuarantineWriter(tmp_path / "quarantine")

    result = process_raw_market_data(
        raw_path=raw_path,
        silver_writer=silver_writer,
        quarantine_writer=quarantine_writer,
        extracted_at=datetime(
            2026, 10, 6, 18, 30, 45, tzinfo=timezone.utc
        ),
        detected_at=datetime(
            2026, 10, 6, 18, 31, tzinfo=timezone.utc
        ),
    )

    expected_silver_path = (
        tmp_path
        / "silver"
        / "symbol=AAPL"
        / "year=2026"
        / "data.parquet"
    )

    assert result.total_records == 1
    assert result.valid_count == 1
    assert result.invalid_count == 0
    assert result.silver_paths == [expected_silver_path]
    assert result.quarantine_paths == []

    table = pq.ParquetFile(expected_silver_path).read()

    assert table.num_rows == 1
    assert table.column("observation_date").to_pylist() == [
        date(2026, 10, 5)
    ]
    assert table.column("close").to_pylist() == [
        Decimal("254.00000000")
    ]

    assert list((tmp_path / "quarantine").rglob("*.json")) == []



def test_processes_mixed_valid_and_invalid_observations(tmp_path):
    raw_path = tmp_path / "raw" / "aapl.json"
    raw_path.parent.mkdir(parents=True)

    payload = {
        "meta": {"symbol": "AAPL"},
        "values": [
            {
                "datetime": "2026-10-05",
                "open": "250.00",
                "high": "255.00",
                "low": "249.00",
                "close": "254.00",
                "volume": "1000000",
            },
            {
                "datetime": "2026-10-06",
                "open": "250.00",
                "high": "255.00",
                "low": "249.00",
                "close": "254.00",
                "volume": "-100",
            },
        ],
    }

    raw_path.write_text(json.dumps(payload), encoding="utf-8")

    result = process_raw_market_data(
        raw_path=raw_path,
        silver_writer=SilverWriter(tmp_path / "silver"),
        quarantine_writer=QuarantineWriter(tmp_path / "quarantine"),
        extracted_at=datetime(2026, 10, 7, tzinfo=timezone.utc),
        detected_at=datetime(2026, 10, 7, 1, tzinfo=timezone.utc),
    )

    assert result.total_records == 2
    assert result.valid_count == 1
    assert result.invalid_count == 1
    assert len(result.silver_paths) == 1
    assert len(result.quarantine_paths) == 1

    silver_table = pq.ParquetFile(result.silver_paths[0]).read()
    assert silver_table.num_rows == 1
    assert silver_table.column("observation_date").to_pylist() == [
        date(2026, 10, 5)
    ]

    quarantine_path = result.quarantine_paths[0]
    assert quarantine_path.exists()

    quarantined = json.loads(quarantine_path.read_text(encoding="utf-8"))

    assert quarantined["record"]["symbol"] == "AAPL"
    assert quarantined["record"]["volume"] == -100
    assert quarantined["violations"]



def test_processes_invalid_only_batch_without_writing_silver(tmp_path):
    raw_path = tmp_path / "raw" / "aapl.json"
    raw_path.parent.mkdir(parents=True)

    payload = {
        "meta": {"symbol": "AAPL"},
        "values": [
            {
                "datetime": "2026-10-05",
                "open": "250.00",
                "high": "255.00",
                "low": "249.00",
                "close": "254.00",
                "volume": "-100",
            }
        ],
    }

    raw_path.write_text(json.dumps(payload), encoding="utf-8")

    result = process_raw_market_data(
        raw_path=raw_path,
        silver_writer=SilverWriter(tmp_path / "silver"),
        quarantine_writer=QuarantineWriter(tmp_path / "quarantine"),
        extracted_at=datetime(2026, 10, 7, tzinfo=timezone.utc),
        detected_at=datetime(2026, 10, 7, 1, tzinfo=timezone.utc),
    )

    assert result.total_records == 1
    assert result.valid_count == 0
    assert result.invalid_count == 1

    assert result.silver_paths == []
    assert len(result.quarantine_paths) == 1
    assert result.quarantine_paths[0].exists()

    assert list((tmp_path / "silver").rglob("*.parquet")) == []
    assert len(list((tmp_path / "quarantine").rglob("*.json"))) == 1



def test_rejects_malformed_raw_json_without_writing_outputs(tmp_path):
    raw_path = tmp_path / "raw" / "aapl.json"
    raw_path.parent.mkdir(parents=True)

    raw_path.write_text(
        '{"meta": {"symbol": "AAPL"}, "values": [',
        encoding="utf-8",
    )

    with pytest.raises(json.JSONDecodeError):
        process_raw_market_data(
            raw_path=raw_path,
            silver_writer=SilverWriter(tmp_path / "silver"),
            quarantine_writer=QuarantineWriter(tmp_path / "quarantine"),
            extracted_at=datetime(2026, 10, 7, tzinfo=timezone.utc),
            detected_at=datetime(2026, 10, 7, 1, tzinfo=timezone.utc),
        )

    assert list((tmp_path / "silver").rglob("*.parquet")) == []
    assert list((tmp_path / "quarantine").rglob("*.json")) == []



def test_rejects_structurally_invalid_response_without_writing_outputs(
    tmp_path,
):
    raw_path = tmp_path / "raw" / "aapl.json"
    raw_path.parent.mkdir(parents=True)

    payload = {
        "meta": {"symbol": "AAPL"},
        "values": "not-a-list",
    }

    raw_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(TwelveDataParseError):
        process_raw_market_data(
            raw_path=raw_path,
            silver_writer=SilverWriter(tmp_path / "silver"),
            quarantine_writer=QuarantineWriter(tmp_path / "quarantine"),
            extracted_at=datetime(2026, 10, 7, tzinfo=timezone.utc),
            detected_at=datetime(2026, 10, 7, 1, tzinfo=timezone.utc),
        )

    assert list((tmp_path / "silver").rglob("*.parquet")) == []
    assert list((tmp_path / "quarantine").rglob("*.json")) == []



def test_rejects_empty_observations_without_writing_outputs(tmp_path):
    raw_path = tmp_path / "raw" / "aapl.json"
    raw_path.parent.mkdir(parents=True)

    payload = {
        "meta": {"symbol": "AAPL"},
        "values": [],
    }

    raw_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(
        TwelveDataParseError,
        match="no observations",
    ):
        process_raw_market_data(
            raw_path=raw_path,
            silver_writer=SilverWriter(tmp_path / "silver"),
            quarantine_writer=QuarantineWriter(tmp_path / "quarantine"),
            extracted_at=datetime(2026, 10, 7, tzinfo=timezone.utc),
            detected_at=datetime(2026, 10, 7, 1, tzinfo=timezone.utc),
        )

    assert list((tmp_path / "silver").rglob("*.parquet")) == []
    assert list((tmp_path / "quarantine").rglob("*.json")) == []



def test_rejects_missing_raw_file_without_writing_outputs(tmp_path):
    raw_path = tmp_path / "raw" / "missing.json"

    assert not raw_path.exists()

    with pytest.raises(FileNotFoundError):
        process_raw_market_data(
            raw_path=raw_path,
            silver_writer=SilverWriter(tmp_path / "silver"),
            quarantine_writer=QuarantineWriter(tmp_path / "quarantine"),
            extracted_at=datetime(2026, 10, 7, tzinfo=timezone.utc),
            detected_at=datetime(2026, 10, 7, 1, tzinfo=timezone.utc),
        )

    assert list((tmp_path / "silver").rglob("*.parquet")) == []
    assert list((tmp_path / "quarantine").rglob("*.json")) == []



def test_reprocessing_same_raw_file_does_not_duplicate_silver_records(
    tmp_path,
):
    raw_path = tmp_path / "raw" / "aapl.json"
    raw_path.parent.mkdir(parents=True)

    payload = {
        "meta": {"symbol": "AAPL"},
        "values": [
            {
                "datetime": "2026-10-05",
                "open": "250.00",
                "high": "255.00",
                "low": "249.00",
                "close": "254.00",
                "volume": "1000000",
            }
        ],
    }

    raw_path.write_text(json.dumps(payload), encoding="utf-8")

    silver_writer = SilverWriter(tmp_path / "silver")
    quarantine_writer = QuarantineWriter(tmp_path / "quarantine")

    extracted_at = datetime(2026, 10, 7, tzinfo=timezone.utc)
    detected_at = datetime(2026, 10, 7, 1, tzinfo=timezone.utc)

    first_result = process_raw_market_data(
        raw_path=raw_path,
        silver_writer=silver_writer,
        quarantine_writer=quarantine_writer,
        extracted_at=extracted_at,
        detected_at=detected_at,
    )

    second_result = process_raw_market_data(
        raw_path=raw_path,
        silver_writer=silver_writer,
        quarantine_writer=quarantine_writer,
        extracted_at=extracted_at,
        detected_at=detected_at,
    )

    assert first_result.silver_paths == second_result.silver_paths
    assert first_result.valid_count == 1
    assert second_result.valid_count == 1

    silver_path = first_result.silver_paths[0]
    table = pq.ParquetFile(silver_path).read()

    assert table.num_rows == 1
    assert table.column("observation_date").to_pylist() == [
        date(2026, 10, 5)
    ]

    assert len(list((tmp_path / "silver").rglob("*.parquet"))) == 1
    assert list((tmp_path / "quarantine").rglob("*.json")) == []



def test_reprocessing_invalid_raw_file_does_not_duplicate_quarantine(
    tmp_path,
):
    raw_path = tmp_path / "raw" / "aapl.json"
    raw_path.parent.mkdir(parents=True)

    payload = {
        "meta": {"symbol": "AAPL"},
        "values": [
            {
                "datetime": "2026-10-05",
                "open": "250.00",
                "high": "255.00",
                "low": "249.00",
                "close": "254.00",
                "volume": "-100",
            }
        ],
    }

    raw_path.write_text(json.dumps(payload), encoding="utf-8")

    silver_writer = SilverWriter(tmp_path / "silver")
    quarantine_writer = QuarantineWriter(tmp_path / "quarantine")

    extracted_at = datetime(2026, 10, 7, tzinfo=timezone.utc)
    detected_at = datetime(2026, 10, 7, 1, tzinfo=timezone.utc)

    first_result = process_raw_market_data(
        raw_path=raw_path,
        silver_writer=silver_writer,
        quarantine_writer=quarantine_writer,
        extracted_at=extracted_at,
        detected_at=detected_at,
    )

    second_result = process_raw_market_data(
        raw_path=raw_path,
        silver_writer=silver_writer,
        quarantine_writer=quarantine_writer,
        extracted_at=extracted_at,
        detected_at=detected_at,
    )

    assert first_result.valid_count == 0
    assert second_result.valid_count == 0
    assert first_result.invalid_count == 1
    assert second_result.invalid_count == 1

    assert first_result.quarantine_paths == second_result.quarantine_paths
    assert len(first_result.quarantine_paths) == 1

    quarantine_files = list(
        (tmp_path / "quarantine").rglob("*.json")
    )

    assert len(quarantine_files) == 1
    assert quarantine_files[0] == first_result.quarantine_paths[0]

    assert list((tmp_path / "silver").rglob("*.parquet")) == []