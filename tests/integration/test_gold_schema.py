import os
import psycopg
import subprocess
import pytest
from datetime import date, datetime, timezone
from decimal import Decimal
from dataclasses import replace
from scripts.manage_migrations import (
    discover_migrations,
    migration_status,
    read_applied_migrations,
    run_psql,
    execute_postgres_migration,
    validate_migration_history,
)
from financial_data_platform.models.market_data import MarketDataRecord
from financial_data_platform.storage.silver import SilverWriter
from concurrent.futures import ThreadPoolExecutor
from financial_data_platform.warehouse.db import connect_to_database
from financial_data_platform.warehouse.gold_loader import (
    ensure_asset,
    ensure_date,
    insert_market_fact,
    load_market_records,
    load_silver_file,
)

def run_test_sql(sql: str) -> subprocess.CompletedProcess[str]:
    """Execute SQL against the isolated PostgreSQL test database."""
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
            '-d financial_market_test -At',
        ],
        input=sql,
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )


@pytest.mark.integration
def test_gold_warehouse_tables_exist():
    """Verify that the test database contains the four Gold tables."""

    sql = """
        SELECT tablename
        FROM pg_tables
        WHERE schemaname = 'public'
        ORDER BY tablename;
    """

    result = run_test_sql(sql)
    assert result.returncode == 0, result.stderr

    actual_tables = set(result.stdout.strip().splitlines())

    assert {
        "dim_asset",
        "dim_date",
        "fact_market_metrics",
        "pipeline_run",
    }.issubset(actual_tables)


@pytest.mark.integration
def test_gold_rejects_negative_trading_volume():
    """Verify PostgreSQL rejects a negative volume."""

    sql = """
        BEGIN;

        INSERT INTO dim_asset (source, symbol)
        VALUES ('twelve_data', 'AAPL');

        INSERT INTO dim_date (
            date_key, full_date, day, month, quarter, year, day_of_week
        )
        VALUES (
            20261005, '2026-10-05', 5, 10, 4, 2026, 1
        );

        INSERT INTO fact_market_metrics (
            asset_key,
            date_key,
            open,
            high,
            low,
            close,
            volume,
            extracted_at
        )
        VALUES (
            (SELECT asset_key FROM dim_asset
             WHERE source = 'twelve_data' AND symbol = 'AAPL'),
            20261005,
            250.00,
            255.00,
            249.00,
            254.00,
            -100,
            '2026-10-06T18:30:00+00'
        );

        ROLLBACK;
    """

    result = run_test_sql(sql)

    assert result.returncode != 0
    assert (
        "ck_fact_market_metrics_nonnegative_volume"
        in result.stderr
    )


@pytest.mark.integration
def test_gold_rejects_duplicate_daily_market_facts():
    """Reject two market observations for the same asset and date."""

    sql = """
        BEGIN;

        INSERT INTO dim_asset (source, symbol)
        VALUES ('test_provider', 'DUPLICATE_TEST');

        INSERT INTO dim_date (
            date_key, full_date, day, month, quarter, year, day_of_week
        )
        VALUES (20261005, '2026-10-05', 5, 10, 4, 2026, 1);

        INSERT INTO fact_market_metrics (
            asset_key, date_key,
            open, high, low, close, volume, extracted_at
        )
        VALUES (
            (SELECT asset_key FROM dim_asset
             WHERE source = 'test_provider'
               AND symbol = 'DUPLICATE_TEST'),
            20261005,
            250.00, 255.00, 249.00, 254.00, 1000,
            '2026-10-06T18:30:00+00'
        );

        INSERT INTO fact_market_metrics (
            asset_key, date_key,
            open, high, low, close, volume, extracted_at
        )
        VALUES (
            (SELECT asset_key FROM dim_asset
             WHERE source = 'test_provider'
               AND symbol = 'DUPLICATE_TEST'),
            20261005,
            250.00, 255.00, 249.00, 254.00, 1000,
            '2026-10-06T18:30:00+00'
        );

        ROLLBACK;
    """

    result = run_test_sql(sql)

    assert result.returncode != 0
    assert "pk_fact_market_metrics" in result.stderr


@pytest.mark.integration
def test_gold_rejects_fact_with_unknown_asset():
    """A market fact must reference an existing asset."""

    sql = """
        BEGIN;

        INSERT INTO dim_date (
            date_key, full_date, day, month, quarter, year, day_of_week
        )
        VALUES (20261005, '2026-10-05', 5, 10, 4, 2026, 1);

        INSERT INTO fact_market_metrics (
            asset_key,
            date_key,
            open,
            high,
            low,
            close,
            volume,
            extracted_at
        )
        VALUES (
            -1,
            20261005,
            250.00,
            255.00,
            249.00,
            254.00,
            1000,
            '2026-10-06T18:30:00+00'
        );

        ROLLBACK;
    """

    result = run_test_sql(sql)

    assert result.returncode != 0
    assert "fk_fact_market_metrics_asset" in result.stderr


@pytest.mark.integration
def test_gold_rejects_close_above_daily_high():
    """Reject a closing price outside the daily low-high range."""

    sql = """
        BEGIN;

        INSERT INTO dim_asset (source, symbol)
        VALUES ('test_provider', 'PRICE_TEST');

        INSERT INTO dim_date (
            date_key, full_date, day, month, quarter, year, day_of_week
        )
        VALUES (20261005, '2026-10-05', 5, 10, 4, 2026, 1);

        INSERT INTO fact_market_metrics (
            asset_key,
            date_key,
            open,
            high,
            low,
            close,
            volume,
            extracted_at
        )
        VALUES (
            (SELECT asset_key
             FROM dim_asset
             WHERE source = 'test_provider'
               AND symbol = 'PRICE_TEST'),
            20261005,
            250.00,
            255.00,
            249.00,
            260.00,
            1000,
            '2026-10-06T18:30:00+00'
        );

        ROLLBACK;
    """

    result = run_test_sql(sql)

    assert result.returncode != 0
    assert "ck_fact_market_metrics_price_range" in result.stderr

@pytest.mark.integration
@pytest.mark.parametrize(
    "open_price, high_price, low_price, close_price, expected_constraint",
    [
        (-1, 255, 249, 254, "ck_fact_market_metrics_positive_prices"),
        (250, 255, 249, 0, "ck_fact_market_metrics_positive_prices"),
        (250, 240, 249, 239, "ck_fact_market_metrics_price_range"),
    ],
)
def test_gold_rejects_invalid_ohlc_values(
    open_price,
    high_price,
    low_price,
    close_price,
    expected_constraint,
):
    """Reject invalid OHLC observations at the database boundary."""

    sql = f"""
        BEGIN;

        INSERT INTO dim_asset (source, symbol)
        VALUES ('test_provider', 'OHLC_TEST');

        INSERT INTO dim_date (
            date_key, full_date, day, month, quarter, year, day_of_week
        )
        VALUES (20261005, '2026-10-05', 5, 10, 4, 2026, 1);

        INSERT INTO fact_market_metrics (
            asset_key, date_key,
            open, high, low, close, volume, extracted_at
        )
        VALUES (
            (SELECT asset_key FROM dim_asset
             WHERE source = 'test_provider'
               AND symbol = 'OHLC_TEST'),
            20261005,
            {open_price}, {high_price}, {low_price}, {close_price},
            1000,
            '2026-10-06T18:30:00+00'
        );

        ROLLBACK;
    """

    result = run_test_sql(sql)

    assert result.returncode != 0
    assert expected_constraint in result.stderr

@pytest.mark.integration
def test_gold_rejects_inconsistent_date_key():
    """Reject a date key that disagrees with the calendar date."""

    sql = """
        BEGIN;

        INSERT INTO dim_date (
            date_key,
            full_date,
            day,
            month,
            quarter,
            year,
            day_of_week
        )
        VALUES (
            20261006,
            '2026-10-05',
            5,
            10,
            4,
            2026,
            1
        );

        ROLLBACK;
    """

    result = run_test_sql(sql)

    assert result.returncode != 0
    assert "ck_dim_date_key_consistency" in result.stderr

@pytest.mark.integration
def test_gold_rejects_inconsistent_calendar_attributes():
    """Reject calendar attributes that disagree with full_date."""

    sql = """
        BEGIN;

        INSERT INTO dim_date (
            date_key,
            full_date,
            day,
            month,
            quarter,
            year,
            day_of_week
        )
        VALUES (
            20261005,
            '2026-10-05',
            5,
            11,
            4,
            2026,
            1
        );

        ROLLBACK;
    """

    result = run_test_sql(sql)

    assert result.returncode != 0
    assert "ck_dim_date_calendar_consistency" in result.stderr

@pytest.mark.integration
def test_gold_rejects_invalid_pipeline_status():
    """Reject an execution status outside the allowed values."""

    sql = """
        BEGIN;

        INSERT INTO pipeline_run (
            run_id,
            started_at,
            status
        )
        VALUES (
            '11111111-1111-4111-8111-111111111111',
            '2026-10-09T10:00:00+00',
            'completed'
        );

        ROLLBACK;
    """

    result = run_test_sql(sql)

    assert result.returncode != 0
    assert "ck_pipeline_run_status" in result.stderr


@pytest.mark.integration
@pytest.mark.parametrize(
    "counter",
    [
        "records_extracted",
        "records_validated",
        "records_transformed",
        "records_loaded",
        "records_rejected",
    ],
)
def test_gold_rejects_negative_pipeline_counters(counter):
    """Reject negative values in every pipeline record counter."""

    sql = f"""
        BEGIN;

        INSERT INTO pipeline_run (
            run_id,
            started_at,
            status,
            {counter}
        )
        VALUES (
            '22222222-2222-4222-8222-222222222222',
            '2026-10-09T10:00:00+00',
            'running',
            -1
        );

        ROLLBACK;
    """

    result = run_test_sql(sql)

    assert result.returncode != 0
    assert "ck_pipeline_run_counters_nonnegative" in result.stderr


@pytest.mark.integration
def test_gold_rejects_pipeline_finish_before_start():
    """Reject a pipeline run that finishes before it starts."""

    sql = """
        BEGIN;

        INSERT INTO pipeline_run (
            run_id,
            started_at,
            finished_at,
            status
        )
        VALUES (
            '33333333-3333-4333-8333-333333333333',
            '2026-10-09T10:00:00+00',
            '2026-10-09T09:00:00+00',
            'failed'
        );

        ROLLBACK;
    """

    result = run_test_sql(sql)

    assert result.returncode != 0
    assert "ck_pipeline_run_time_order" in result.stderr

@pytest.mark.integration
def test_gold_rejects_negative_pipeline_duration():
    """Reject a negative pipeline execution duration."""

    sql = """
        BEGIN;

        INSERT INTO pipeline_run (
            run_id,
            started_at,
            status,
            duration_seconds
        )
        VALUES (
            '44444444-4444-4444-8444-444444444444',
            '2026-10-09T10:00:00+00',
            'failed',
            -5.000
        );

        ROLLBACK;
    """

    result = run_test_sql(sql)

    assert result.returncode != 0
    assert "ck_pipeline_run_duration_nonnegative" in result.stderr


@pytest.mark.integration
def test_migration_runner_connects_to_test_database():
    """Verify that the migration runner connects to the requested database."""

    result = run_psql(
        database="financial_market_test",
        sql="SELECT current_database();",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "financial_market_test"


@pytest.mark.integration
def test_initial_gold_migration_is_registered():
    """Verify that migration 001 is registered with its file checksum."""

    migrations = discover_migrations()
    version, _, expected_checksum = migrations[0]

    result = run_psql(
        database="financial_market_test",
        sql="""
            SELECT version, checksum
            FROM schema_migrations
            WHERE version = '001';
        """,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"{version}|{expected_checksum}"


@pytest.mark.integration
def test_migration_runner_reads_applied_migrations():
    """Read migration history from the isolated test database."""

    applied = read_applied_migrations("financial_market_test")
    migrations = discover_migrations()

    version, _, expected_checksum = migrations[0]

    assert applied == {
        version: expected_checksum,
    }


@pytest.mark.integration
def test_migration_status_rejects_changed_migration():
    """Reject a migration whose checksum differs from database history."""

    applied = read_applied_migrations("financial_market_test")
    migrations = discover_migrations()

    version, path, checksum = migrations[0]

    changed_migrations = [
        (version, path, "0" * 64),
    ]

    with pytest.raises(ValueError, match="Checksum mismatch"):
        migration_status(changed_migrations, applied)


@pytest.mark.integration
def test_migration_transaction_rolls_back_on_sql_error():
    """A failed transaction must not leave partially created tables."""

    result = run_psql(
        database="financial_market_test",
        sql="""
            BEGIN;

            CREATE TABLE migration_rollback_probe (
                id INTEGER PRIMARY KEY
            );

            SELECT 1 / 0;

            COMMIT;
        """,
    )

    assert result.returncode != 0
    assert "division by zero" in result.stderr

    check = run_psql(
        database="financial_market_test",
        sql="""
            SELECT to_regclass(
                'public.migration_rollback_probe'
            );
        """,
    )

    assert check.returncode == 0, check.stderr
    assert check.stdout.strip() == ""


@pytest.mark.integration
def test_failed_migration_does_not_change_schema_or_history(tmp_path):
    """Rollback both schema changes and history on migration failure."""

    migration = tmp_path / "999_rollback_probe.sql"
    migration.write_text(
        """
        CREATE TABLE migration_failure_probe (
            id INTEGER PRIMARY KEY
        );

        SELECT 1 / 0;
        """,
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Migration 999 failed"):
        execute_postgres_migration(
            database="financial_market_test",
            version="999",
            path=migration,
            checksum="a" * 64,
        )

    verification = run_psql(
        database="financial_market_test",
        sql="""
            SELECT
                to_regclass('public.migration_failure_probe') IS NULL,
                NOT EXISTS (
                    SELECT 1
                    FROM schema_migrations
                    WHERE version = '999'
                );
        """,
    )

    assert verification.returncode == 0, verification.stderr
    assert verification.stdout.strip() == "t|t"


@pytest.mark.integration
def test_successful_migration_records_schema_and_history(tmp_path):
    """A successful migration creates its schema and history record."""

    migration = tmp_path / "998_success_probe.sql"
    migration.write_text(
        """
        CREATE TABLE migration_success_probe (
            id INTEGER PRIMARY KEY
        );
        """,
        encoding="utf-8",
    )

    try:
        execute_postgres_migration(
            database="financial_market_test",
            version="998",
            path=migration,
            checksum="b" * 64,
        )

        verification = run_psql(
            database="financial_market_test",
            sql="""
                SELECT
                    to_regclass('public.migration_success_probe')
                        IS NOT NULL,
                    EXISTS (
                        SELECT 1
                        FROM schema_migrations
                        WHERE version = '998'
                          AND checksum = repeat('b', 64)
                    );
            """,
        )

        assert verification.returncode == 0, verification.stderr
        assert verification.stdout.strip() == "t|t"

    finally:
        cleanup = run_psql(
            database="financial_market_test",
            sql="""
                BEGIN;
                DROP TABLE IF EXISTS migration_success_probe;
                DELETE FROM schema_migrations
                WHERE version = '998'
                  AND checksum = repeat('b', 64);
                COMMIT;
            """,
        )

        assert cleanup.returncode == 0, cleanup.stderr


@pytest.mark.integration
def test_migration_history_schema_is_valid():
    """Verify the real migration-history table has the expected structure."""

    validate_migration_history("financial_market_test")


@pytest.mark.integration
def test_sql_executor_skips_already_applied_migration(tmp_path):
    """The SQL executor must skip a migration already in history."""

    migration = tmp_path / "001_should_not_execute.sql"
    migration.write_text(
        """
        CREATE TABLE migration_unexpected_execution_probe (
            id INTEGER PRIMARY KEY
        );
        """,
        encoding="utf-8",
    )

    applied = read_applied_migrations("financial_market_migration_test")
    original_checksum = applied["001"]

    # Supply the checksum already registered for version 001.
    # PostgreSQL should skip the SQL file entirely.
    execute_postgres_migration(
        database="financial_market_migration_test",
        version="001",
        path=migration,
        checksum=original_checksum,
    )

    result = run_psql(
        database="financial_market_migration_test",
        sql="""
            SELECT to_regclass(
                'public.migration_unexpected_execution_probe'
            );
        """,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == ""


@pytest.mark.integration
def test_sql_executor_rejects_checksum_mismatch(tmp_path):
    """Reject a changed migration inside the locked transaction."""

    migration = tmp_path / "001_changed.sql"
    migration.write_text(
        """
        CREATE TABLE migration_checksum_mismatch_probe (
            id INTEGER PRIMARY KEY
        );
        """,
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Migration 001 failed"):
        execute_postgres_migration(
            database="financial_market_migration_test",
            version="001",
            path=migration,
            checksum="0" * 64,
        )

    verification = run_psql(
        database="financial_market_migration_test",
        sql="""
            SELECT
                to_regclass(
                    'public.migration_checksum_mismatch_probe'
                ) IS NULL,
                (
                    SELECT COUNT(*)
                    FROM schema_migrations
                    WHERE version = '001'
                ) = 1;
        """,
    )

    assert verification.returncode == 0, verification.stderr
    assert verification.stdout.strip() == "t|t"


@pytest.mark.integration
def test_concurrent_migration_attempts_apply_once(tmp_path):
    """Two concurrent attempts must apply the same migration only once."""

    database = "financial_market_migration_test"
    version = "997"
    checksum = "c" * 64

    migration = tmp_path / "997_concurrency_probe.sql"
    migration.write_text(
        """
        CREATE TABLE migration_concurrency_probe (
            id INTEGER PRIMARY KEY
        );
        """,
        encoding="utf-8",
    )

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                executor.submit(
                    execute_postgres_migration,
                    database,
                    version,
                    migration,
                    checksum,
                )
                for _ in range(2)
            ]

            for future in futures:
                future.result()

        verification = run_psql(
            database=database,
            sql="""
                SELECT
                    to_regclass('public.migration_concurrency_probe')
                        IS NOT NULL,
                    (
                        SELECT COUNT(*)
                        FROM schema_migrations
                        WHERE version = '997'
                    ) = 1;
            """,
        )

        assert verification.returncode == 0, verification.stderr
        assert verification.stdout.strip() == "t|t"

    finally:
        cleanup = run_psql(
            database=database,
            sql="""
                BEGIN;
                DROP TABLE IF EXISTS migration_concurrency_probe;
                DELETE FROM schema_migrations
                WHERE version = '997'
                  AND checksum = repeat('c', 64);
                COMMIT;
            """,
        )

        assert cleanup.returncode == 0, cleanup.stderr


@pytest.mark.integration
def test_gold_loader_connects_to_postgresql(monkeypatch):
    """Connect to the isolated Gold warehouse test database."""

    # Requires POSTGRES_PASSWORD in the test process environment.
    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    with connect_to_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database();")
            database_name = cursor.fetchone()[0]

    assert database_name == "financial_market_test"


@pytest.mark.integration
def test_ensure_asset_is_idempotent():
    """Repeated asset loading must return the same key without duplicates."""

    with connect_to_database() as connection:
        with connection.cursor() as cursor:
            try:
                first_key = ensure_asset(
                    cursor,
                    source="integration_test",
                    symbol="TEST_ASSET_23",
                )

                second_key = ensure_asset(
                    cursor,
                    source="integration_test",
                    symbol="TEST_ASSET_23",
                )

                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM dim_asset
                    WHERE source = %s AND symbol = %s;
                    """,
                    ("integration_test", "TEST_ASSET_23"),
                )

                count = cursor.fetchone()[0]

                assert first_key == second_key
                assert count == 1

            finally:
                connection.rollback()



@pytest.mark.integration
def test_ensure_date_is_idempotent(monkeypatch):
    """Repeated date loading must not create duplicate calendar rows."""

    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    with connect_to_database() as connection:
        try:
            with connection.cursor() as cursor:
                first_key = ensure_date(cursor, date(2026, 10, 9))
                second_key = ensure_date(cursor, date(2026, 10, 9))

                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM dim_date
                    WHERE date_key = %s;
                    """,
                    (20261009,),
                )

                count = cursor.fetchone()[0]

                assert first_key == second_key == 20261009
                assert count == 1

        finally:
            connection.rollback()


@pytest.mark.integration
def test_insert_market_fact_preserves_decimal_precision(monkeypatch):
    """Insert an OHLCV fact without losing decimal precision."""

    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    record = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 9),
        open=Decimal("250.12345678"),
        high=Decimal("255.00000000"),
        low=Decimal("248.50000000"),
        close=Decimal("253.87654321"),
        volume=1234567,
        source="integration_test",
        extracted_at=datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc),
    )

    with connect_to_database() as connection:
        try:
            with connection.cursor() as cursor:
                asset_key = ensure_asset(
                    cursor,
                    source=record.source,
                    symbol=record.symbol,
                )
                ensure_date(cursor, record.observation_date)
                insert_market_fact(cursor, record, asset_key)

                cursor.execute(
                    """
                    SELECT open, high, low, close, volume, extracted_at
                    FROM fact_market_metrics
                    WHERE asset_key = %s AND date_key = %s;
                    """,
                    (asset_key, 20261009),
                )

                actual = cursor.fetchone()

                assert actual == (
                    record.open,
                    record.high,
                    record.low,
                    record.close,
                    record.volume,
                    record.extracted_at,
                )

        finally:
            connection.rollback()



@pytest.mark.integration
def test_identical_market_fact_retry_is_unchanged(monkeypatch):
    """Loading an identical fact twice must not create a duplicate."""

    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    record = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 9),
        open=Decimal("250.12345678"),
        high=Decimal("255.00000000"),
        low=Decimal("248.50000000"),
        close=Decimal("253.87654321"),
        volume=1234567,
        source="integration_test",
        extracted_at=datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc),
    )

    with connect_to_database() as connection:
        try:
            with connection.cursor() as cursor:
                asset_key = ensure_asset(
                    cursor,
                    source=record.source,
                    symbol=record.symbol,
                )
                ensure_date(cursor, record.observation_date)

                first_action = insert_market_fact(cursor, record, asset_key)
                second_action = insert_market_fact(cursor, record, asset_key)

                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM fact_market_metrics
                    WHERE asset_key = %s AND date_key = %s;
                    """,
                    (asset_key, 20261009),
                )

                assert first_action == "insert"
                assert second_action == "unchanged"
                assert cursor.fetchone()[0] == 1

        finally:
            connection.rollback()



@pytest.mark.integration
def test_newer_market_fact_updates_existing_prices(monkeypatch):
    """Newer corrected prices should update the existing Gold fact."""

    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    original = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 9),
        open=Decimal("250.00000000"),
        high=Decimal("255.00000000"),
        low=Decimal("248.00000000"),
        close=Decimal("253.00000000"),
        volume=1000000,
        source="integration_test",
        extracted_at=datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    )

    corrected = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 9),
        open=Decimal("250.00000000"),
        high=Decimal("255.00000000"),
        low=Decimal("248.00000000"),
        close=Decimal("254.50000000"),
        volume=1000000,
        source="integration_test",
        extracted_at=datetime(
            2026, 10, 9, 19, 0, tzinfo=timezone.utc
        ),
    )

    with connect_to_database() as connection:
        try:
            with connection.cursor() as cursor:
                asset_key = ensure_asset(
                    cursor,
                    source=original.source,
                    symbol=original.symbol,
                )
                ensure_date(cursor, original.observation_date)

                first_action = insert_market_fact(
                    cursor, original, asset_key
                )
                second_action = insert_market_fact(
                    cursor, corrected, asset_key
                )

                cursor.execute(
                    """
                    SELECT close, extracted_at
                    FROM fact_market_metrics
                    WHERE asset_key = %s AND date_key = %s;
                    """,
                    (asset_key, 20261009),
                )

                stored = cursor.fetchone()

                assert first_action == "insert"
                assert second_action == "update"
                assert stored == (
                    corrected.close,
                    corrected.extracted_at,
                )

        finally:
            connection.rollback()



@pytest.mark.integration
def test_older_market_fact_does_not_overwrite_newer_data(monkeypatch):
    """An older extraction must not overwrite a newer Gold fact."""

    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    newer = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 9),
        open=Decimal("250.00000000"),
        high=Decimal("255.00000000"),
        low=Decimal("248.00000000"),
        close=Decimal("254.50000000"),
        volume=1000000,
        source="integration_test",
        extracted_at=datetime(
            2026, 10, 9, 19, 0, tzinfo=timezone.utc
        ),
    )

    older = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 9),
        open=Decimal("250.00000000"),
        high=Decimal("255.00000000"),
        low=Decimal("248.00000000"),
        close=Decimal("253.00000000"),
        volume=1000000,
        source="integration_test",
        extracted_at=datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    )

    with connect_to_database() as connection:
        try:
            with connection.cursor() as cursor:
                asset_key = ensure_asset(
                    cursor,
                    source=newer.source,
                    symbol=newer.symbol,
                )
                ensure_date(cursor, newer.observation_date)

                first_action = insert_market_fact(
                    cursor, newer, asset_key
                )
                second_action = insert_market_fact(
                    cursor, older, asset_key
                )

                cursor.execute(
                    """
                    SELECT close, extracted_at
                    FROM fact_market_metrics
                    WHERE asset_key = %s AND date_key = %s;
                    """,
                    (asset_key, 20261009),
                )
                stored = cursor.fetchone()

                assert first_action == "insert"
                assert second_action == "unchanged"
                assert stored == (
                    newer.close,
                    newer.extracted_at,
                )

        finally:
            connection.rollback()


@pytest.mark.integration
def test_equal_timestamp_conflict_rejects_changed_prices(monkeypatch):
    """Reject conflicting prices with identical extraction timestamps."""

    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    original = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 9),
        open=Decimal("250.00000000"),
        high=Decimal("255.00000000"),
        low=Decimal("248.00000000"),
        close=Decimal("253.00000000"),
        volume=1000000,
        source="integration_test",
        extracted_at=datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    )

    conflicting = MarketDataRecord(
        symbol="AAPL",
        observation_date=date(2026, 10, 9),
        open=Decimal("250.00000000"),
        high=Decimal("255.00000000"),
        low=Decimal("248.00000000"),
        close=Decimal("254.50000000"),
        volume=1000000,
        source="integration_test",
        extracted_at=original.extracted_at,
    )

    with connect_to_database() as connection:
        try:
            with connection.cursor() as cursor:
                asset_key = ensure_asset(
                    cursor,
                    source=original.source,
                    symbol=original.symbol,
                )
                ensure_date(cursor, original.observation_date)

                first_action = insert_market_fact(
                    cursor, original, asset_key
                )
                second_action = insert_market_fact(
                    cursor, conflicting, asset_key
                )

                cursor.execute(
                    """
                    SELECT close, extracted_at
                    FROM fact_market_metrics
                    WHERE asset_key = %s AND date_key = %s;
                    """,
                    (asset_key, 20261009),
                )

                stored = cursor.fetchone()

                assert first_action == "insert"
                assert second_action == "reject"
                assert stored == (
                    original.close,
                    original.extracted_at,
                )

        finally:
            connection.rollback()


@pytest.mark.integration
def test_gold_batch_rolls_back_all_records_on_database_error(monkeypatch):
    """An invalid fact must roll back earlier successful inserts."""

    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    valid = MarketDataRecord(
        symbol="ROLLBACK23",
        observation_date=date(2026, 10, 8),
        open=Decimal("100.00000000"),
        high=Decimal("105.00000000"),
        low=Decimal("98.00000000"),
        close=Decimal("102.00000000"),
        volume=1000,
        source="integration_test",
        extracted_at=datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc),
    )

    invalid = replace(
        valid,
        observation_date=date(2026, 10, 9),
        volume=-1,
    )

    with pytest.raises(psycopg.errors.CheckViolation):
        load_market_records([valid, invalid])

    # Use a new connection to inspect the committed database state.
    with connect_to_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM dim_asset
                WHERE source = %s AND symbol = %s;
                """,
                ("integration_test", "ROLLBACK23"),
            )
            assert cursor.fetchone()[0] == 0


@pytest.mark.integration
def test_gold_batch_commits_valid_market_records(monkeypatch):
    """Commit valid records and report accurate insertion counts."""

    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    first = MarketDataRecord(
        symbol="BATCH23",
        observation_date=date(2026, 10, 8),
        open=Decimal("100.00000000"),
        high=Decimal("105.00000000"),
        low=Decimal("98.00000000"),
        close=Decimal("102.00000000"),
        volume=1000,
        source="integration_test",
        extracted_at=datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc),
    )

    second = replace(
        first,
        observation_date=date(2026, 10, 9),
        close=Decimal("103.00000000"),
    )

    try:
        counts = load_market_records([first, second])

        assert counts == {
            "inserted": 2,
            "updated": 0,
            "unchanged": 0,
            "rejected": 0,
        }

        with connect_to_database() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM fact_market_metrics AS f
                    JOIN dim_asset AS a
                        ON a.asset_key = f.asset_key
                    WHERE a.source = %s
                      AND a.symbol = %s;
                    """,
                    ("integration_test", "BATCH23"),
                )

                assert cursor.fetchone()[0] == 2

    finally:
        # Remove only records belonging to this integration-test asset.
        with connect_to_database() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM fact_market_metrics
                    WHERE asset_key IN (
                        SELECT asset_key
                        FROM dim_asset
                        WHERE source = %s AND symbol = %s
                    );
                    """,
                    ("integration_test", "BATCH23"),
                )

                cursor.execute(
                    """
                    DELETE FROM dim_asset
                    WHERE source = %s AND symbol = %s;
                    """,
                    ("integration_test", "BATCH23"),
                )


@pytest.mark.integration
def test_gold_batch_retry_is_idempotent(monkeypatch):
    """Retrying an identical batch must not duplicate Gold facts."""

    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    first = MarketDataRecord(
        symbol="RETRY23",
        observation_date=date(2026, 10, 8),
        open=Decimal("100.00000000"),
        high=Decimal("105.00000000"),
        low=Decimal("98.00000000"),
        close=Decimal("102.00000000"),
        volume=1000,
        source="integration_test",
        extracted_at=datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc),
    )

    second = replace(
        first,
        observation_date=date(2026, 10, 9),
        close=Decimal("103.00000000"),
    )

    try:
        first_counts = load_market_records([first, second])
        retry_counts = load_market_records([first, second])

        assert first_counts == {
            "inserted": 2,
            "updated": 0,
            "unchanged": 0,
            "rejected": 0,
        }

        assert retry_counts == {
            "inserted": 0,
            "updated": 0,
            "unchanged": 2,
            "rejected": 0,
        }

        with connect_to_database() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM fact_market_metrics AS f
                    JOIN dim_asset AS a
                        ON a.asset_key = f.asset_key
                    WHERE a.source = %s
                      AND a.symbol = %s;
                    """,
                    ("integration_test", "RETRY23"),
                )

                assert cursor.fetchone()[0] == 2

    finally:
        with connect_to_database() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM fact_market_metrics
                    WHERE asset_key IN (
                        SELECT asset_key
                        FROM dim_asset
                        WHERE source = %s AND symbol = %s
                    );
                    """,
                    ("integration_test", "RETRY23"),
                )

                cursor.execute(
                    """
                    DELETE FROM dim_asset
                    WHERE source = %s AND symbol = %s;
                    """,
                    ("integration_test", "RETRY23"),
                )


@pytest.mark.integration
def test_gold_batch_newer_correction_updates_committed_fact(monkeypatch):
    """A newer extraction updates a previously committed Gold fact."""

    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    first = MarketDataRecord(
        symbol="CORRECT23",
        observation_date=date(2026, 10, 8),
        open=Decimal("100.00000000"),
        high=Decimal("105.00000000"),
        low=Decimal("98.00000000"),
        close=Decimal("102.00000000"),
        volume=1000,
        source="integration_test",
        extracted_at=datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc),
    )

    second = replace(
        first,
        observation_date=date(2026, 10, 9),
        close=Decimal("103.00000000"),
    )

    corrected = replace(
        second,
        close=Decimal("104.50000000"),
        extracted_at=datetime(
            2026, 10, 9, 19, 0, tzinfo=timezone.utc
        ),
    )

    try:
        first_counts = load_market_records([first, second])
        correction_counts = load_market_records([corrected])

        assert first_counts == {
            "inserted": 2,
            "updated": 0,
            "unchanged": 0,
            "rejected": 0,
        }

        assert correction_counts == {
            "inserted": 0,
            "updated": 1,
            "unchanged": 0,
            "rejected": 0,
        }

        conflicting = replace(
            corrected,
            close=Decimal("104.75000000"),
        )

        conflict_counts = load_market_records([conflicting])

        assert conflict_counts == {
            "inserted": 0,
            "updated": 0,
            "unchanged": 0,
            "rejected": 1,
        }

        with connect_to_database() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM fact_market_metrics AS f
                    JOIN dim_asset AS a
                        ON a.asset_key = f.asset_key
                    WHERE a.source = %s
                      AND a.symbol = %s;
                    """,
                    ("integration_test", "CORRECT23"),
                )

                assert cursor.fetchone()[0] == 2

                cursor.execute(
                    """
                    SELECT f.close, f.extracted_at
                    FROM fact_market_metrics AS f
                    JOIN dim_asset AS a
                        ON a.asset_key = f.asset_key
                    WHERE a.source = %s
                    AND a.symbol = %s
                    AND f.date_key = %s;
                    """,
                    ("integration_test", "CORRECT23", 20261009),
                )

                stored_close, stored_extracted_at = cursor.fetchone()

                assert stored_close == Decimal("104.50000000")
                assert stored_extracted_at == datetime(
                    2026, 10, 9, 19, 0, tzinfo=timezone.utc
                )

    finally:
        with connect_to_database() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM fact_market_metrics
                    WHERE asset_key IN (
                        SELECT asset_key
                        FROM dim_asset
                        WHERE source = %s AND symbol = %s
                    );
                    """,
                    ("integration_test", "CORRECT23"),
                )

                cursor.execute(
                    """
                    DELETE FROM dim_asset
                    WHERE source = %s AND symbol = %s;
                    """,
                    ("integration_test", "CORRECT23"),
                )



@pytest.mark.integration
def test_silver_parquet_file_loads_into_gold(monkeypatch, tmp_path):
    """Load a real Silver Parquet file into the test Gold database."""

    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    record = MarketDataRecord(
        symbol="PARQUET23",
        observation_date=date(2026, 10, 9),
        open=Decimal("100.00000000"),
        high=Decimal("105.00000000"),
        low=Decimal("98.00000000"),
        close=Decimal("102.50000000"),
        volume=1000,
        source="integration_test",
        extracted_at=datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc),
    )

    writer = SilverWriter(base_dir=tmp_path)
    parquet_paths = writer.write([record])

    assert len(parquet_paths) == 1
    parquet_path = parquet_paths[0]

    try:
        counts = load_silver_file(str(parquet_path))

        assert counts == {
            "inserted": 1,
            "updated": 0,
            "unchanged": 0,
            "rejected": 0,
        }

        with connect_to_database() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT f.close
                    FROM fact_market_metrics AS f
                    JOIN dim_asset AS a
                        ON a.asset_key = f.asset_key
                    WHERE a.source = %s
                      AND a.symbol = %s
                      AND f.date_key = %s;
                    """,
                    ("integration_test", "PARQUET23", 20261009),
                )

                assert cursor.fetchone()[0] == Decimal("102.50000000")

    finally:
        with connect_to_database() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM fact_market_metrics
                    WHERE asset_key IN (
                        SELECT asset_key
                        FROM dim_asset
                        WHERE source = %s AND symbol = %s
                    );
                    """,
                    ("integration_test", "PARQUET23"),
                )

                cursor.execute(
                    """
                    DELETE FROM dim_asset
                    WHERE source = %s AND symbol = %s;
                    """,
                    ("integration_test", "PARQUET23"),
                )