import json
import pytest
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

from financial_data_platform.models.market_data import MarketDataRecord
from financial_data_platform.storage.quarantine import QuarantineWriter
from financial_data_platform.validation.market_data import (
    InvalidMarketDataRecord,
    ValidationViolation,
)


def test_quarantine_writer_persists_invalid_record(tmp_path):
    invalid_record = InvalidMarketDataRecord(
        record=MarketDataRecord(
            symbol="AAPL",
            observation_date=date(2026, 10, 5),
            open=Decimal("250.00"),
            high=Decimal("255.00"),
            low=Decimal("249.00"),
            close=Decimal("254.00"),
            volume=-1,
            source="twelve_data",
            extracted_at=datetime(
                2026,
                10,
                6,
                18,
                30,
                45,
                tzinfo=timezone.utc,
            ),
        ),
        violations=[
            ValidationViolation(
                code="NEGATIVE_VOLUME",
                field="volume",
                message="Volume must not be negative.",
            )
        ],
    )

    writer = QuarantineWriter(tmp_path)

    path = writer.write(
        invalid_record,
        detected_at=datetime(
            2026,
            10,
            6,
            18,
            31,
            tzinfo=timezone.utc,
        ),
    )

    assert path.exists()
    assert path.suffix == ".json"


def test_quarantine_writer_preserves_record_violations_and_detection_metadata(
    tmp_path,
):
    invalid_record = InvalidMarketDataRecord(
        record=MarketDataRecord(
            symbol="AAPL",
            observation_date=date(2026, 10, 5),
            open=Decimal("250.00"),
            high=Decimal("255.00"),
            low=Decimal("249.00"),
            close=Decimal("254.00"),
            volume=-1,
            source="twelve_data",
            extracted_at=datetime(
                2026,
                10,
                6,
                18,
                30,
                45,
                tzinfo=timezone.utc,
            ),
        ),
        violations=[
            ValidationViolation(
                code="NEGATIVE_VOLUME",
                field="volume",
                message="Volume must not be negative.",
            )
        ],
    )
    detected_at = datetime(
        2026,
        10,
        6,
        18,
        31,
        tzinfo=timezone.utc,
    )

    writer = QuarantineWriter(tmp_path)

    path = writer.write(
        invalid_record,
        detected_at=detected_at,
    )

    with path.open(encoding="utf-8") as file:
        payload = json.load(file)

    assert payload == {
        "record": {
            "symbol": "AAPL",
            "observation_date": "2026-10-05",
            "open": "250.00",
            "high": "255.00",
            "low": "249.00",
            "close": "254.00",
            "volume": -1,
            "source": "twelve_data",
            "extracted_at": "2026-10-06T18:30:45+00:00",
        },
        "violations": [
            {
                "code": "NEGATIVE_VOLUME",
                "field": "volume",
                "message": "Volume must not be negative.",
            }
        ],
        "detected_at": "2026-10-06T18:31:00+00:00",
    }



def test_quarantine_writer_rejects_naive_detected_at(tmp_path):
    invalid_record = InvalidMarketDataRecord(
        record=MarketDataRecord(
            symbol="AAPL",
            observation_date=date(2026, 10, 5),
            open=Decimal("250.00"),
            high=Decimal("255.00"),
            low=Decimal("249.00"),
            close=Decimal("254.00"),
            volume=-1,
            source="twelve_data",
            extracted_at=datetime(
                2026,
                10,
                6,
                18,
                30,
                45,
                tzinfo=timezone.utc,
            ),
        ),
        violations=[
            ValidationViolation(
                code="NEGATIVE_VOLUME",
                field="volume",
                message="Volume must not be negative.",
            )
        ],
    )

    naive_detected_at = datetime(2026, 10, 6, 18, 31)

    writer = QuarantineWriter(tmp_path)

    with pytest.raises(
        ValueError,
        match="detected_at must be timezone-aware",
    ):
        writer.write(
            invalid_record,
            detected_at=naive_detected_at,
        )



def test_quarantine_writer_uses_deterministic_path(tmp_path):
    invalid_record = InvalidMarketDataRecord(
        record=MarketDataRecord(
            symbol="AAPL",
            observation_date=date(2026, 10, 5),
            open=Decimal("250.00"),
            high=Decimal("255.00"),
            low=Decimal("249.00"),
            close=Decimal("254.00"),
            volume=-1,
            source="twelve_data",
            extracted_at=datetime(
                2026,
                10,
                6,
                18,
                30,
                45,
                tzinfo=timezone.utc,
            ),
        ),
        violations=[
            ValidationViolation(
                code="NEGATIVE_VOLUME",
                field="volume",
                message="Volume must not be negative.",
            )
        ],
    )

    writer = QuarantineWriter(tmp_path)

    path = writer.write(
        invalid_record,
        detected_at=datetime(
            2026,
            10,
            6,
            18,
            31,
            tzinfo=timezone.utc,
        ),
    )

    expected_path = (
        tmp_path
        / "twelve_data"
        / "AAPL"
        / "2026"
        / "10"
        / "06"
        / "20261006T183100000000Z_2026-10-05.json"
    )

    assert path == expected_path



def test_quarantine_writer_normalizes_detected_at_to_utc(tmp_path):
    invalid_record = InvalidMarketDataRecord(
        record=MarketDataRecord(
            symbol="AAPL",
            observation_date=date(2026, 10, 5),
            open=Decimal("250.00"),
            high=Decimal("255.00"),
            low=Decimal("249.00"),
            close=Decimal("254.00"),
            volume=-1,
            source="twelve_data",
            extracted_at=datetime(
                2026,
                10,
                6,
                18,
                30,
                45,
                tzinfo=timezone.utc,
            ),
        ),
        violations=[
            ValidationViolation(
                code="NEGATIVE_VOLUME",
                field="volume",
                message="Volume must not be negative.",
            )
        ],
    )

    writer = QuarantineWriter(tmp_path)

    utc_path = writer.write(
        invalid_record,
        detected_at=datetime(
            2026,
            10,
            6,
            18,
            31,
            tzinfo=timezone.utc,
        ),
    )

    utc_plus_two = timezone(timedelta(hours=2))

    offset_path = writer.write(
        invalid_record,
        detected_at=datetime(
            2026,
            10,
            6,
            20,
            31,
            tzinfo=utc_plus_two,
        ),
    )

    assert offset_path == utc_path



@pytest.mark.parametrize(
    ("source", "symbol"),
    [
        ("../outside", "AAPL"),
        ("twelve/data", "AAPL"),
        ("twelve\\data", "AAPL"),
        ("twelve_data", "../AAPL"),
        ("twelve_data", "AA/PL"),
        ("twelve_data", "AA\\PL"),
    ],
)
def test_quarantine_writer_rejects_unsafe_path_components(
    tmp_path,
    source,
    symbol,
):
    invalid_record = InvalidMarketDataRecord(
        record=MarketDataRecord(
            symbol=symbol,
            observation_date=date(2026, 10, 5),
            open=Decimal("250.00"),
            high=Decimal("255.00"),
            low=Decimal("249.00"),
            close=Decimal("254.00"),
            volume=-1,
            source=source,
            extracted_at=datetime(
                2026,
                10,
                6,
                18,
                30,
                45,
                tzinfo=timezone.utc,
            ),
        ),
        violations=[
            ValidationViolation(
                code="NEGATIVE_VOLUME",
                field="volume",
                message="Volume must not be negative.",
            )
        ],
    )

    writer = QuarantineWriter(tmp_path)

    with pytest.raises(
        ValueError,
        match="source and symbol must be safe path components",
    ):
        writer.write(
            invalid_record,
            detected_at=datetime(
                2026,
                10,
                6,
                18,
                31,
                tzinfo=timezone.utc,
            ),
        )



def test_quarantine_writer_is_idempotent_for_same_record_and_detected_at(
    tmp_path,
):
    invalid_record = InvalidMarketDataRecord(
        record=MarketDataRecord(
            symbol="AAPL",
            observation_date=date(2026, 10, 5),
            open=Decimal("250.00"),
            high=Decimal("255.00"),
            low=Decimal("249.00"),
            close=Decimal("254.00"),
            volume=-1,
            source="twelve_data",
            extracted_at=datetime(
                2026,
                10,
                6,
                18,
                30,
                45,
                tzinfo=timezone.utc,
            ),
        ),
        violations=[
            ValidationViolation(
                code="NEGATIVE_VOLUME",
                field="volume",
                message="Volume must not be negative.",
            )
        ],
    )
    detected_at = datetime(
        2026,
        10,
        6,
        18,
        31,
        tzinfo=timezone.utc,
    )

    writer = QuarantineWriter(tmp_path)

    first_path = writer.write(
        invalid_record,
        detected_at=detected_at,
    )
    second_path = writer.write(
        invalid_record,
        detected_at=detected_at,
    )

    assert first_path == second_path

    with second_path.open(encoding="utf-8") as file:
        payload = json.load(file)

    assert payload["record"]["symbol"] == "AAPL"
    assert payload["record"]["observation_date"] == "2026-10-05"
    assert payload["violations"][0]["code"] == "NEGATIVE_VOLUME"



def test_quarantine_writer_uses_distinct_paths_for_different_observations(
    tmp_path,
):
    detected_at = datetime(
        2026,
        10,
        6,
        18,
        31,
        tzinfo=timezone.utc,
    )

    first_record = InvalidMarketDataRecord(
        record=MarketDataRecord(
            symbol="AAPL",
            observation_date=date(2026, 10, 4),
            open=Decimal("250.00"),
            high=Decimal("255.00"),
            low=Decimal("249.00"),
            close=Decimal("254.00"),
            volume=-1,
            source="twelve_data",
            extracted_at=datetime(
                2026,
                10,
                6,
                18,
                30,
                45,
                tzinfo=timezone.utc,
            ),
        ),
        violations=[
            ValidationViolation(
                code="NEGATIVE_VOLUME",
                field="volume",
                message="Volume must not be negative.",
            )
        ],
    )

    second_record = InvalidMarketDataRecord(
        record=MarketDataRecord(
            symbol="AAPL",
            observation_date=date(2026, 10, 5),
            open=Decimal("250.00"),
            high=Decimal("255.00"),
            low=Decimal("249.00"),
            close=Decimal("254.00"),
            volume=-1,
            source="twelve_data",
            extracted_at=datetime(
                2026,
                10,
                6,
                18,
                30,
                45,
                tzinfo=timezone.utc,
            ),
        ),
        violations=[
            ValidationViolation(
                code="NEGATIVE_VOLUME",
                field="volume",
                message="Volume must not be negative.",
            )
        ],
    )

    writer = QuarantineWriter(tmp_path)

    first_path = writer.write(
        first_record,
        detected_at=detected_at,
    )
    second_path = writer.write(
        second_record,
        detected_at=detected_at,
    )

    assert first_path != second_path
    assert first_path.exists()
    assert second_path.exists()