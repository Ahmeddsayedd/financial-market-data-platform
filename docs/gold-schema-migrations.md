# Gold Warehouse Schema Migrations

The Gold warehouse schema is managed through versioned PostgreSQL SQL
migrations and the Python migration runner.

## Prerequisites

- Python 3.11+
- Docker Desktop with Docker Compose
- Running PostgreSQL service (`docker compose up -d`)
- A target PostgreSQL database that already exists

Run commands from the repository root.

## Initialize migration history

For a new, empty target database, initialize and validate the
migration-history table:

```bash
python -c "from scripts.manage_migrations import initialize_migration_history, validate_migration_history; initialize_migration_history('financial_market_test'); validate_migration_history('financial_market_test')"
```

Replace financial_market_test with the name of the PostgreSQL database you want to initialize or manage.

## Apply migrations

```bash
python scripts/manage_migrations.py apply --database financial_market_test
```

The runner applies pending SQL migrations in version order and records their SHA-256 checksums.

Already-applied migrations are skipped. Changes to previously applied migration files are rejected when their checksums no longer match.

## Check migration status

```bash
python scripts/manage_migrations.py status --database financial_market_test
```

Expected after applying migration `001`:

```text
001 | applied
```

## Safety and repeatability

- Schema changes and migration-history insertion execute in one transaction.
- An advisory lock serializes migrations using this runner.
- Migration history is rechecked after acquiring the lock.
- PostgreSQL errors stop migration execution.
- Existing warehouse tables and Docker volumes are not automatically deleted.

## Existing databases

If the warehouse tables were created manually before migration tracking was introduced, do not run migration `001` again.

Verify that the existing schema matches the migration before explicitly registering it as applied. Baselining is a separate, manual operation; the runner does not automatically baseline existing schemas.
