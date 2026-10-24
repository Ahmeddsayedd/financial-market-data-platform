# Market Data Quality Contracts

## Purpose

Define deterministic validation and error-handling rules for daily OHLCV market observations in the Financial Market Data Platform.

These contracts apply to Twelve Data parsing, canonical market-data validation, Raw-to-Silver processing, and quarantine storage.

## 1. Canonical record

Each `MarketDataRecord` represents one daily market observation and contains:

| Field | Expected representation |
|---|---|
| `symbol` | Nonempty provider symbol |
| `observation_date` | Valid calendar date |
| `open`, `high`, `low`, `close` | Decimal prices |
| `volume` | Integer trading volume |
| `source` | Data provider identifier |
| `extracted_at` | Timezone-aware extraction timestamp |

The provider parser validates the response structure, symbol, observation dates, required fields, numeric conversion, and extraction timestamp.

## 2. Financial integrity rules

- All OHLC prices must be finite and strictly positive.
- The daily high must not be below the daily low.
- Open and close prices must lie within the inclusive low-to-high range.
- Trading volume must be nonnegative; zero is allowed.
- NaN and positive or negative infinity are invalid prices.

Violations are represented using stable codes such as `NON_POSITIVE_OPEN`, `NON_FINITE_CLOSE`, `HIGH_BELOW_LOW`, `OPEN_OUTSIDE_RANGE`, `CLOSE_OUTSIDE_RANGE`, and `NEGATIVE_VOLUME`.

## 3. Provider input rules

- A time-series response must be a JSON object containing valid `meta` information and a nonempty `values` list.
- Every observation must have the required date, OHLC, and volume fields.
- Observation dates must use valid `YYYY-MM-DD` calendar dates.
- Volume must be an integer or an integer string, without fractional truncation.
- Negative integer volumes may be parsed but fail the financial-quality contract.
- Repeated observation dates within one provider response cause a parsing error.
- Missing or malformed provider fields cause `TwelveDataParseError`.

## 4. Rejection and quarantine behavior

**Structural parsing errors:** The Raw-processing operation fails before writing Silver or quarantine output for that batch.

**Financial validation errors:** Individual invalid observations are excluded from Silver and written to quarantine JSON with their violation codes. Other valid observations in the same batch remain eligible for Silver storage.

Raw source responses remain available for diagnosis and replay.

## 5. Duplicate handling

A provider response containing multiple observations for the same date is rejected as ambiguous. The parser does not silently choose the first or last observation.

Reprocessing an identical preserved Raw file is covered by existing idempotency tests.

## 6. Test strategy

Quality tests use deterministic local fixtures and temporary storage paths. They do not require live API requests, API credentials, or PostgreSQL writes.

Coverage includes OHLC boundary values, non-finite prices, invalid volumes, missing fields, invalid dates, duplicate dates, mixed valid/invalid batches, and quarantine persistence.

## 7. Current limitations

The canonical dataclass itself does not enforce all runtime types. The documented guarantees rely on provider parsing and explicit market-data validation before persistence.

Strict symbol-format policies, cross-provider reconciliation, and historical anomaly detection are outside the current issue.