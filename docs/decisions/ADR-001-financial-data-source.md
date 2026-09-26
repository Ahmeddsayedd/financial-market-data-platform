# ADR-001 — Primary Financial Data Source

## Status

Accepted

---

## Date

2026-09-26

---

## Context

The financial analytics platform requires an external market-data provider for scheduled extraction of historical and newly available market observations.

The selected provider must support the project's core requirements:

- zero-cost access for the initial educational implementation;
- daily OHLCV market data;
- multiple equity symbols;
- sufficient historical observations for rolling financial calculations;
- programmatic access through a REST API;
- reliable use within an automated ETL pipeline;
- reproducible historical extraction;
- manageable request limits;
- identifiable error behavior; and
- compatibility with the project's educational and portfolio goals.

Three candidate providers were evaluated:

1. Alpha Vantage
2. Financial Modeling Prep
3. Twelve Data

The detailed provider comparison is documented in `docs/data-source-evaluation.md`.

The candidates were also tested experimentally using real API requests in `EXP-001 — Financial Data Source Validation`.

The experiment used the following assets:

- AAPL
- MSFT
- NVDA
- AMZN
- GOOGL

All three providers successfully returned the required OHLCV data for these assets, but substantial differences were observed in historical depth, request allowances, response structures, and error behavior.

---

## Decision Drivers

The primary decision drivers are:

1. Availability of the required OHLCV fields
2. Historical depth available under free access
3. Free-tier request capacity
4. Support for controlled historical and incremental extraction
5. Suitability for scheduled automated ETL
6. Error-response behavior
7. Ability to monitor API consumption
8. Reproducibility of historical ingestion
9. Compatibility with the project's zero-cost constraint
10. Ability to isolate provider-specific behavior from downstream processing
11. Licensing and public-display considerations

---

## Options Considered

### Option 1 — Alpha Vantage

Alpha Vantage successfully returned OHLCV data for all five test assets.

During EXP-001, each asset returned 100 daily observations covering May 5, 2026 through September 25, 2026.

The API provides a relatively simple mechanism for retrieving daily market data and supplies all fields required by the project.

However, the free daily compact response is limited to 100 observations, and the standard free service provides a relatively small daily request allowance.

The invalid-symbol experiment also returned HTTP `200 OK` while reporting the failure inside the JSON response. An extractor using Alpha Vantage would therefore need to inspect provider-specific response fields in addition to HTTP status codes.

#### Advantages

- Provides the required OHLCV fields
- Simple REST-based extraction
- Successfully returned all five required assets
- Suitable for small scheduled workloads
- Supports the project's own downstream financial calculations

#### Disadvantages

- Only 100 daily observations returned under the tested free daily access
- Relatively restrictive free request allowance
- Limited historical backfill capability under the tested free access
- HTTP `200 OK` may still contain an API-level error
- Additional payload validation is required to distinguish successful and unsuccessful responses

---

### Option 2 — Financial Modeling Prep

Financial Modeling Prep successfully returned OHLCV data for all five test assets.

During EXP-001, each asset returned 1,255 observations covering September 27, 2021 through September 25, 2026.

The returned records have a relatively direct structure containing fields such as `symbol`, `date`, `open`, `high`, `low`, `close`, and `volume`, which would be straightforward to normalize.

The free request allowance also provides more development capacity than Alpha Vantage.

However, the invalid-symbol experiment returned HTTP `402 Payment Required` with a message indicating that the supplied symbol was unavailable under the current subscription. This does not clearly distinguish a nonexistent asset from an asset that may exist but is inaccessible under the current subscription.

Data-display and redistribution requirements are also an important consideration for the project's intended public portfolio and potential dashboard demonstration.

#### Advantages

- Provides the required OHLCV fields
- Successfully returned all five required assets
- Approximately five years of historical observations obtained during EXP-001
- Direct and convenient response structure
- Higher free request allowance than Alpha Vantage
- Suitable for scheduled end-of-day ingestion

#### Disadvantages

- Less tested historical depth than Twelve Data
- Subscription-related HTTP behavior introduces error-classification ambiguity
- Public display and redistribution require additional licensing consideration
- Potential public dashboard usage would require careful review of applicable data rights

---

### Option 3 — Twelve Data

Twelve Data successfully returned OHLCV data for all five test assets.

During EXP-001, the API returned the requested 5,000 daily observations for each asset, covering November 8, 2006 through September 25, 2026.

This was the largest historical dataset returned by any of the three evaluated providers under the tested access.

The `/time_series` endpoint also supports parameters for controlling historical extraction, including date-bounded requests. This is useful for both initial historical backfills and future incremental ingestion.

The invalid-symbol experiment returned HTTP `404 Not Found` together with a structured JSON error response containing an error code, status, and explanatory message.

API-credit information was also observed in HTTP response headers, providing a potential mechanism for monitoring API consumption.

The free Basic plan provides sufficient request capacity for the planned small-scale scheduled workload.

Individual-plan usage conditions support educational use, but unrestricted public redistribution of provider-sourced market data must not be assumed. Public dashboard deployment therefore requires a separate review of applicable display rights.

#### Advantages

- Provides the required OHLCV fields
- Successfully returned all five required assets
- Returned the requested 5,000 observations per asset during EXP-001
- Largest tested historical depth
- Free request capacity suitable for the planned workload
- Supports controlled historical date ranges
- Suitable for incremental extraction
- Structured invalid-symbol response
- API-credit usage observable through response headers
- Clear separation between metadata and time-series observations
- Suitable for scheduled automated extraction

#### Disadvantages

- Free-tier API-credit limits still require request management
- Historical availability may differ between instruments and markets
- Free market coverage is not unlimited
- External API behavior and plan conditions may change
- Public display and redistribution rights are restricted and must be reviewed separately

---

## Decision

Twelve Data is selected as the primary financial market data provider for the initial implementation of the platform.

The provider will be used for scheduled extraction of raw daily OHLCV market observations.

The initial implementation will use a limited set of supported equity assets and will operate within the free API allowance.

Twelve Data-specific response structures will not be propagated directly into the downstream transformation, storage, or presentation layers.

Instead, extracted provider data will be validated and normalized into a provider-independent internal representation before downstream processing.

---

## Rationale

Twelve Data provides the strongest overall fit for the current project requirements based on both documented capabilities and the results of EXP-001.

The experiment demonstrated that Twelve Data could successfully retrieve all five required assets and return the requested 5,000 daily observations for each asset. This historical depth is useful for the project's planned financial calculations, including:

- period returns;
- logarithmic returns;
- moving averages;
- rolling volatility;
- RSI;
- drawdown; and
- rolling volume statistics.

The available historical depth also provides a larger dataset for the planned Pandas and PySpark scalability experiment.

The API's support for controlled date ranges is important for pipeline design. The platform can perform an initial historical backfill and later request only the required incremental period rather than downloading the complete historical dataset on every scheduled execution.

The observed structured error response for an invalid symbol is also suitable for automated failure classification and logging.

In addition, observable API-credit headers may be incorporated into pipeline metadata or logging to improve operational visibility.

The available free request capacity is sufficient for the project's intended small-scale scheduled ingestion workload.

These technical advantages provide a better fit for the project's current requirements than the more restrictive tested historical response from Alpha Vantage and the additional display/licensing concerns associated with Financial Modeling Prep.

---

## Consequences

### Positive Consequences

- The project gains sufficient historical market data for implementing and testing rolling financial calculations.
- Historical backfills and scheduled incremental extraction can use the same provider.
- The relatively generous free request allowance supports repeated development, testing, and scheduled pipeline execution.
- Structured API errors can be incorporated into extraction failure handling.
- API-credit information can potentially be captured for observability.
- The larger historical dataset supports meaningful performance and scalability experiments.
- The selected source satisfies the project's initial zero-cost requirement for the planned workload.

### Negative Consequences

- The platform becomes dependent on an external provider whose API behavior, request limits, market coverage, and subscription conditions may change.
- The free tier still imposes request limits, so extraction must avoid unnecessary API calls.
- Not every financial instrument is guaranteed to provide the same historical depth observed during EXP-001.
- Provider-specific error handling remains necessary.
- Market-data licensing restrictions mean that successful API access cannot be interpreted as unrestricted permission to redistribute raw market data publicly.
- A future public Streamlit deployment must review the applicable data-display rights before exposing provider-derived data.

---

## Architectural Implications

The extraction layer must isolate Twelve Data-specific behavior from the rest of the platform.

The intended flow is:

    Twelve Data API
          |
          v
    Provider-Specific Extraction
          |
          v
    Raw Response Preservation
          |
          v
    Response and Data Validation
          |
          v
    Canonical Market-Data Schema
          |
          v
    Transformation / Business Logic
          |
          v
    PostgreSQL Dimensional Model
          |
          v
    Streamlit Analytics

The canonical representation should contain provider-independent fields such as:

- symbol
- observation date
- open
- high
- low
- close
- volume
- source
- extraction timestamp

Downstream business logic must operate on the normalized representation rather than directly on Twelve Data's native `values` response structure.

This reduces vendor coupling and improves testability.

---

## Failure Handling Implications

The extraction component should explicitly handle at least the following failure categories:

- authentication failure
- invalid symbol
- malformed request
- API rate-limit exhaustion
- timeout
- connection failure
- server error
- malformed JSON
- missing expected response fields
- empty time-series response
- invalid market-data values

Retries should be bounded and should use appropriate backoff behavior for transient failures.

Permanent failures such as invalid symbols should not be retried indefinitely.

Provider-specific errors should be converted into meaningful internal failure categories for logging and pipeline metadata.

---

## Rate-Limit Implications

The pipeline should minimize unnecessary API consumption.

The initial historical backfill should be separated conceptually from normal scheduled incremental ingestion.

After historical data has been loaded successfully, normal pipeline executions should request only the data required to bring the local dataset up to date.

Where useful, API-credit information exposed by Twelve Data may be recorded as operational metadata.

Tests for rate-limit behavior should use mocked responses rather than intentionally exhausting the real free API allowance.

---

## Data Licensing and Public Display

Twelve Data is selected for educational ingestion and analytical processing.

This decision does not assume unrestricted rights to publicly redistribute raw provider data.

Raw API responses will not be committed to the public Git repository.

API credentials will be supplied through environment variables and will not be stored in version control.

Before a publicly accessible Streamlit dashboard is deployed, the applicable provider terms and data-display rights must be reviewed again.

If the selected provider's licensing conditions do not permit the intended public demonstration, the presentation layer may need to use:

- appropriately licensed demonstration data;
- a local or private dashboard;
- restricted provider-derived information;
- permitted derived analytics; or
- another data source with suitable display rights.

This licensing consideration does not prevent Twelve Data from being used for the project's local educational ETL implementation.

---

## Alternatives and Fallback Strategy

Alpha Vantage and Financial Modeling Prep remain documented fallback providers.

The architecture should make replacement of the primary provider possible without rewriting the complete pipeline.

Provider replacement should require changes primarily within the extraction and normalization components.

The following downstream components should remain provider-independent:

- data-quality validation rules
- financial business logic
- dimensional model
- PostgreSQL loading logic
- orchestration structure
- pipeline metadata
- automated business-logic tests
- analytics queries
- dashboard logic

If Twelve Data becomes unsuitable because of pricing, availability, licensing, market coverage, or API changes, another provider can be integrated by implementing a new provider-specific extractor that produces the same canonical internal schema.

---

## Related Documentation

- `docs/data-source-evaluation.md`
- `docs/experiments/EXP-001-data-source-validation.md`
- `docs/requirements.md`

---

## Decision Outcome

Twelve Data is accepted as the primary financial market data source for the initial implementation.

The decision will be reconsidered if:

- the free plan no longer supports the required workload;
- required assets become unavailable;
- API behavior changes materially;
- licensing conditions conflict with project requirements;
- reliability becomes insufficient for scheduled ingestion; or
- another project requirement makes the selected provider unsuitable.

Because the provider-specific extraction layer will be isolated from downstream processing, reconsidering this decision should not require redesigning the entire platform.