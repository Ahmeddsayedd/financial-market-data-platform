from dataclasses import dataclass

from financial_data_platform.models.market_data import MarketDataRecord

@dataclass(frozen=True)
class ValidationViolation:
    """Describe one data-quality violation."""

    code: str
    field: str
    message: str


@dataclass(frozen=True)
class InvalidMarketDataRecord:
    """Associate an invalid record with its data-quality violations."""

    record: MarketDataRecord
    violations: list[ValidationViolation]


@dataclass(frozen=True)
class BatchValidationResult:
    """Separate valid and invalid records after data-quality validation."""

    valid_records: list[MarketDataRecord]
    invalid_records: list[InvalidMarketDataRecord]


def validate_market_data_record(
    record: MarketDataRecord,
) -> list[ValidationViolation]:
    """Return data-quality violations for a canonical market-data record."""
    violations: list[ValidationViolation] = []

    price_fields = {
        "open": record.open,
        "high": record.high,
        "low": record.low,
        "close": record.close,
    }

    for field, value in price_fields.items():
        if value <= 0:
            violations.append(
                ValidationViolation(
                    code=f"NON_POSITIVE_{field.upper()}",
                    field=field,
                    message=f"{field.capitalize()} price must be positive.",
                )
            )

    if record.volume < 0:
        violations.append(
            ValidationViolation(
                code="NEGATIVE_VOLUME",
                field="volume",
                message="Volume must not be negative.",
            )
        )


    if record.high < record.low:
        violations.append(
            ValidationViolation(
                code="HIGH_BELOW_LOW",
                field="high",
                message="High price must not be below low price.",
            )
        )

    if record.low <= record.high and not (
        record.low <= record.open <= record.high
    ):
        violations.append(
            ValidationViolation(
                code="OPEN_OUTSIDE_RANGE",
                field="open",
                message="Open price must be between low and high prices.",
            )
        )



    if record.low <= record.high and not (
        record.low <= record.close <= record.high
    ):
        violations.append(
            ValidationViolation(
                code="CLOSE_OUTSIDE_RANGE",
                field="close",
                message="Close price must be between low and high prices.",
            )
        )


    return violations


def partition_market_data_records(
    records: list[MarketDataRecord],
) -> BatchValidationResult:
    """Partition canonical records into valid and invalid groups."""
    valid_records: list[MarketDataRecord] = []
    invalid_records: list[InvalidMarketDataRecord] = []

    for record in records:
        violations = validate_market_data_record(record)

        if violations:
            invalid_records.append(
                InvalidMarketDataRecord(
                    record=record,
                    violations=violations,
                )
            )
        else:
            valid_records.append(record)

    return BatchValidationResult(
        valid_records=valid_records,
        invalid_records=invalid_records,
    )