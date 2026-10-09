"""Manage versioned PostgreSQL schema migrations."""

import hashlib
import subprocess
from pathlib import Path
from collections.abc import Callable


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = PROJECT_ROOT / "sql" / "migrations"


def discover_migrations() -> list[tuple[str, Path, str]]:
    """Return migration version, file path, and SHA-256 checksum."""

    migrations = []
    seen_versions: set[str] = set()

    for path in sorted(MIGRATIONS_DIR.glob("[0-9]*_*.sql")):
        version = path.name.split("_", maxsplit=1)[0]

        if version in seen_versions:
            raise ValueError(
                f"Duplicate migration version: {version}"
            )

        seen_versions.add(version)

        checksum = hashlib.sha256(path.read_bytes()).hexdigest()
        migrations.append((version, path, checksum))

    return migrations

def migration_status(
    migrations: list[tuple[str, Path, str]],
    applied: dict[str, str],
) -> list[tuple[str, str]]:
    """Classify migrations as applied or pending; reject checksum changes."""

    statuses = []

    for version, path, checksum in migrations:
        if version not in applied:
            statuses.append((version, "pending"))
            continue

        if applied[version] != checksum:
            raise ValueError(
                f"Checksum mismatch for migration {version} ({path.name})"
            )

        statuses.append((version, "applied"))

    return statuses


def run_psql(database: str, sql: str) -> subprocess.CompletedProcess[str]:
    """Execute SQL through PostgreSQL's Docker Compose service."""

    return subprocess.run(
        [
            "docker",
            "compose",
            "exec",
            "-T",
            "postgres",
            "sh",
            "-c",
            'psql -X -v ON_ERROR_STOP=1 '
            '-U "$POSTGRES_USER" '
            '-d "$1" -At',
            "sh",
            database,
        ],
        input=sql,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )

def read_applied_migrations(database: str) -> dict[str, str]:
    """Read applied migration versions and checksums from PostgreSQL."""

    result = run_psql(
        database=database,
        sql="""
            SELECT version, checksum
            FROM schema_migrations
            ORDER BY version;
        """,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Failed to read migration history: {result.stderr.strip()}"
        )

    applied = {}

    for line in result.stdout.splitlines():
        version, checksum = line.split("|", maxsplit=1)
        applied[version] = checksum.strip()

    return applied


def apply_migrations(
    migrations: list[tuple[str, Path, str]],
    applied: dict[str, str],
    execute_migration: Callable[[str, Path, str], None],
) -> None:
    """Execute pending migrations, skipping already-applied versions."""

    # Validate all recorded checksums before executing anything.
    statuses = migration_status(migrations, applied)

    for (version, path, checksum), (_, status) in zip(
        migrations, statuses
    ):
        if status == "applied":
            continue

        execute_migration(version, path, checksum)


def build_migration_sql(
    version: str,
    path: Path,
    checksum: str,
) -> str:
    """Wrap a SQL migration and its history record in one transaction."""

    migration_sql = path.read_text(encoding="utf-8")

    if not version.isdigit():
        raise ValueError("Migration version must contain only digits")

    if len(checksum) != 64 or any(
        character not in "0123456789abcdef"
        for character in checksum
    ):
        raise ValueError("Invalid migration checksum")

    # Transaction control belongs to the migration runner.
    # This initial check rejects standalone BEGIN/COMMIT/ROLLBACK lines.
    transaction_statements = {
        "BEGIN",
        "COMMIT",
        "ROLLBACK",
        "START TRANSACTION",
    }

    for line in migration_sql.splitlines():
        statement = line.strip().rstrip(";").upper()

        if statement in transaction_statements:
            raise ValueError(
                f"Transaction control is not allowed in {path.name}"
            )

    return (
        "BEGIN;\n"
        "SELECT pg_advisory_xact_lock(2026, 21);\n"
        "DO $$\n"
        "BEGIN\n"
        "    IF EXISTS (\n"
        "        SELECT 1 FROM schema_migrations\n"
        f"        WHERE version = '{version}'\n"
        f"          AND checksum <> '{checksum}'\n"
        "    ) THEN\n"
        "        RAISE EXCEPTION 'Migration checksum mismatch';\n"
        "    END IF;\n"
        "END;\n"
        "$$;\n"
        "SELECT NOT EXISTS (\n"
        "    SELECT 1 FROM schema_migrations\n"
        f"    WHERE version = '{version}'\n"
        ") AS should_apply \\gset\n"
        "\\if :should_apply\n"
        f"{migration_sql}\n"
        "INSERT INTO schema_migrations (version, checksum)\n"
        f"VALUES ('{version}', '{checksum}');\n"
        "\\endif\n"
        "COMMIT;\n"
    )


def execute_postgres_migration(
    database: str,
    version: str,
    path: Path,
    checksum: str,
) -> None:
    """Execute a migration and record its version atomically."""

    sql = build_migration_sql(
        version=version,
        path=path,
        checksum=checksum,
    )

    result = run_psql(
        database=database,
        sql=sql,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Migration {version} failed: {result.stderr.strip()}"
        )


def load_migration_history_sql() -> str:
    """Load the SQL used to initialize the migration-history table."""

    path = PROJECT_ROOT / "sql" / "create_migration_history.sql"

    return path.read_text(encoding="utf-8")


def initialize_migration_history(database: str) -> None:
    """Initialize the migration-history table in PostgreSQL."""

    sql = load_migration_history_sql()

    result = run_psql(
        database=database,
        sql=sql,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Failed to initialize migration history: "
            f"{result.stderr.strip()}"
        )


def validate_migration_history(database: str) -> None:
    """Reject a missing or structurally incompatible history table."""

    sql = """
        SELECT
            (
                SELECT COUNT(*) = 3
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'schema_migrations'
            )
            AND EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'schema_migrations'
                  AND column_name = 'version'
                  AND data_type = 'character varying'
                  AND character_maximum_length = 100
                  AND is_nullable = 'NO'
            )
            AND EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'schema_migrations'
                  AND column_name = 'checksum'
                  AND data_type = 'character'
                  AND character_maximum_length = 64
                  AND is_nullable = 'NO'
            )
            AND EXISTS (
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'schema_migrations'
                  AND column_name = 'applied_at'
                  AND data_type = 'timestamp with time zone'
                  AND is_nullable = 'NO'
                  AND column_default IS NOT NULL
            )
            AND EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conrelid = 'public.schema_migrations'::regclass
                AND conname = 'schema_migrations_pkey'
                AND contype = 'p'
                AND convalidated
                AND pg_get_constraintdef(oid) = 'PRIMARY KEY (version)'
            )
            AND EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conrelid = 'public.schema_migrations'::regclass
                AND conname = 'ck_schema_migrations_checksum_format'
                AND contype = 'c'
                AND convalidated
                AND pg_get_constraintdef(oid) =
                    'CHECK ((checksum ~ ''^[0-9a-f]{64}$''::text))'
            );
    """

    result = run_psql(database=database, sql=sql)

    if result.returncode != 0 or result.stdout.strip() != "t":
        raise RuntimeError(
            "Invalid migration history schema: "
            + (result.stderr.strip() or "structure check failed")
        )


if __name__ == "__main__":
    import argparse
    from functools import partial

    parser = argparse.ArgumentParser(
        description="Manage PostgreSQL schema migrations."
    )
    parser.add_argument(
        "command",
        choices=["status", "apply"],
        help="Migration management command.",
    )
    parser.add_argument(
        "--database",
        required=True,
        help="Target PostgreSQL database.",
    )

    args = parser.parse_args()

    migrations = discover_migrations()
    applied = read_applied_migrations(args.database)

    if args.command == "status":
        statuses = migration_status(migrations, applied)

        for version, status in statuses:
            print(f"{version} | {status}")

    elif args.command == "apply":
        apply_migrations(
            migrations=migrations,
            applied=applied,
            execute_migration=partial(
                execute_postgres_migration,
                args.database,
            ),
        )
        print("Migration application completed.")