# Financial Market Data Platform

Python-based financial market data ingestion, validation, PostgreSQL analytics and
Apache Airflow orchestration, with a read-only Streamlit dashboard.

The repository's development setup uses Docker Compose, Airflow 3.1.7 and PostgreSQL
17. Financial API access and Gold loading are disabled by default; any authorized
writes through Airflow are restricted to the isolated `financial_market_test`
database. The DAG is paused on creation. This is a local development platform, not
an automatically deployed production service.

## Getting started and operating safely

- [M11 v1.0 readiness audit](docs/operations/m11-v1-release-audit.md) —
  current release gaps and follow-up priorities.
- [M11 v1.0 release gate checklist](docs/operations/m11-v1-release-checklist.md) —
  review and verification steps; not an approval record.
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
