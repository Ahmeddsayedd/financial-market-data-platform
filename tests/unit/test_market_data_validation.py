import pytest
from datetime import date, datetime, timezone
from decimal import Decimal
from financial_data_platform.models.market_data import MarketDataRecord
from financial_data_platform.validation.market_data import (
    ValidationViolation,
    partition_market_data_records,
    validate_market_data_record,
)


def test_valid_market_data_record_has_no_violations():
    record = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 5),
        open=Decimal("250.00"),
        high=Decimal("255.00"),
        low=Decimal("249.00"),
        close=Decimal("254.00"),
        volume=50_000_000,
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
    )

    violations = validate_market_data_record(record)

    assert violations == []



@pytest.mark.parametrize(
    ("field", "expected_code", "expected_message"),
    [
        ("open", "NON_POSITIVE_OPEN", "Open price must be positive."),
        ("high", "NON_POSITIVE_HIGH", "High price must be positive."),
        ("low", "NON_POSITIVE_LOW", "Low price must be positive."),
        ("close", "NON_POSITIVE_CLOSE", "Close price must be positive."),
    ],
)
def test_non_positive_price_produces_violation(
    field,
    expected_code,
    expected_message,
):
    record_values = {
        "open": Decimal("250.00"),
        "high": Decimal("255.00"),
        "low": Decimal("249.00"),
        "close": Decimal("254.00"),
    }
    record_values[field] = Decimal("0")

    record = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 5),
        open=record_values["open"],
        high=record_values["high"],
        low=record_values["low"],
        close=record_values["close"],
        volume=50_000_000,
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
    )

    violations = validate_market_data_record(record)

    assert ValidationViolation(
        code=expected_code,
        field=field,
        message=expected_message,
    ) in violations



def test_zero_volume_is_valid():
    record = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 5),
        open=Decimal("250.00"),
        high=Decimal("255.00"),
        low=Decimal("249.00"),
        close=Decimal("254.00"),
        volume=0,
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
    )

    violations = validate_market_data_record(record)

    assert violations == []


def test_negative_volume_produces_violation():
    record = MarketDataRecord(
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
    )

    violations = validate_market_data_record(record)

    assert violations == [
        ValidationViolation(
            code="NEGATIVE_VOLUME",
            field="volume",
            message="Volume must not be negative.",
        )
    ]



def test_high_below_low_produces_violation():
    record = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 5),
        open=Decimal("252.00"),
        high=Decimal("249.00"),
        low=Decimal("250.00"),
        close=Decimal("251.00"),
        volume=50_000_000,
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
    )

    violations = validate_market_data_record(record)

    assert ValidationViolation(
        code="HIGH_BELOW_LOW",
        field="high",
        message="High price must not be below low price.",
    ) in violations


@pytest.mark.parametrize(
    "open_price",
    [
        Decimal("248.99"),
        Decimal("255.01"),
    ],
)
def test_open_outside_low_high_range_produces_violation(open_price):
    record = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 5),
        open=open_price,
        high=Decimal("255.00"),
        low=Decimal("249.00"),
        close=Decimal("254.00"),
        volume=50_000_000,
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
    )

    violations = validate_market_data_record(record)

    assert ValidationViolation(
        code="OPEN_OUTSIDE_RANGE",
        field="open",
        message="Open price must be between low and high prices.",
    ) in violations



@pytest.mark.parametrize(
    "open_price",
    [
        Decimal("249.00"),  # exactly low
        Decimal("255.00"),  # exactly high
    ],
)
def test_open_at_low_or_high_boundary_is_valid(open_price):
    record = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 5),
        open=open_price,
        high=Decimal("255.00"),
        low=Decimal("249.00"),
        close=Decimal("254.00"),
        volume=50_000_000,
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
    )

    violations = validate_market_data_record(record)

    assert violations == []



@pytest.mark.parametrize(
    "close_price",
    [
        Decimal("248.99"),
        Decimal("255.01"),
    ],
)
def test_close_outside_low_high_range_produces_violation(close_price):
    record = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 5),
        open=Decimal("250.00"),
        high=Decimal("255.00"),
        low=Decimal("249.00"),
        close=close_price,
        volume=50_000_000,
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
    )

    violations = validate_market_data_record(record)

    assert ValidationViolation(
        code="CLOSE_OUTSIDE_RANGE",
        field="close",
        message="Close price must be between low and high prices.",
    ) in violations



@pytest.mark.parametrize(
    "close_price",
    [
        Decimal("249.00"),  # exactly low
        Decimal("255.00"),  # exactly high
    ],
)
def test_close_at_low_or_high_boundary_is_valid(close_price):
    record = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 5),
        open=Decimal("250.00"),
        high=Decimal("255.00"),
        low=Decimal("249.00"),
        close=close_price,
        volume=50_000_000,
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
    )

    violations = validate_market_data_record(record)

    assert violations == []


def test_record_can_produce_multiple_violations():
    record = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 5),
        open=Decimal("0"),
        high=Decimal("255.00"),
        low=Decimal("249.00"),
        close=Decimal("-1"),
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
    )

    violations = validate_market_data_record(record)

    assert violations == [
        ValidationViolation(
            code="NON_POSITIVE_OPEN",
            field="open",
            message="Open price must be positive.",
        ),
        ValidationViolation(
            code="NON_POSITIVE_CLOSE",
            field="close",
            message="Close price must be positive.",
        ),
        ValidationViolation(
            code="NEGATIVE_VOLUME",
            field="volume",
            message="Volume must not be negative.",
        ),
        ValidationViolation(
            code="OPEN_OUTSIDE_RANGE",
            field="open",
            message="Open price must be between low and high prices.",
        ),
        ValidationViolation(
            code="CLOSE_OUTSIDE_RANGE",
            field="close",
            message="Close price must be between low and high prices.",
        ),
    ]



def test_partition_records_separates_valid_and_invalid_records():
    valid_record = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 5),
        open=Decimal("250.00"),
        high=Decimal("255.00"),
        low=Decimal("249.00"),
        close=Decimal("254.00"),
        volume=50_000_000,
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
    )

    invalid_record = MarketDataRecord(
        symbol="MSFT",
        observation_date=date(2026, 10, 5),
        open=Decimal("500.00"),
        high=Decimal("510.00"),
        low=Decimal("490.00"),
        close=Decimal("505.00"),
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
    )

    result = partition_market_data_records(
        [valid_record, invalid_record]
    )

    assert result.valid_records == [valid_record]
    assert len(result.invalid_records) == 1
    assert result.invalid_records[0].record == invalid_record
    assert result.invalid_records[0].violations == [
        ValidationViolation(
            code="NEGATIVE_VOLUME",
            field="volume",
            message="Volume must not be negative.",
        )
    ]



def test_partition_empty_batch_returns_empty_result():
    result = partition_market_data_records([])

    assert result.valid_records == []
    assert result.invalid_records == []