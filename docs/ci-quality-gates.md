
# CI Quality Gates

## Overview

The project uses GitHub Actions to validate pull requests
and pushes to `main`.

The initial workflow runs two independent checks:

1. Ruff linting.
2. Database-independent pytest tests.

## Local Setup

Install development dependencies:

```bash
python -m pip install -e ".[dev]"
```

## Ruff Lint

```bash
python -m ruff check .
```

The lint command reports issues without modifying files.

## Unit Tests

```bash
python -m pytest -q -m "not integration"
```

Integration tests are excluded using the registered
pytest `integration` marker.

## PostgreSQL Integration Tests

PostgreSQL integration tests are not executed by the
initial GitHub Actions workflow.

They require a dedicated PostgreSQL test environment
and database-safety configuration.

To execute integration tests locally, follow the
project's existing integration-test prerequisites
and use the local test runner:

```bash
python scripts/run_tests.py tests/integration -v
```

The runner requires the local `.env` configuration.

Never point integration tests at the production warehouse.
The expected isolated database is `financial_market_test`.

## Security

The initial CI workflow:

- Does not use production credentials.
- Does not require Twelve Data API credentials.
- Does not perform live market ingestion.
- Does not modify the Gold warehouse.
- Uses read-only GitHub repository permissions.

## Troubleshooting

If Ruff fails, inspect the reported filename and line
number and fix the issue locally.

If unit tests fail, reproduce the failure using:

```bash
python -m pytest -q -m "not integration"
```

Do not add a private `.env` file to the repository.
