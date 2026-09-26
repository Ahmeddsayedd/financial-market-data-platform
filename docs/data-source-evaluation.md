# Financial Data Source Evaluation

## 1. Purpose

The financial data pipeline requires an external source of market data. Before implementation, candidate data providers are evaluated to ensure that the selected source satisfies the functional requirements and the zero-cost constraint of the project.

The selected source should provide sufficient raw market data for the project to calculate its own financial metrics rather than relying on precomputed indicators from the provider.

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

The source should also provide sufficient historical observations to support rolling calculations and performance experiments.

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

---

## 4. Candidates

### 4.1 Alpha Vantage

Alpha Vantage provides financial market data through a REST API and supports multiple asset classes, including equities, ETFs, foreign exchange, and cryptocurrencies. For equities, the TIME_SERIES_DAILY endpoint provides the required OHLCV fields: date, open price, high price, low price, close price, and trading volume. Responses can be returned as either JSON or CSV, making the service suitable for an automated extraction process.

The provider offers more than 25 years of daily historical equity data; however, an important limitation exists for the free tier. The free compact response contains only the latest 100 observations, while requesting the complete historical series using outputsize=full requires premium access. The standard free service is also limited to 25 API requests per day. Alpha Vantage states that verified educational and open-source projects may qualify for increased access, but the project should not depend on receiving such an exception.

For this project, Alpha Vantage could support a small scheduled end-of-day pipeline because only a limited number of assets would need to be requested each day. The available OHLCV information is sufficient for implementing the project's own financial calculations, including returns, moving averages, rolling volatility, RSI, and drawdown. However, the low daily request limit and restricted free historical depth reduce its suitability for larger experiments and frequent pipeline executions.

The project would use only raw market observations from the provider for its primary transformations rather than relying on Alpha Vantage's precomputed technical indicators. This ensures that the financial calculations remain part of the project's independently testable business logic.

### 4.2 Financial Modeling Prep

Financial Modeling Prep (FMP) provides financial market information through a REST API and offers historical end-of-day market data suitable for analytical applications and ETL pipelines. Its historical market-data services include stock-price information that can be used as the source for financial transformations.

The current free Basic plan provides 250 API calls per day and access to end-of-day historical data. The free plan currently provides up to five years of historical data. Compared with Alpha Vantage's standard free allowance of 25 requests per day, this provides substantially more capacity for repeated development, testing, and scheduled ingestion.

The end-of-day nature of the free plan would make the source suitable for a scheduled daily financial analytics pipeline rather than a genuine real-time market-data system. This limitation is acceptable if the project's core architecture is defined as scheduled or periodically refreshed financial analytics.

An additional consideration is data licensing. FMP states that displaying or redistributing its data requires an appropriate data display and licensing agreement. Therefore, the project would need to avoid redistributing substantial provider data through the public GitHub repository and would need to investigate the permitted use of data in a publicly accessible demonstration dashboard before selecting FMP as the final source.

From a technical perspective, the higher request allowance and historical end-of-day access make FMP an attractive candidate for development and ETL experimentation. The licensing conditions, however, require additional consideration because reproducibility and portfolio presentation are important requirements of this project.

### 4.3 Twelve Data

Twelve Data provides financial market information through a REST API with support for equities, ETFs, foreign exchange, cryptocurrencies, and other instruments. Its /time_series endpoint provides historical time-series observations containing datetime, open, high, low, close and, where applicable, trading volume. The endpoint supports intervals ranging from one minute to one month and can return data in JSON or CSV format.

The free Basic plan currently provides eight API credits per minute and a daily allowance of 800 credits. A standard /time_series request has a weight of one credit per requested symbol. This provides considerably more request capacity than the standard free Alpha Vantage allowance and would allow repeated extraction during development without immediately exhausting the daily quota.

The /time_series endpoint supports a maximum of 5,000 observations per request. Twelve Data also provides start_date and end_date parameters, which are useful for controlled historical extraction and incremental ingestion. According to its documentation, daily intervals can provide historical information extending back to the first trading date for many symbols, although actual data availability depends on the instrument and the access provided by the selected plan.

Twelve Data also exposes useful metadata such as the instrument symbol, exchange, currency, exchange timezone, MIC code, asset type, and interval. These fields could be useful when designing the project's asset dimension and handling timestamps correctly.

A significant consideration is plan-specific market coverage. The Basic plan provides access to a limited set of capabilities and trial coverage, while broader international market coverage and some advanced functionality require paid plans. The exact symbols intended for the project must therefore be tested using a free account before the source can be considered suitable.

Technically, Twelve Data is an attractive candidate because of its structured time-series endpoint, OHLCV support, relatively generous API allowance, historical query parameters, explicit metadata, and support for controlled date ranges. Its actual free symbol coverage and usage conditions should be experimentally verified before a final decision is made.

---

## 5. Comparison

| Criterion | Alpha Vantage | FMP | Twelve Data |
|---|---|---|---|
| Free tier | Yes | Yes | Yes |
| REST API | Yes | Yes | Yes |
| OHLCV | Yes | Yes | Yes |
| JSON | Yes | Yes | Yes |
| CSV | Yes | To verify | Yes |
| Historical data | Yes | Yes | Yes |
| Free historical depth | Latest 100 daily observations through compact response | Up to 5 years | Instrument/plan dependent; verify experimentally |
| Free request allowance | 25 requests/day | 250 calls/day | 8 credits/minute, 800/day |
| Date-range queries | Limited by endpoint/output size | Available depending on endpoint | Yes |
| Max observations/request | 100 for free daily compact response | To verify | 5,000 |
| API key required | Yes | Yes | Yes |
| Intraday on free tier | Restricted/premium for relevant equity use | Not core Basic offering | Available features depend on Basic coverage |
| Suitable for scheduled ETL | Yes | Yes | Yes |
| Suitable for our own calculations | Yes | Yes | Yes |
| Free symbol coverage | Good, but verify selected assets | Verify | Must verify |
| Licensing concern | Must review before publication | Display/redistribution restrictions | Must review before publication |
| Main advantage | Simple raw OHLCV API | 250 calls/day + EOD history | 800/day + flexible time-series API |
| Main disadvantage | Very low free quota/history restriction | Licensing/display restrictions | Free coverage requires verification |

---

## 6. Selected Source

TODO

---

## 7. Limitations

TODO