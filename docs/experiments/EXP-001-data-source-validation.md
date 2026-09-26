# EXP-001 — Financial Data Source Validation

## Objective

Validate the candidate financial data providers using real API requests before selecting the primary data source for the project.

The experiment evaluates whether each candidate can provide the required OHLCV market data, sufficient historical observations, usable response structures, appropriate error handling, and suitable behavior for automated ETL processing.

---

## Date

2026-09-26

---

## Test Assets

- AAPL
- MSFT
- NVDA
- AMZN
- GOOGL

---

## Candidate Providers

1. Alpha Vantage
2. Financial Modeling Prep
3. Twelve Data

---

## Validation Criteria

For each provider, verify:

- Successful API authentication
- Availability of the five selected assets
- Availability of open, high, low, close, and volume data
- Historical data availability
- Response format and structure
- Date/timestamp representation
- Invalid-symbol behavior
- HTTP status codes
- Rate-limit information where observable
- Suitability for automated extraction

---

## Results

### Alpha Vantage

#### Authentication and Response Structure

API-key authentication successfully completed.

The API returned JSON responses containing provider metadata and daily market observations keyed by date.

Observed market-data fields:

- open
- high
- low
- close
- volume

Date representation:

- Each daily observation is identified by a date key.

Response format:

- JSON

#### Historical Observations

| Symbol | Success | OHLCV | Observations | Oldest Date | Newest Date |
|---|---|---|---:|---|---|
| AAPL | Yes | Yes | 100 | 2026-05-05 | 2026-09-25 |
| MSFT | Yes | Yes | 100 | 2026-05-05 | 2026-09-25 |
| NVDA | Yes | Yes | 100 | 2026-05-05 | 2026-09-25 |
| AMZN | Yes | Yes | 100 | 2026-05-05 | 2026-09-25 |
| GOOGL | Yes | Yes | 100 | 2026-05-05 | 2026-09-25 |

All five selected US equity symbols were successfully retrieved and contained the required OHLCV fields.

Each request returned 100 daily observations covering the period from May 5, 2026 through September 25, 2026.

The 100 observations represent trading observations rather than 100 consecutive calendar days.

#### Invalid Symbol Test

Symbol: `THIS_SYMBOL_SHOULD_NOT_EXIST_12345`

HTTP status: `200 OK`

Response behavior: The HTTP request completed successfully, but the response did not contain market time-series data.

Error returned inside JSON: Yes

The response contained an `Error Message` indicating that the API call was invalid.

#### Rate-Limit Information Observed

No rate-limit information was identified in the tested response that was used as part of this experiment.

The experiment did not intentionally exhaust the provider's request allowance because deliberately consuming the available quota was unnecessary for validating the required extraction behavior.

#### Engineering Observation

Alpha Vantage may return HTTP status `200 OK` even when a request does not produce valid market data. Therefore, checking only the HTTP status code is insufficient for determining whether an extraction was successful.

The future extraction component should perform both transport-level and response-level validation. After confirming a successful HTTP response, it should verify that the expected time-series structure is present and check for API-specific error or informational fields before accepting the response as valid raw market data.

This behavior should later be covered by an automated test to ensure that an HTTP `200` response containing an API error is not treated as a successful extraction.

#### ETL Suitability Observation

Alpha Vantage successfully provided the required OHLCV data for all five tested assets, and its JSON response can be parsed programmatically.

However, the tested response contained only 100 daily observations per asset. This provides less historical data for initial backfilling and historical financial-metric calculations than the other providers tested in this experiment.

Provider-specific response validation would also be required because unsuccessful requests may still use HTTP `200 OK`.

---

### Financial Modeling Prep

#### Authentication and Response Structure

API-key authentication successfully completed.

The API returned JSON responses containing historical market observations in a direct collection of records.

Observed market-data fields included:

- symbol
- date
- open
- high
- low
- close
- volume

Date representation:

- Each observation contains a `date` field.

Response format:

- JSON

#### Historical Observations

| Symbol | Success | OHLCV | Observations | Oldest Date | Newest Date |
|---|---|---|---:|---|---|
| AAPL | Yes | Yes | 1255 | 2021-09-27 | 2026-09-25 |
| MSFT | Yes | Yes | 1255 | 2021-09-27 | 2026-09-25 |
| NVDA | Yes | Yes | 1255 | 2021-09-27 | 2026-09-25 |
| AMZN | Yes | Yes | 1255 | 2021-09-27 | 2026-09-25 |
| GOOGL | Yes | Yes | 1255 | 2021-09-27 | 2026-09-25 |

All five selected US equity symbols were successfully retrieved and contained the required OHLCV fields.

Each request returned 1,255 historical observations covering the period from September 27, 2021 through September 25, 2026.

This represents approximately five years of trading history and provides substantially more historical data under the tested access than the 100 observations obtained during the Alpha Vantage experiment.

#### Invalid Symbol Test

Symbol: `THIS_SYMBOL_SHOULD_NOT_EXIST_12345`

HTTP status: `402 Payment Required`

Response behavior: The request was rejected and no market time-series data was returned.

The response indicated that the supplied value for the `symbol` parameter was not available under the current subscription and suggested upgrading the subscription.

#### Rate-Limit Information Observed

No rate-limit information was identified in the tested response that was used as part of this experiment.

The experiment did not intentionally exhaust the provider's request allowance because deliberately consuming the available quota was unnecessary for validating the required extraction behavior.

#### Engineering Observation

Unlike the observed Alpha Vantage behavior, Financial Modeling Prep did not return HTTP `200 OK` for the unsuccessful invalid-symbol request. It returned HTTP status `402 Payment Required`.

However, the response does not clearly distinguish an invalid or nonexistent symbol from a symbol that exists but is unavailable under the current subscription. Therefore, the extraction component should not automatically interpret every `402` response as evidence that an asset does not exist.

The future extractor should distinguish successful responses from authentication, subscription, rate-limit, server, and data-validation failures where the provider makes such distinctions available.

#### ETL Suitability Observation

Financial Modeling Prep successfully provided the required OHLCV data for all five tested assets and returned substantially more historical data than Alpha Vantage in this experiment.

The returned records use a relatively direct structure containing fields such as `symbol`, `date`, `open`, `high`, `low`, `close`, and `volume`. This structure is suitable for automated parsing and normalization within an ETL extraction layer.

The observed `402 Payment Required` behavior also means that the future extraction component would need to distinguish subscription-related responses from other classes of extraction failure.

---

### Twelve Data

#### Authentication and Response Structure

API-key authentication successfully completed.

The API returned JSON responses containing a metadata object, a collection of market observations under `values`, and a response status.

Observed market-data fields:

- datetime
- open
- high
- low
- close
- volume

Date representation:

- Each observation contains a `datetime` field.

Response format:

- JSON

#### Historical Observations

| Symbol | Success | OHLCV | Observations | Oldest Date | Newest Date |
|---|---|---|---:|---|---|
| AAPL | Yes | Yes | 5000 | 2006-11-08 | 2026-09-25 |
| MSFT | Yes | Yes | 5000 | 2006-11-08 | 2026-09-25 |
| NVDA | Yes | Yes | 5000 | 2006-11-08 | 2026-09-25 |
| AMZN | Yes | Yes | 5000 | 2006-11-08 | 2026-09-25 |
| GOOGL | Yes | Yes | 5000 | 2006-11-08 | 2026-09-25 |

All five selected US equity symbols were successfully retrieved and contained the required OHLCV fields.

The tested endpoint successfully returned the requested 5,000 daily observations for each of the five selected assets. The returned period extended from November 8, 2006 through September 25, 2026.

The value of 5,000 represents the requested `outputsize` used during this experiment and should not be interpreted as evidence that 5,000 observations are the maximum historical data available from the provider.

The observed historical depth was substantially larger than the history returned during the Alpha Vantage and Financial Modeling Prep experiments.

#### Invalid Symbol Test

Symbol: `THIS_SYMBOL_SHOULD_NOT_EXIST_12345`

HTTP status: `404 Not Found`

Response behavior: The request was rejected and no market time-series data was returned.

Error returned inside JSON: Yes

The response contained a structured JSON error object with:

- `code`: `404`
- `status`: `error`
- A message indicating that the `symbol` or `figi` parameter was missing or invalid

#### Rate-Limit Information Observed

The response headers exposed API-credit information.

Observed headers included:

- `Api-Credits-Left`
- `Api-Credits-Request`
- `Api-Credits-Used`

During the invalid-symbol request, the response indicated that one API credit was requested and used.

These headers may later be useful for pipeline observability and rate-limit monitoring.

The experiment did not intentionally exhaust the available API credits because deliberately consuming the quota was unnecessary for validating extraction behavior.

#### Engineering Observation

Twelve Data returned both an appropriate HTTP error status and a structured JSON error response for the invalid-symbol test.

This behavior allows an extraction component to identify the failure at the HTTP level while also retaining provider-specific error information for logging and diagnostics.

The separation between response metadata, the `values` collection, and the response status also provides identifiable structures that can be validated before extracted observations are accepted for downstream processing.

The API-credit headers provide additional information that could later be captured as part of pipeline observability.

#### ETL Suitability Observation

Twelve Data successfully provided the required OHLCV data for all five tested assets and returned the largest historical dataset requested during this experiment.

The response structure is suitable for programmatic parsing. Market observations are contained within a clearly identifiable `values` collection, while provider metadata is stored separately.

The combination of structured success responses, structured error responses, explicit HTTP error behavior, and observable API-credit information provides useful signals for implementing automated extraction, validation, logging, and monitoring.

---

## Cross-Provider Comparison

| Criterion | Alpha Vantage | Financial Modeling Prep | Twelve Data |
|---|---|---|---|
| Authentication successful | Yes | Yes | Yes |
| All five assets available | Yes | Yes | Yes |
| OHLCV available | Yes | Yes | Yes |
| JSON response | Yes | Yes | Yes |
| Observations per tested asset | 100 | 1,255 | 5,000 requested and returned |
| Oldest observation | 2026-05-05 | 2021-09-27 | 2006-11-08 |
| Newest observation | 2026-09-25 | 2026-09-25 | 2026-09-25 |
| Invalid-symbol HTTP status | `200 OK` | `402 Payment Required` | `404 Not Found` |
| Invalid-symbol information in response | Yes | Yes | Yes |
| Explicit API usage information observed | No | No | Yes |
| Programmatically parseable | Yes | Yes | Yes |
| Provider-specific error handling required | Yes | Yes | Yes |

---

## Key Engineering Findings

The experiment identified several requirements that should influence the implementation of the future extraction component.

First, HTTP status codes alone cannot be treated as a universal indicator of extraction success. Alpha Vantage returned HTTP `200 OK` for an invalid-symbol request while reporting the failure inside the response body. Therefore, successful extraction must require both acceptable transport-level behavior and validation of the provider-specific response structure.

Second, error semantics differ between providers. Financial Modeling Prep returned `402 Payment Required` for the intentionally invalid symbol, while Twelve Data returned `404 Not Found`. The extraction layer should classify failures using provider-specific handling rather than assuming identical HTTP behavior across APIs.

Third, the providers expose different JSON structures. Alpha Vantage stores observations in a date-keyed time-series object, Financial Modeling Prep returns a direct collection of historical records, and Twelve Data places observations inside a `values` collection alongside separate metadata. This supports using provider-specific parsing followed by normalization into a common internal schema.

A possible canonical representation for downstream processing is:

`symbol`, `date`, `open`, `high`, `low`, `close`, `volume`, `source`, `extracted_at`

This would allow downstream validation, transformation, and loading components to operate independently of the original provider-specific JSON structure.

Finally, the experiment demonstrated significant differences in the amount of historical data returned under the tested access. Historical depth is particularly relevant to this project because the planned business logic includes rolling indicators such as moving averages, volatility, RSI, rolling volume statistics, and drawdown calculations.

---

## Conclusion

All three candidate providers successfully returned the required OHLCV data for the five selected test assets: AAPL, MSFT, NVDA, AMZN, and GOOGL. Therefore, all three demonstrated basic technical compatibility with the project's market-data requirements.

The experiment also identified substantial differences between the providers.

Alpha Vantage returned 100 daily observations per tested asset, covering May 5, 2026 through September 25, 2026. Financial Modeling Prep returned 1,255 observations per asset, covering September 27, 2021 through September 25, 2026. Twelve Data returned the requested 5,000 observations per asset, covering November 8, 2006 through September 25, 2026.

Error handling also differed. Alpha Vantage returned HTTP `200 OK` while representing the invalid-symbol failure inside the JSON response. Financial Modeling Prep returned HTTP `402 Payment Required` with a subscription-related response. Twelve Data returned HTTP `404 Not Found` together with a structured JSON error object.

These results demonstrate that provider-specific extraction and validation logic is necessary. The extraction component should validate HTTP behavior, provider-specific error fields, and expected response structures before accepting data as a successful extraction.

The experiment does not make the final provider selection by itself. The final architectural decision should combine these measured results with additional considerations including free-tier request limits, licensing and attribution requirements, historical-data restrictions, incremental extraction capabilities, reproducibility, and suitability for use within the project's public portfolio and dashboard.

The selected provider and the rationale for that selection will be documented separately in the project's data-source evaluation and Architecture Decision Record.