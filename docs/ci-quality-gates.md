
# CI Quality Gates

## Overview

The Financial Market Data Platform uses GitHub Actions to
automatically verify code quality and run database-independent
tests on pull requests and pushes to `main`.

The CI workflow includes:

- Ruff linting.
- Ruff formatting verification.
- Database-independent pytest tests.

## Local Setup

Install the project's development dependencies:

```bash
python -m pip install -e ".[dev]"
```

## Ruff Linting

Check Python code for lint violations:

```bash
python -m ruff check .
```

This command reports issues without modifying files.

## Ruff Formatting

Check whether all Python files follow the configured
formatting standard:

```bash
python -m ruff format --check .
```

The formatting check does not modify files.

To format Python files locally, run:

```bash
python -m ruff format .
```

This command modifies files to match the Ruff formatting
standard.

Review the changes before committing:

```bash
git diff --stat
git diff --check
git diff
```

GitHub Actions enforces both linting and formatting on
pull requests and pushes to `main`.

## Database-Independent Tests

Run unit tests without requiring PostgreSQL or Docker:

```bash
python -m pytest -q -m "not integration"
```

Tests marked `integration` are excluded.

## PostgreSQL Integration Tests

PostgreSQL integration tests are currently executed locally
using the isolated test database `financial_market_test`.

Make sure PostgreSQL is running and the local `.env` file
contains the correct test database configuration.

Run the complete test suite:

```bash
python scripts/run_tests.py
```

The test runner loads the local `.env` file.

Never run integration tests against the production or
primary Gold warehouse.

Automated PostgreSQL integration testing in GitHub Actions
will be implemented in a separate M7 issue.

## Security

- Do not commit `.env` files or database credentials.
- Do not use production database credentials in CI.
- Do not make live Twelve Data API requests during tests.
- Use only the isolated `financial_market_test` database
  for PostgreSQL integration tests.
- Use minimal GitHub Actions permissions.

## Troubleshooting

If Ruff linting fails:

```bash
python -m ruff check .
```

If formatting verification fails:

```bash
python -m ruff format --check .
```

If unit tests fail:

```bash
python -m pytest -q -m "not integration"
```

Review reported errors before making changes.


## Automated PostgreSQL Integration Tests

GitHub Actions runs PostgreSQL-backed integration tests in a
dedicated job on pull requests and pushes to `main`.

### CI Environment

The integration-test job uses:

- Python 3.11.
- PostgreSQL 17 through Docker Compose.
- The isolated `financial_market_test` database.
- Temporary CI-only database credentials.
- The existing SQL migration system.

The workflow creates the required Docker network, starts
PostgreSQL, initializes migration history, and applies the
existing Gold warehouse migrations.

It then executes:

```bash
python -m pytest -q -m integration
```

The integration job is independent of the Ruff and unit-test
jobs.

### Local Integration Tests

Local tests continue to use the project's private `.env` file
and dedicated PostgreSQL test database.

Run the complete test suite using:

```bash
python scripts/run_tests.py
```

Never execute database integration tests against the primary
warehouse.

### CI Database Safety

- CI does not require production database credentials.
- The temporary PostgreSQL database exists only for the CI run.
- CI does not make live Twelve Data API requests.
- Tests must verify they are using `financial_market_test`.
- The existing targeted cleanup and database safety checks
  remain in place.
- The temporary Docker environment is removed after execution.

### Troubleshooting

If the integration job fails:

1. Check whether Docker Compose started successfully.
2. Check the PostgreSQL readiness and database identity steps.
3. Review migration initialization and application logs.
4. Identify the first failing integration test.
5. Reproduce the failure locally against `financial_market_test`.

Do not bypass database identity checks to make CI pass.