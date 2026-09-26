# Financial Data Source Evaluation

## 1. Purpose

The financial data pipeline requires an external source of market data. Before implementation, candidate data providers are evaluated to ensure that the selected source satisfies the functional requirements and the zero-cost constraint of the project.

The selected source should provide sufficient raw market data for the project to calculate its own financial metrics rather than relying on precomputed indicators from the provider.

The evaluation combines information from official provider documentation with the empirical results recorded in `EXP-001 — Financial Data Source Validation`.

---

## 2. Required Data

The minimum required market data fields are:

- asset symbol
- observation date or timestamp
- open price
- high price
- low price
- close price
- trading volume

The source should also provide sufficient historical observations to support rolling calculations, historical reprocessing, and performance experiments.

The project primarily requires scheduled daily market-data ingestion rather than high-frequency trading data. Therefore, reliable end-of-day or daily OHLCV data is sufficient for the core implementation.

---

## 3. Evaluation Criteria

The following criteria are used:

1. Zero-cost access
2. OHLCV availability
3. Historical data availability
4. REST API availability
5. API documentation quality
6. Rate limits
7. Authentication requirements
8. Reliability for scheduled ingestion
9. Suitability for reproducible experiments
10. Licensing and redistribution restrictions
11. Ability to support multiple assets
12. Suitability for automated ETL
13. Error-response behavior
14. Support for incremental or date-bounded extraction
15. Observability of API usage where available

---

## 4. Candidates

### 4.1 Alpha Vantage

Alpha Vantage provides financial market data through a REST API and supports multiple asset classes. For equities, the `TIME_SERIES_DAILY` endpoint provides the required daily OHLCV fields: date, open price, high price, low price, close price, and trading volume.

Responses can be returned as JSON or CSV, making the service technically suitable for an automated extraction process.

Alpha Vantage documents more than 25 years of daily equity history. However, the free `outputsize=compact` response is limited to the latest 100 observations. Access to the complete daily historical series using `outputsize=full` requires a premium API key.

The standard free service is also limited to 25 API requests per day.

During EXP-001, Alpha Vantage successfully returned OHLCV data for all five selected test assets:

- AAPL
- MSFT
- NVDA
- AMZN
- GOOGL

Each tested asset returned 100 daily observations covering May 5, 2026 through September 25, 2026.

The invalid-symbol experiment identified an important extraction consideration. Alpha Vantage returned HTTP `200 OK` even though the requested symbol was invalid. The failure was represented inside the JSON response through an API-specific error message.

Therefore, an Alpha Vantage extraction component could not rely exclusively on HTTP status codes. It would also need to inspect the response body and verify that the expected time-series structure exists before accepting an extraction as successful.

Alpha Vantage provides sufficient raw OHLCV information for the project's financial calculations. However, its limited free historical response and low daily request allowance reduce its suitability for repeated development experiments, historical backfills, and larger-scale testing.

The project would use only raw market observations rather than Alpha Vantage's precomputed technical indicators so that financial calculations remain part of the project's independently implemented and testable business logic.

---

### 4.2 Financial Modeling Prep

Financial Modeling Prep (FMP) provides financial market information through a REST API and provides end-of-day historical market data through its free Basic plan.

The Basic plan currently provides 250 API calls per day. This provides substantially more development capacity than Alpha Vantage's standard free allowance.

During EXP-001, FMP successfully returned the required OHLCV data for all five selected test assets.

Each tested asset returned 1,255 observations covering September 27, 2021 through September 25, 2026, representing approximately five years of trading history in the tested responses.

The response structure was relatively direct, with records containing fields including:

- symbol
- date
- open
- high
- low
- close
- volume

This structure is suitable for automated parsing and normalization.

The invalid-symbol experiment returned HTTP `402 Payment Required`. The response stated that the supplied symbol value was not available under the current subscription.

This behavior introduces some ambiguity because the response does not necessarily distinguish a nonexistent symbol from an otherwise valid asset that is unavailable under the current subscription. An FMP extraction component would therefore need provider-specific handling for subscription, authentication, rate-limit, server, and data-validation failures.

An additional concern is data licensing. FMP states that displaying or redistributing FMP-sourced data requires a specific Data Display and Licensing Agreement.

This restriction is particularly relevant because the project is intended to support a public portfolio and may eventually include a Streamlit demonstration dashboard. API accessibility alone must therefore not be interpreted as permission to publicly redistribute provider-sourced market data.

Technically, FMP provides a useful free request allowance, straightforward response structure, and substantially more tested historical data than Alpha Vantage. However, its data-display and redistribution requirements introduce an additional constraint for the project's portfolio and demonstration goals.

---

### 4.3 Twelve Data

Twelve Data provides financial market information through a REST API supporting multiple financial instrument types.

Its `/time_series` endpoint provides time-series observations containing:

- datetime
- open
- high
- low
- close
- volume

The API supports JSON responses and provides parameters such as `start_date`, `end_date`, and `outputsize` for controlling historical extraction.

The current free Basic plan provides eight API credits per minute with a daily allowance of 800 API credits. A standard `/time_series` request consumes one API credit per requested symbol.

The `/time_series` endpoint supports up to 5,000 observations in a single request. Date-bounded extraction can also be performed using `start_date` and `end_date`, making the API suitable for controlled historical extraction and future incremental-ingestion strategies.

During EXP-001, Twelve Data successfully returned the required OHLCV data for all five selected test assets:

- AAPL
- MSFT
- NVDA
- AMZN
- GOOGL

The experiment requested 5,000 daily observations for each asset, and all five requests successfully returned the requested 5,000 observations. The resulting data covered November 8, 2006 through September 25, 2026.

The 5,000 observations represent the requested experiment output size and should not be interpreted as the maximum historical depth available for every asset.

Twelve Data returned responses containing a separate metadata object and a `values` collection containing the market observations. This structure is suitable for programmatic validation and provider-specific parsing.

The invalid-symbol experiment returned HTTP `404 Not Found` together with a structured JSON error response containing an error code, error status, and explanatory message.

The response headers also exposed API-credit information, including credits requested, used, and remaining. These values may later provide useful observability signals for monitoring API consumption.

The free Basic plan is intended for internal non-display usage. Twelve Data's usage guidance identifies educational projects and academic research as acceptable non-commercial uses of individual plans. However, individual plans do not grant unrestricted redistribution or commercial third-party display rights.

This distinction is important for the project. Twelve Data can be used as the primary source for the educational ingestion and analytical pipeline, but a future publicly deployed dashboard must not assume that free API access automatically grants permission to redistribute provider-sourced market data.

From a technical perspective, Twelve Data provides the strongest combination observed during this evaluation: sufficient free request capacity for the project's small scheduled workload, the largest historical dataset returned during EXP-001, date-bounded historical extraction, structured error responses, and observable API-credit usage.

---

## 5. Comparison

| Criterion | Alpha Vantage | Financial Modeling Prep | Twelve Data |
|---|---|---|---|
| Free tier | Yes | Yes | Yes |
| REST API | Yes | Yes | Yes |
| OHLCV | Yes | Yes | Yes |
| JSON | Yes | Yes | Yes |
| CSV support | Yes | Not required by project | Yes |
| API key required | Yes | Yes | Yes |
| Test assets successful in EXP-001 | 5/5 | 5/5 | 5/5 |
| Observations per asset in EXP-001 | 100 | 1,255 | 5,000 requested and returned |
| Oldest observation in EXP-001 | 2026-05-05 | 2021-09-27 | 2006-11-08 |
| Newest observation in EXP-001 | 2026-09-25 | 2026-09-25 | 2026-09-25 |
| Free request allowance | 25 requests/day | 250 calls/day | 8 API credits/minute, 800/day |
| Free historical behavior relevant to project | Latest 100 daily observations using compact response | Approximately five years observed during EXP-001 | 5,000 requested observations successfully returned during EXP-001 |
| Controlled date-range extraction | Limited for selected daily endpoint | Endpoint-dependent | Yes |
| Maximum observations relevant to tested endpoint | 100 using free daily compact response | Not used as selection criterion | 5,000 per `/time_series` request |
| Invalid-symbol HTTP behavior | `200 OK` | `402 Payment Required` | `404 Not Found` |
| Structured failure information | Yes | Yes | Yes |
| API-usage information observed during EXP-001 | No | No | Yes, credit headers |
| Suitable for scheduled ETL | Yes | Yes | Yes |
| Suitable for own financial calculations | Yes | Yes | Yes |
| Historical backfill suitability under tested access | Limited | Good | Strong |
| Incremental extraction suitability | Possible | Possible | Strong due to date parameters |
| Public display / redistribution consideration | Requires applicable rights review | Specific display/licensing agreement required | Basic intended for internal/non-display use; redistribution restricted |
| Main technical advantage | Simple OHLCV API | Direct records and useful free historical depth | Historical depth, request allowance, date-range control, structured errors and credit metadata |
| Main limitation for this project | Low free quota and 100-observation free daily response | Display/redistribution restrictions and subscription-related error ambiguity | Public display/redistribution restrictions must be respected |

---

## 6. Selected Source

Twelve Data is selected as the primary financial market data source for the initial implementation of the project.

The decision is based on a combination of the experimental results recorded in EXP-001, the project's functional and non-functional requirements, and the documented capabilities of the free Basic plan.

During EXP-001, Twelve Data successfully returned OHLCV data for all five selected test assets. Each request returned the requested 5,000 daily observations, covering November 8, 2006 through September 25, 2026. This was the largest historical dataset returned by the three evaluated providers under the tested access.

Historical depth is particularly valuable to this project because several planned business metrics depend on rolling windows or historical state. These include moving averages, rolling volatility, RSI, rolling volume statistics, returns, and drawdown.

Twelve Data also demonstrated behavior useful for automated ETL processing. Successful responses contain identifiable metadata and a `values` collection containing market observations. The invalid-symbol experiment returned HTTP `404 Not Found` together with a structured JSON error response. API-credit usage was also exposed through response headers, providing a possible signal for future pipeline observability.

The API's support for `start_date` and `end_date` is also useful for the planned pipeline architecture. Initial historical ingestion can retrieve a controlled historical range, while later scheduled runs can request only the required incremental period instead of repeatedly downloading the complete historical dataset.

The free Basic allowance is sufficient for the planned small-scale educational workload, which uses a limited number of assets and scheduled ingestion rather than high-frequency data collection.

Alpha Vantage was not selected as the primary provider because the free daily endpoint returned only 100 observations per asset during EXP-001 and the standard free request allowance is comparatively restrictive.

Financial Modeling Prep was not selected as the primary provider because, although it provided substantially more historical data than Alpha Vantage and a useful free request allowance, its display and redistribution requirements introduce additional constraints for the project's portfolio and dashboard goals. Its invalid-symbol test also produced a subscription-related `402` response that is less explicit than Twelve Data's observed invalid-symbol behavior.

The selection of Twelve Data applies specifically to the project's primary ingestion and educational analytical pipeline. It does not imply that the project has unrestricted rights to publicly redistribute Twelve Data market data.

Alpha Vantage and Financial Modeling Prep remain documented alternatives and potential fallback providers.

---

## 7. Limitations

The selected data source introduces several limitations that must be considered during implementation.

### 7.1 External API Dependency

The project depends on an external service whose endpoints, request limits, market coverage, response structures, and subscription conditions may change.

Provider-specific extraction logic should therefore be isolated from downstream transformation and loading logic.

The rest of the pipeline should not depend directly on Twelve Data's native JSON structure.

### 7.2 Free-Tier Usage Limits

The Basic plan imposes API-credit limits.

The pipeline should avoid unnecessary requests and should use controlled incremental extraction rather than repeatedly downloading the complete historical dataset during every scheduled execution.

API-credit information exposed by response headers may be captured in pipeline logs or metadata to support observability.

### 7.3 Historical Availability

The 5,000 observations obtained during EXP-001 represent the requested `outputsize` used during the experiment.

The result should not be interpreted as a guarantee that every financial instrument or market available through Twelve Data will provide the same historical depth.

Historical availability should therefore be validated for assets added to the project in the future.

### 7.4 Market Coverage

The free Basic plan does not provide unrestricted access to every market and dataset supported by Twelve Data.

The five US equity symbols selected for EXP-001 were successfully retrieved, which is sufficient for the initial project scope. Expanding the project to additional exchanges, asset classes, or regions may require additional validation or different access rights.

### 7.5 Provider-Specific Error Handling

EXP-001 demonstrated that financial data providers use different error semantics.

The Twelve Data extractor should explicitly handle:

- authentication failures
- invalid symbols
- malformed requests
- rate-limit failures
- server failures
- timeouts
- malformed JSON
- missing expected fields
- empty responses

The extractor should not treat HTTP success alone as proof that valid market data was returned.

### 7.6 Licensing and Public Display

Free API access does not automatically grant unrestricted rights to redistribute market data.

Twelve Data's individual plans are intended for personal or internal use and support non-commercial educational use cases, but redistribution and external display are restricted.

The project will therefore use Twelve Data for educational ingestion, transformation, testing, and analysis without assuming unrestricted redistribution rights.

Before deploying a publicly accessible Streamlit dashboard, the applicable data-display rights must be reviewed again.

Depending on those requirements, the public demonstration may need to:

- operate locally or privately;
- use appropriately licensed demonstration data;
- restrict the provider-derived information displayed;
- emphasize derived analytical results where permitted; or
- use a different data source specifically approved for public display.

No API keys or substantial raw provider responses will be committed to the public Git repository.

### 7.7 Provider Portability

Twelve Data should not become tightly coupled to the transformation and storage layers.

Provider-specific responses will be converted into a canonical internal market-data representation before downstream processing.

A target normalized structure may contain fields such as:

- symbol
- observation date
- open
- high
- low
- close
- volume
- source
- extraction timestamp

This separation allows the project to replace Twelve Data with another provider in the future without rewriting the core financial calculations, data-quality rules, dimensional model, or dashboard logic.

---

## 8. Decision Summary

Twelve Data is selected as the primary market-data provider for the initial implementation.

The selection is primarily supported by:

- successful retrieval of all five required test assets;
- availability of the required OHLCV fields;
- 5,000 requested daily observations successfully returned per asset during EXP-001;
- substantially greater tested historical depth than the other candidates;
- a free request allowance suitable for the planned workload;
- support for controlled historical date ranges;
- structured error responses;
- observable API-credit information; and
- suitability for educational, scheduled ETL development.

The decision is not irreversible.

The extraction layer will be designed so that provider-specific parsing is separated from the project's canonical data model and downstream business logic. This allows Alpha Vantage, Financial Modeling Prep, or another provider to be introduced later if technical, licensing, availability, or project requirements change.

The formal architectural rationale and consequences of this decision are recorded separately in `ADR-001 — Primary Financial Data Source`.