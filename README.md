# Financial Market Data Platform

Python-based financial market data ingestion, validation, PostgreSQL analytics and
Apache Airflow orchestration, with a read-only Streamlit dashboard.

The repository's development setup uses Docker Compose, Airflow 3.1.7 and PostgreSQL
17. Financial API access and Gold loading are disabled by default; any authorized
writes through Airflow are restricted to the isolated `financial_market_test`
database. The DAG is paused on creation. This is a local development platform, not
an automatically deployed production service.

## Portfolio v1.0 candidate

This repository demonstrates financial-market ingestion and validation, a PostgreSQL
analytics warehouse, scheduled Airflow orchestration and a read-only four-page
Streamlit dashboard. It is a **local portfolio project**, not a hosted service or
production trading system. Financial provider access and Gold writes are off by
default; the DAG starts paused.

A reviewer can follow the [dashboard local setup](docs/dashboard-local-setup.md)
for the read-only UI, the [offline smoke guide](docs/operations/offline-smoke-verification.md)
for safe validation without API credentials, and the [M10 experiment closeout](docs/experiments/m10-reproducibility-closeout.md)
for reproducibility evidence. Actual populated-data demonstrations require an
approved isolated test database and locally configured credentials; no private
data is bundled. Runtime timings depend on the host machine.

Version `1.0.0` is prepared as a release candidate only; **no Git tag, GitHub
Release, registry upload or production deployment is implied**. Consult the
[v1.0.0 draft release notes](docs/operations/v1.0.0-release-notes.md) and
[M11 release evidence](docs/operations/m11-v1-release-evidence.md) before any
publication. Known limitations include range-based dependencies, tag-based base
images, no verified SBOM/signing, and no hosted environment.

## Getting started and operating safely

- [M11 v1.0 readiness audit](docs/operations/m11-v1-release-audit.md) —
  current release gaps and follow-up priorities.
- [M11 v1.0 release gate checklist](docs/operations/m11-v1-release-checklist.md) —
  review and verification steps; not an approval record.
- [M11 deployment startup verification (#97)](docs/operations/m11-deployment-reliability.md) —
  read-only container health snapshot and safe opt-in local startup procedure.
- [Operations index and runbooks](docs/operations/README.md) — start here for
  service startup/shutdown, diagnostics, secrets and backup procedures.
- [Airflow local setup](docs/airflow-local-setup.md) — local Airflow architecture
  and DAG behavior.
- [Secrets and least privilege](docs/operations/secrets-and-least-privilege.md) —
  configuration inventory, role boundaries and manual grants.
- [Backup and recovery](docs/operations/backup-and-recovery.md) — manual,
  operator-approved recovery guidance.

## Development checks

```bash
python -m pip install -e ".[dev]"
python -m ruff check .
python -m ruff format --check .
python scripts/run_tests.py
```

The full test runner uses the local `.env` and expects isolated test databases for
PostgreSQL integration tests. Never upload, commit or paste `.env` or credentials.
GitHub Actions additionally validates Airflow/Streamlit offline smoke checks and
Docker Compose configuration.


### Financial analytics methodology (Issue #101)

The Gold warehouse now calculates and persists period and log returns,
SMA 7/20/30/50, annualized 20-session historical volatility, Wilder RSI 14,
running-peak drawdown, and a 20-session volume z-score. Incomplete rolling
windows remain NULL. See [indicator definitions](docs/financial-indicator-definitions.md)
for precise conventions and the isolated verification procedure. Live Twelve
Data ingestion remains disabled by default and is **not** part of this change.

### Controlled Twelve Data verification (Issue #103)

A bounded, opt-in one-request AAPL verification and replay command is documented in
[`docs/operations/issue-103-twelve-data-live-verification.md`](docs/operations/issue-103-twelve-data-live-verification.md).
It uses the local ignored `.env` and writes evidence to ignored `data/experiments/`;
Gold writes require explicit isolated `financial_market_test` confirmation.

### Repeatable real-market evidence (Issue #104)

[Issue #104 experiment guide](docs/operations/issue-104-end-to-end-evidence.md)
collects measured offline Raw-to-Silver replay distributions from the saved
Issue #103 real AAPL response. An optional read-only audit of
`financial_market_test` reports persisted Gold counts and indicator coverage.
This experiment makes no provider requests, performs no Gold writes, and does
not claim whole-Airflow-DAG performance.

For a run-specific, read-only evidence collection procedure covering local Airflow
tracking, existing Gold indicators, and populated dashboard review, see
[`docs/operations/airflow-end-to-end-demonstration.md`](docs/operations/airflow-end-to-end-demonstration.md).

For the opt-in, test-only complete Airflow Raw → Silver → Gold replay using captured Twelve Data input, see [controlled Airflow real-data execution](docs/operations/controlled-airflow-real-data-execution.md).
