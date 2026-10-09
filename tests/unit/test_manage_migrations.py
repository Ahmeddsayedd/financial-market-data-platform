import hashlib
import subprocess
from scripts.manage_migrations import migration_status
from pathlib import Path
from scripts.manage_migrations import (
    MIGRATIONS_DIR,
    discover_migrations,
    apply_migrations,
    build_migration_sql,
    execute_postgres_migration,
    load_migration_history_sql,
    initialize_migration_history,
    validate_migration_history,
)
from unittest.mock import Mock, patch


def test_discovers_initial_gold_schema_migration():
    migrations = discover_migrations()

    assert len(migrations) == 1

    version, path, checksum = migrations[0]

    assert version == "001"
    assert path.name == "001_create_gold_schema.sql"
    assert path.parent == MIGRATIONS_DIR

    expected_checksum = hashlib.sha256(
        path.read_bytes()
    ).hexdigest()

    assert checksum == expected_checksum
    assert len(checksum) == 64

import pytest


def test_rejects_duplicate_migration_versions(tmp_path, monkeypatch):
    migration_dir = tmp_path / "migrations"
    migration_dir.mkdir()

    (migration_dir / "001_create_schema.sql").write_text(
        "CREATE TABLE example (id INTEGER);",
        encoding="utf-8",
    )

    (migration_dir / "001_add_indexes.sql").write_text(
        "CREATE INDEX example_idx ON example (id);",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "scripts.manage_migrations.MIGRATIONS_DIR",
        migration_dir,
    )

    with pytest.raises(ValueError, match="Duplicate migration version"):
        discover_migrations()

def test_migration_status_detects_pending_and_applied_versions():
    migrations = [
        ("001", Path("001_create_schema.sql"), "checksum-one"),
        ("002", Path("002_add_indexes.sql"), "checksum-two"),
    ]

    applied = {
        "001": "checksum-one",
    }

    result = migration_status(migrations, applied)

    assert result == [
        ("001", "applied"),
        ("002", "pending"),
    ]


def test_migration_status_rejects_checksum_mismatch():
    migrations = [
        ("001", Path("001_create_schema.sql"), "new-checksum"),
    ]

    applied = {
        "001": "old-checksum",
    }

    with pytest.raises(ValueError, match="Checksum mismatch"):
        migration_status(migrations, applied)


def test_apply_skips_already_applied_migration():
    """Do not execute SQL for a migration already recorded."""

    migrations = [
        ("001", Path("001_create_gold_schema.sql"), "checksum-one"),
    ]
    applied = {
        "001": "checksum-one",
    }

    execute_migration = Mock()

    apply_migrations(
        migrations=migrations,
        applied=applied,
        execute_migration=execute_migration,
    )

    execute_migration.assert_not_called()


def test_apply_executes_pending_migration_once():
    """Execute a pending migration exactly once."""

    migration_path = Path("002_add_indexes.sql")

    migrations = [
        ("002", migration_path, "checksum-two"),
    ]

    applied = {}
    execute_migration = Mock()

    apply_migrations(
        migrations=migrations,
        applied=applied,
        execute_migration=execute_migration,
    )

    execute_migration.assert_called_once_with(
        "002",
        migration_path,
        "checksum-two",
    )


def test_apply_rejects_mismatch_before_executing_anything():
    """Reject checksum mismatches before applying pending migrations."""

    migrations = [
        ("001", Path("001_create_schema.sql"), "checksum-one"),
        ("002", Path("002_add_indexes.sql"), "new-checksum"),
    ]

    applied = {
        "002": "old-checksum",
    }

    execute_migration = Mock()

    with pytest.raises(ValueError, match="Checksum mismatch"):
        apply_migrations(
            migrations=migrations,
            applied=applied,
            execute_migration=execute_migration,
        )

    execute_migration.assert_not_called()


def test_build_migration_sql_wraps_schema_and_history_in_transaction(tmp_path):
    """Schema changes and migration tracking must share one transaction."""
    migration = tmp_path / "002_add_example.sql"
    migration.write_text(
        "CREATE TABLE example (id INTEGER);",
        encoding="utf-8",
    )

    sql = build_migration_sql(
        version="002",
        path=migration,
        checksum="a" * 64,
    )

    assert sql.startswith("BEGIN;")
    assert "CREATE TABLE example (id INTEGER);" in sql
    assert "INSERT INTO schema_migrations" in sql
    assert "'002'" in sql
    assert "'" + ("a" * 64) + "'" in sql
    assert sql.rstrip().endswith("COMMIT;")

    assert sql.index("CREATE TABLE example") < sql.index(
        "INSERT INTO schema_migrations"
    )


@pytest.mark.parametrize(
    "statement",
    [
        "BEGIN;",
        "COMMIT;",
        "ROLLBACK;",
        "START TRANSACTION;",
    ],
)
def test_build_migration_sql_rejects_transaction_control(
    tmp_path,
    statement,
):
    """Migration files must not control their own transactions."""

    migration = tmp_path / "002_invalid.sql"
    migration.write_text(
        f"CREATE TABLE example (id INTEGER);\n{statement}\n",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="Transaction control is not allowed",
    ):
        build_migration_sql(
            version="002",
            path=migration,
            checksum="a" * 64,
        )


def test_execute_postgres_migration_raises_on_sql_failure(tmp_path):
    """Do not silently accept a failed PostgreSQL migration."""

    migration = tmp_path / "002_example.sql"
    migration.write_text(
        "CREATE TABLE example (id INTEGER);",
        encoding="utf-8",
    )

    failed_result = subprocess.CompletedProcess(
        args=[],
        returncode=3,
        stdout="BEGIN\n",
        stderr="ERROR: relation already exists",
    )

    with patch(
        "scripts.manage_migrations.run_psql",
        return_value=failed_result,
    ) as mock_psql:
        with pytest.raises(RuntimeError, match="Migration 002 failed"):
            execute_postgres_migration(
                database="financial_market_test",
                version="002",
                path=migration,
                checksum="a" * 64,
            )

    mock_psql.assert_called_once()


def test_execute_postgres_migration_succeeds(tmp_path):
    """Execute the generated SQL when PostgreSQL reports success."""

    migration = tmp_path / "002_example.sql"
    migration.write_text(
        "CREATE TABLE example (id INTEGER);",
        encoding="utf-8",
    )

    successful_result = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout="BEGIN\nCREATE TABLE\nINSERT 0 1\nCOMMIT\n",
        stderr="",
    )

    with patch(
        "scripts.manage_migrations.run_psql",
        return_value=successful_result,
    ) as mock_psql:
        execute_postgres_migration(
            database="financial_market_test",
            version="002",
            path=migration,
            checksum="a" * 64,
        )

    mock_psql.assert_called_once()

    args, kwargs = mock_psql.call_args

    assert kwargs["database"] == "financial_market_test"

    submitted_sql = kwargs["sql"]
    assert submitted_sql.startswith("BEGIN;")
    assert "CREATE TABLE example (id INTEGER);" in submitted_sql
    assert "INSERT INTO schema_migrations" in submitted_sql
    assert submitted_sql.rstrip().endswith("COMMIT;")


def test_load_migration_history_sql():
    """Load the SQL used to initialize migration tracking."""

    sql = load_migration_history_sql()

    assert "CREATE TABLE IF NOT EXISTS schema_migrations" in sql
    assert "version VARCHAR(100) PRIMARY KEY" in sql
    assert "checksum CHAR(64) NOT NULL" in sql
    assert "ck_schema_migrations_checksum_format" in sql


def test_initialize_migration_history_raises_on_failure():
    """Stop if PostgreSQL cannot initialize migration history."""

    failed_result = subprocess.CompletedProcess(
        args=[],
        returncode=3,
        stdout="",
        stderr="ERROR: permission denied",
    )

    with patch(
        "scripts.manage_migrations.run_psql",
        return_value=failed_result,
    ) as mock_psql:
        with pytest.raises(
            RuntimeError,
            match="Failed to initialize migration history",
        ):
            initialize_migration_history("financial_market_test")

    mock_psql.assert_called_once()


def test_initialize_migration_history_succeeds():
    """Initialize migration history using the expected SQL."""

    successful_result = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout="CREATE TABLE\n",
        stderr="",
    )

    with patch(
        "scripts.manage_migrations.run_psql",
        return_value=successful_result,
    ) as mock_psql:
        initialize_migration_history("financial_market_test")

    mock_psql.assert_called_once()

    _, kwargs = mock_psql.call_args

    assert kwargs["database"] == "financial_market_test"
    assert "CREATE TABLE IF NOT EXISTS schema_migrations" in kwargs["sql"]
    assert "ck_schema_migrations_checksum_format" in kwargs["sql"]


def test_validate_migration_history_rejects_wrong_structure():
    """Reject a migration-history table with an incompatible structure."""

    invalid_result = subprocess.CompletedProcess(
        args=[],
        returncode=0,
        stdout="f\n",
        stderr="",
    )

    with patch(
        "scripts.manage_migrations.run_psql",
        return_value=invalid_result,
    ) as mock_psql:
        with pytest.raises(
            RuntimeError,
            match="Invalid migration history schema",
        ):
            validate_migration_history("financial_market_test")

    mock_psql.assert_called_once()


def test_build_migration_sql_acquires_lock_before_schema_changes(tmp_path):
    """Serialize migration execution within PostgreSQL."""

    migration = tmp_path / "002_example.sql"
    migration.write_text(
        "CREATE TABLE example (id INTEGER);",
        encoding="utf-8",
    )

    sql = build_migration_sql(
        version="002",
        path=migration,
        checksum="a" * 64,
    )

    assert "pg_advisory_xact_lock" in sql

    assert sql.index("pg_advisory_xact_lock") < sql.index(
        "CREATE TABLE example"
    )


def test_build_migration_sql_rechecks_history_after_lock(tmp_path):
    """Recheck migration history after acquiring the database lock."""

    migration = tmp_path / "002_example.sql"
    migration.write_text(
        "CREATE TABLE example (id INTEGER);",
        encoding="utf-8",
    )

    sql = build_migration_sql(
        version="002",
        path=migration,
        checksum="a" * 64,
    )

    lock_position = sql.index("pg_advisory_xact_lock")
    history_position = sql.index("FROM schema_migrations")
    schema_position = sql.index("CREATE TABLE example")

    assert lock_position < history_position < schema_position