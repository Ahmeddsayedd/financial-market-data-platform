# System Requirements

## 1. Project Objective

The objective of this project is to design and implement an automated financial data engineering platform that collects market data from an external REST API, preserves the original source data, validates and transforms the collected records, calculates financial analytics, and loads the resulting data into a dimensional data warehouse.

The system will demonstrate practical data engineering concepts including automated data ingestion, data transformation, dimensional modeling, workflow orchestration, data-quality validation, idempotent processing, automated testing, containerization, observability, and analytical visualization.

The project is intended to operate as a reproducible data engineering system rather than as a trading platform. Its analytical output will be presented through a read-only dashboard.

The core system must be reproducible using free and open-source technologies without depending on paid cloud infrastructure.

---

## 2. Scope

The project covers the complete data lifecycle from external data acquisition to analytical presentation.

The system will collect historical and periodically updated financial market data for a selected set of publicly traded assets. The retrieved source data will first be stored in a raw data layer so that transformations can be reproduced without repeatedly requesting the same data from the external API.

The processing layer will validate, clean, and transform the raw records. It will also calculate derived financial metrics such as returns, moving averages, rolling volatility, drawdown, and other selected indicators.

Processed information will be loaded into a dimensional PostgreSQL data warehouse designed for analytical queries. Apache Airflow will orchestrate the individual pipeline stages and execute them according to a configurable schedule.

A Streamlit dashboard will query the analytical data and provide visualizations of financial metrics and pipeline-health information.

The project also includes automated testing, data-quality checks, execution logging, pipeline metadata, failure handling, and performance experiments.

The core implementation will run locally using Docker-based infrastructure so that the complete environment can be reproduced without paid services.

---

## 3. Functional Requirements

### FR-01 — Financial Data Extraction
The system shall retrieve financial market data from an external REST API for a configured collection of assets.

### FR-02 — Raw Data Preservation
The system shall preserve retrieved source data before transformation so that previously collected data can be reprocessed without requiring another API request.

### FR-03 — Input Validation
The system shall validate incoming financial records before they enter the transformation and analytical layers.

### FR-04 — Financial Transformation
The system shall transform validated market data and calculate defined analytical financial metrics.

### FR-05 — Dimensional Data Warehouse
The system shall load processed information into a dimensional PostgreSQL data warehouse suitable for analytical queries.

### FR-06 — Automated Orchestration
The system shall use Apache Airflow to orchestrate pipeline stages and execute the pipeline according to a configurable schedule.

### FR-07 — Analytical Dashboard
The system shall expose processed analytical information through a read-only Streamlit dashboard.

### FR-08 — Pipeline Metadata
The system shall record metadata describing pipeline executions, including execution status, processing duration, and record counts.

### FR-09 — Invalid Record Quarantine
The system shall prevent records that violate defined data-quality rules from entering the analytical layer and shall preserve rejected records for investigation.

### FR-10 — Historical Reprocessing
The system shall support reprocessing previously collected raw data without requiring the source API to be queried again.

### FR-11 — Automated Testing
The project shall provide automated tests for critical transformation and business-logic components.

### FR-12 — Pipeline Health Analytics
The system shall provide information about pipeline execution health, including successful and failed executions, processing duration, and processed/rejected record counts.

---

## 4. Non-Functional Requirements

### NFR-01 — Idempotency
Processing the same source data multiple times shall not produce duplicate analytical records or otherwise incorrectly change the resulting warehouse state.

### NFR-02 — Reproducibility
The development environment shall be reproducible using Docker-based configuration and documented setup instructions.

### NFR-03 — Testability
Financial transformation logic shall be separated from external APIs, orchestration, and database access so that it can be tested independently.

### NFR-04 — Recoverability
A failed downstream processing stage shall be rerunnable without requiring successful upstream stages to be unnecessarily repeated.

### NFR-05 — Observability
Pipeline executions shall record sufficient metadata to determine execution status, processing duration, processed record counts, rejected record counts, and failures.

### NFR-06 — Security
Secrets, passwords, and API credentials shall not be committed to version control.

### NFR-07 — Data Quality
Invalid records shall be detected before they become available to the analytical layer.

### NFR-08 — Cost
The core project shall be executable using free and open-source software without requiring paid cloud infrastructure.

### NFR-09 — Maintainability
Extraction, transformation, loading, data-quality, orchestration, and presentation responsibilities shall be separated into appropriate modules to reduce unnecessary coupling.

### NFR-10 — Traceability
Processed analytical records and pipeline executions shall contain sufficient metadata to identify when and through which pipeline execution the data was produced.

---

## 5. Business Logic Requirements

The transformation layer represents the primary business logic of the application. Financial calculations shall be implemented independently from the dashboard so that they can be tested and reused.

The initial set of business calculations will include the following requirements:

### BL-01 — Period Return
The system shall calculate the percentage return between consecutive closing prices for each asset.

### BL-02 — Logarithmic Return
The system shall calculate logarithmic returns from consecutive valid closing prices.

### BL-03 — Simple Moving Average
The system shall calculate configurable rolling simple moving averages, initially including 20-period and 50-period windows.

### BL-04 — Rolling Volatility
The system shall calculate rolling historical volatility from asset returns using a defined rolling window.

### BL-05 — Drawdown
The system shall calculate the percentage decline of an asset from its previous running maximum.

### BL-06 — Relative Strength Index
The system shall calculate the Relative Strength Index (RSI) using a documented calculation method and configurable period, initially using 14 periods.

### BL-07 — Volume Analysis
The system shall calculate rolling volume statistics that can be used to identify unusually high or low trading activity.

### BL-08 — Business Logic Validation
Each critical financial calculation shall have automated tests using known input values and expected outputs.

The exact mathematical definitions, assumptions, window sizes, and handling of incomplete periods shall be documented before the corresponding transformation is implemented.

---

## 6. Data Quality Requirements

Data-quality validation shall occur before invalid records are made available to analytical consumers.

At minimum, the system shall validate the following rules:

### DQ-01 — Required Fields
Records shall contain the required asset identifier and timestamp.

### DQ-02 — Positive Prices
Valid market prices shall be greater than zero.

### DQ-03 — Price Range Consistency
For OHLC data, the recorded high price shall not be lower than the recorded low price.

### DQ-04 — OHLC Consistency
The high price shall not be lower than the valid open or close price, and the low price shall not be higher than the valid open or close price.

### DQ-05 — Volume Validation
Trading volume shall not be negative.

### DQ-06 — Duplicate Detection
The system shall detect duplicate market observations according to the defined business key, initially expected to consist of an asset identifier and observation timestamp.

### DQ-07 — Invalid Record Handling
Records that fail critical validation rules shall not silently disappear. They shall be rejected or quarantined with information describing the reason for rejection.

### DQ-08 — Quality Metrics
The pipeline shall record the number of accepted and rejected records for each applicable execution.

---

## 7. Security Requirements

### SEC-01 — Secret Management
API credentials, database passwords, and other secrets shall be supplied through environment configuration or another appropriate secret-management mechanism and shall not be hard-coded in application source code.

### SEC-02 — Version Control
Files containing secrets, local credentials, or sensitive environment configuration shall be excluded from Git using .gitignore.

An example configuration file without real credentials may be committed to document the required configuration.

### SEC-03 — Database Access
Application components shall use only the database permissions necessary for their responsibilities where practical.

### SEC-04 — Dashboard Access Pattern
The analytical dashboard shall perform read operations against analytical data and shall not be responsible for modifying source financial records.

### SEC-05 — Logging
Application logs shall not intentionally expose API keys, database passwords, or other secrets.

---

## 8. Reproducibility Requirements

### REP-01 — Containerized Environment
Core infrastructure components shall be defined using Docker and Docker Compose where appropriate.

### REP-02 — Dependency Definition
Python and infrastructure dependencies shall be explicitly defined and versioned sufficiently to allow the project environment to be recreated.

### REP-03 — Configuration Documentation
The repository shall contain documentation describing the configuration required to execute the project.

### REP-04 — Environment Template
The repository shall provide an example environment configuration containing required variable names but no real credentials.

### REP-05 — Database Initialization
Database schemas and required database objects shall be created through version-controlled scripts or migrations rather than undocumented manual configuration.

### REP-06 — Repeatable Setup
A new developer with the documented prerequisites shall be able to clone the repository, configure the required environment variables, initialize the required services, and execute the project by following the repository documentation.

### REP-07 — Reproducible Experiments
Performance experiments used in the thesis shall record their input dataset, configuration, methodology, and results so that the experiment can be repeated.

---

## 9. Constraints

The project is subject to the following constraints:

1. The core implementation must not require paid cloud services or paid infrastructure.
2. The project will primarily run on a single development machine using Docker-based infrastructure.
3. External financial data availability is dependent on the limitations, rate limits, and reliability of the selected free API.
4. The system is an educational and analytical platform and is not intended to provide financial advice.
5. Financial calculations will operate on the data granularity supported by the selected source and project scope.
6. Apache Spark, when used, may operate in local mode rather than on a production distributed cluster.
7. PostgreSQL will represent the analytical warehouse in the reproducible local implementation.
8. The project will prioritize data-engineering architecture, reliability, testability, and reproducibility over frontend complexity.
9. The implementation should remain executable on reasonable consumer hardware.
10. Optional technologies shall not be allowed to prevent completion of the core system.

---

## 10. Out of Scope

The following capabilities are explicitly outside the required scope of the initial project:

    - Real-money trading or order execution
    - Automated investment decisions
    - Financial advice
    - High-frequency trading
    - Machine-learning price prediction
    - Production-scale Kubernetes deployment
    - Paid cloud infrastructure as a requirement
    - Multi-region disaster recovery
    - Production-scale distributed Spark infrastructure
    - Building a complex custom frontend
    - Supporting every financial market or financial instrument
    - Guaranteed real-time market-data delivery

**Note:** Technologies such as Kafka, Kubernetes, Terraform, and managed cloud services may later be investigated as optional extensions, but they are not dependencies for successful completion of the core project.