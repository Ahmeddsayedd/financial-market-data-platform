import pytest
from dataclasses import replace
from financial_data_platform.warehouse.db import connect_to_database
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from financial_data_platform.analytics.indicators import MarketIndicators
from financial_data_platform.models.market_data import MarketDataRecord
from financial_data_platform.warehouse.gold_loader import (
    ensure_asset,
    ensure_date,
    insert_market_fact,
)
from financial_data_platform.warehouse.gold_indicator_persistence import (
    update_gold_indicators,
    calculate_and_persist_indicators,
    load_market_records_with_indicators,
)
from financial_data_platform.warehouse.gold_market_history import (
    read_gold_market_records,
)
from unittest.mock import patch

@pytest.mark.integration
def test_indicator_integration_database_has_required_columns(monkeypatch):
    """Confirm that the test database supports all four indicators."""

    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    with connect_to_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'fact_market_metrics'
                  AND column_name IN (
                      'price_change',
                      'daily_return_pct',
                      'sma_7',
                      'sma_30'
                  )
                """
            )

            columns = {row[0] for row in cursor.fetchall()}

    assert columns == {
        "price_change",
        "daily_return_pct",
        "sma_7",
        "sma_30",
    }


@pytest.mark.integration
def test_update_gold_indicators_preserves_market_data(monkeypatch):
    """Persist indicators without changing the original market observation."""

    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    record = MarketDataRecord(
        symbol="INDICATOR27",
        observation_date=date(2026, 10, 9),
        open=Decimal("100.00000000"),
        high=Decimal("105.00000000"),
        low=Decimal("98.00000000"),
        close=Decimal("102.00000000"),
        volume=1000,
        source="integration_test",
        extracted_at=datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc),
    )

    indicators = MarketIndicators(
        record=record,
        price_change=Decimal("2.00000000"),
        daily_return_pct=Decimal("2.00000000"),
        sma_7=Decimal("101.50000000"),
        sma_30=None,
    )

    connection = connect_to_database()

    try:
        with connection.cursor() as cursor:
            asset_key = ensure_asset(
                cursor,
                source=record.source,
                symbol=record.symbol,
            )
            ensure_date(cursor, record.observation_date)
            insert_market_fact(cursor, record, asset_key)

            updated = update_gold_indicators(
                cursor=cursor,
                asset_key=asset_key,
                indicators=indicators,
            )

            assert updated is True

            cursor.execute(
                """
                SELECT
                    open, high, low, close, volume, extracted_at,
                    price_change, daily_return_pct, sma_7, sma_30
                FROM fact_market_metrics
                WHERE asset_key = %s
                  AND date_key = %s
                """,
                (asset_key, 20261009),
            )

            row = cursor.fetchone()

            assert row == (
                record.open,
                record.high,
                record.low,
                record.close,
                record.volume,
                record.extracted_at,
                Decimal("2.00000000"),
                Decimal("2.00000000"),
                Decimal("101.50000000"),
                None,
            )

    finally:
        connection.rollback()
        connection.close()


@pytest.mark.integration
def test_update_gold_indicators_is_idempotent(monkeypatch):
    """Identical indicator values must not trigger a second update."""

    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    record = MarketDataRecord(
        symbol="IDEMPOTENT27",
        observation_date=date(2026, 10, 9),
        open=Decimal("100.00000000"),
        high=Decimal("105.00000000"),
        low=Decimal("98.00000000"),
        close=Decimal("102.00000000"),
        volume=1000,
        source="integration_test",
        extracted_at=datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    )

    indicators = MarketIndicators(
        record=record,
        price_change=Decimal("2.00000000"),
        daily_return_pct=Decimal("2.00000000"),
        sma_7=Decimal("101.50000000"),
        sma_30=None,
    )

    connection = connect_to_database()

    try:
        with connection.cursor() as cursor:
            asset_key = ensure_asset(
                cursor,
                source=record.source,
                symbol=record.symbol,
            )
            ensure_date(cursor, record.observation_date)
            insert_market_fact(cursor, record, asset_key)

            first_update = update_gold_indicators(
                cursor=cursor,
                asset_key=asset_key,
                indicators=indicators,
            )

            second_update = update_gold_indicators(
                cursor=cursor,
                asset_key=asset_key,
                indicators=indicators,
            )

            assert first_update is True
            assert second_update is False

    finally:
        connection.rollback()
        connection.close()


@pytest.mark.integration
def test_update_gold_indicators_replaces_null_with_value(monkeypatch):
    """A newly available SMA must replace its previous NULL value."""

    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    record = MarketDataRecord(
        symbol="NULLSMA27",
        observation_date=date(2026, 10, 9),
        open=Decimal("100.00000000"),
        high=Decimal("105.00000000"),
        low=Decimal("98.00000000"),
        close=Decimal("102.00000000"),
        volume=1000,
        source="integration_test",
        extracted_at=datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    )

    initial = MarketIndicators(
        record=record,
        price_change=None,
        daily_return_pct=None,
        sma_7=None,
        sma_30=None,
    )

    recalculated = replace(
        initial,
        sma_7=Decimal("101.50000000"),
    )

    connection = connect_to_database()

    try:
        with connection.cursor() as cursor:
            asset_key = ensure_asset(
                cursor,
                source=record.source,
                symbol=record.symbol,
            )
            ensure_date(cursor, record.observation_date)
            insert_market_fact(cursor, record, asset_key)

            initial_update = update_gold_indicators(
                cursor=cursor,
                asset_key=asset_key,
                indicators=initial,
            )

            corrected_update = update_gold_indicators(
                cursor=cursor,
                asset_key=asset_key,
                indicators=recalculated,
            )

            assert initial_update is False
            assert corrected_update is True

            cursor.execute(
                """
                SELECT sma_7
                FROM fact_market_metrics
                WHERE asset_key = %s
                  AND date_key = %s
                """,
                (asset_key, 20261009),
            )

            assert cursor.fetchone()[0] == Decimal("101.50000000")

    finally:
        connection.rollback()
        connection.close()


@pytest.mark.integration
def test_stale_observation_cannot_overwrite_gold_indicators(monkeypatch):
    """Reject indicator writes based on an outdated extraction timestamp."""

    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    record = MarketDataRecord(
        symbol="STALE27",
        observation_date=date(2026, 10, 9),
        open=Decimal("100.00000000"),
        high=Decimal("105.00000000"),
        low=Decimal("98.00000000"),
        close=Decimal("102.00000000"),
        volume=1000,
        source="integration_test",
        extracted_at=datetime(2026, 10, 9, 19, 0, tzinfo=timezone.utc),
    )

    current_indicators = MarketIndicators(
        record=record,
        price_change=Decimal("2.00000000"),
        daily_return_pct=Decimal("2.00000000"),
        sma_7=None,
        sma_30=None,
    )

    older_record = replace(
        record,
        extracted_at=datetime(2026, 10, 9, 18, 0, tzinfo=timezone.utc),
    )

    stale_indicators = replace(
        current_indicators,
        record=older_record,
        price_change=Decimal("3.00000000"),
    )

    connection = connect_to_database()

    try:
        with connection.cursor() as cursor:
            asset_key = ensure_asset(
                cursor,
                source=record.source,
                symbol=record.symbol,
            )
            ensure_date(cursor, record.observation_date)
            insert_market_fact(cursor, record, asset_key)

            assert update_gold_indicators(
                cursor, asset_key, current_indicators
            ) is True

            with pytest.raises(ValueError, match="Stale market observation"):
                update_gold_indicators(
                    cursor, asset_key, stale_indicators
                )

            cursor.execute(
                """
                SELECT price_change, extracted_at
                FROM fact_market_metrics
                WHERE asset_key = %s
                  AND date_key = %s
                """,
                (asset_key, 20261009),
            )

            assert cursor.fetchone() == (
                Decimal("2.00000000"),
                record.extracted_at,
            )

    finally:
        connection.rollback()
        connection.close()


@pytest.mark.integration
def test_update_gold_indicators_rejects_missing_fact(monkeypatch):
    """A missing Gold fact must not be treated as an unchanged update."""

    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    record = MarketDataRecord(
        symbol="MISSING27",
        observation_date=date(2026, 10, 9),
        open=Decimal("100.00000000"),
        high=Decimal("105.00000000"),
        low=Decimal("98.00000000"),
        close=Decimal("102.00000000"),
        volume=1000,
        source="integration_test",
        extracted_at=datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    )

    indicators = MarketIndicators(
        record=record,
        price_change=None,
        daily_return_pct=None,
        sma_7=None,
        sma_30=None,
    )

    connection = connect_to_database()

    try:
        with connection.cursor() as cursor:
            # Create the asset dimension, but deliberately do not
            # insert a fact_market_metrics row.
            asset_key = ensure_asset(
                cursor,
                source=record.source,
                symbol=record.symbol,
            )

            with pytest.raises(ValueError, match="Gold market fact not found"):
                update_gold_indicators(
                    cursor=cursor,
                    asset_key=asset_key,
                    indicators=indicators,
                )

    finally:
        connection.rollback()
        connection.close()


@pytest.mark.integration
def test_update_gold_indicators_rejects_stale_observation(monkeypatch):
    """A stale extraction must raise an error, not appear unchanged."""

    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    record = MarketDataRecord(
        symbol="STALEERROR27",
        observation_date=date(2026, 10, 9),
        open=Decimal("100.00000000"),
        high=Decimal("105.00000000"),
        low=Decimal("98.00000000"),
        close=Decimal("102.00000000"),
        volume=1000,
        source="integration_test",
        extracted_at=datetime(
            2026, 10, 9, 19, 0, tzinfo=timezone.utc
        ),
    )

    stale_record = replace(
        record,
        extracted_at=datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    )

    stale_indicators = MarketIndicators(
        record=stale_record,
        price_change=Decimal("3.00000000"),
        daily_return_pct=Decimal("3.00000000"),
        sma_7=None,
        sma_30=None,
    )

    connection = connect_to_database()

    try:
        with connection.cursor() as cursor:
            asset_key = ensure_asset(
                cursor,
                source=record.source,
                symbol=record.symbol,
            )
            ensure_date(cursor, record.observation_date)
            insert_market_fact(cursor, record, asset_key)

            with pytest.raises(ValueError, match="Stale market observation"):
                update_gold_indicators(
                    cursor=cursor,
                    asset_key=asset_key,
                    indicators=stale_indicators,
                )

    finally:
        connection.rollback()
        connection.close()


@pytest.mark.integration
def test_read_gold_market_records_from_postgresql(monkeypatch):
    """Read a real Gold observation back as a MarketDataRecord."""

    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    record = MarketDataRecord(
        symbol="HISTORY27",
        observation_date=date(2026, 10, 9),
        open=Decimal("100.00000000"),
        high=Decimal("105.00000000"),
        low=Decimal("98.00000000"),
        close=Decimal("102.00000000"),
        volume=1000,
        source="integration_test",
        extracted_at=datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    )

    connection = connect_to_database()

    try:
        with connection.cursor() as cursor:
            asset_key = ensure_asset(
                cursor,
                source=record.source,
                symbol=record.symbol,
            )
            ensure_date(cursor, record.observation_date)
            insert_market_fact(cursor, record, asset_key)

            history = read_gold_market_records(
                cursor=cursor,
                source="integration_test",
                symbol="HISTORY27",
            )

            assert history == [record]

    finally:
        connection.rollback()
        connection.close()


@pytest.mark.integration
def test_sma_7_uses_gold_history_across_batches(monkeypatch):
    """SMA 7 uses historical Gold facts from earlier batches."""

    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    base = MarketDataRecord(
        symbol="SMABATCH27",
        observation_date=date(2026, 10, 1),
        open=Decimal("100.00000000"),
        high=Decimal("110.00000000"),
        low=Decimal("90.00000000"),
        close=Decimal("101.00000000"),
        volume=1000,
        source="integration_test",
        extracted_at=datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    )

    records = [
        replace(
            base,
            observation_date=base.observation_date + timedelta(days=index),
            close=Decimal(101 + index),
        )
        for index in range(7)
    ]

    connection = connect_to_database()

    try:
        with connection.cursor() as cursor:
            asset_key = ensure_asset(
                cursor,
                source=base.source,
                symbol=base.symbol,
            )

            # First batch: six historical observations.
            for record in records[:6]:
                ensure_date(cursor, record.observation_date)
                insert_market_fact(cursor, record, asset_key)

            # Second batch: the seventh observation.
            seventh = records[6]
            ensure_date(cursor, seventh.observation_date)
            insert_market_fact(cursor, seventh, asset_key)

            counts = calculate_and_persist_indicators(
                cursor,
                [seventh],
            )

            assert counts == {
                "updated": 6,
                "unchanged": 1,
            }

            cursor.execute(
                """
                SELECT sma_7
                FROM fact_market_metrics
                WHERE asset_key = %s
                  AND date_key = %s
                """,
                (asset_key, 20261007),
            )

            assert cursor.fetchone()[0] == Decimal("104.00000000")

    finally:
        connection.rollback()
        connection.close()


@pytest.mark.integration
def test_historical_price_correction_recalculates_later_indicators(monkeypatch):
    """Correcting an earlier close updates indicators on later dates."""

    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    base = MarketDataRecord(
        symbol="CORRECTION27",
        observation_date=date(2026, 10, 1),
        open=Decimal("100.00000000"),
        high=Decimal("110.00000000"),
        low=Decimal("90.00000000"),
        close=Decimal("100.00000000"),
        volume=1000,
        source="integration_test",
        extracted_at=datetime(
            2026, 10, 3, 18, 0, tzinfo=timezone.utc
        ),
    )

    first = base
    second = replace(
        base,
        observation_date=date(2026, 10, 2),
        close=Decimal("102.00000000"),
    )
    third = replace(
        base,
        observation_date=date(2026, 10, 3),
        close=Decimal("105.00000000"),
    )

    corrected_second = replace(
        second,
        close=Decimal("104.00000000"),
        extracted_at=datetime(
            2026, 10, 3, 19, 0, tzinfo=timezone.utc
        ),
    )

    connection = connect_to_database()

    try:
        with connection.cursor() as cursor:
            asset_key = ensure_asset(
                cursor,
                source=base.source,
                symbol=base.symbol,
            )

            for record in [first, second, third]:
                ensure_date(cursor, record.observation_date)
                insert_market_fact(cursor, record, asset_key)

            calculate_and_persist_indicators(cursor, [first, second, third])

            # Apply a newer correction to the October 2 market fact.
            assert insert_market_fact(
                cursor, corrected_second, asset_key
            ) == "update"

            # Recalculate using Gold's updated historical prices.
            calculate_and_persist_indicators(cursor, [corrected_second])

            cursor.execute(
                """
                SELECT price_change, daily_return_pct
                FROM fact_market_metrics
                WHERE asset_key = %s
                  AND date_key = %s
                """,
                (asset_key, 20261003),
            )

            stored_change, stored_return = cursor.fetchone()

            assert stored_change == Decimal("1.00000000")
            assert stored_return == (
                Decimal("1") / Decimal("104") * Decimal("100")
            ).quantize(Decimal("0.00000001"))

    finally:
        connection.rollback()
        connection.close()


@pytest.mark.integration
def test_atomic_gold_loading_persists_market_data_and_indicators(
    monkeypatch,
):
    """Commit market observations and their indicators together."""

    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    first = MarketDataRecord(
        symbol="ATOMIC27",
        observation_date=date(2026, 10, 8),
        open=Decimal("100.00000000"),
        high=Decimal("105.00000000"),
        low=Decimal("98.00000000"),
        close=Decimal("100.00000000"),
        volume=1000,
        source="integration_test",
        extracted_at=datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    )

    second = replace(
        first,
        observation_date=date(2026, 10, 9),
        close=Decimal("102.00000000"),
    )

    try:
        counts = load_market_records_with_indicators([first, second])

        assert counts["market"] == {
            "inserted": 2,
            "updated": 0,
            "unchanged": 0,
            "rejected": 0,
        }

        assert counts["indicators"] == {
            "updated": 1,
            "unchanged": 1,
        }

        with connect_to_database() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT f.close, f.price_change, f.daily_return_pct
                    FROM fact_market_metrics AS f
                    JOIN dim_asset AS a
                        ON a.asset_key = f.asset_key
                    WHERE a.source = %s
                      AND a.symbol = %s
                      AND f.date_key = %s
                    """,
                    ("integration_test", "ATOMIC27", 20261009),
                )

                assert cursor.fetchone() == (
                    Decimal("102.00000000"),
                    Decimal("2.00000000"),
                    Decimal("2.00000000"),
                )

    finally:
        # This workflow commits, so explicitly remove its test data.
        with connect_to_database() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM fact_market_metrics
                    WHERE asset_key IN (
                        SELECT asset_key
                        FROM dim_asset
                        WHERE source = %s AND symbol = %s
                    )
                    """,
                    ("integration_test", "ATOMIC27"),
                )

                cursor.execute(
                    """
                    DELETE FROM dim_asset
                    WHERE source = %s AND symbol = %s
                    """,
                    ("integration_test", "ATOMIC27"),
                )


@pytest.mark.integration
def test_atomic_gold_loading_rolls_back_when_indicators_fail(monkeypatch):
    """A failure during indicator persistence rolls back market facts."""

    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    record = MarketDataRecord(
        symbol="ROLLBACKIND27",
        observation_date=date(2026, 10, 9),
        open=Decimal("100.00000000"),
        high=Decimal("105.00000000"),
        low=Decimal("98.00000000"),
        close=Decimal("102.00000000"),
        volume=1000,
        source="integration_test",
        extracted_at=datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    )

    with patch(
        "financial_data_platform.warehouse.gold_indicator_persistence.calculate_and_persist_indicators",
        side_effect=RuntimeError("Simulated indicator failure"),
    ):
        with pytest.raises(RuntimeError, match="Simulated indicator failure"):
            load_market_records_with_indicators([record])

    # Inspect committed state using a new database connection.
    with connect_to_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM dim_asset
                WHERE source = %s
                  AND symbol = %s
                """,
                ("integration_test", "ROLLBACKIND27"),
            )

            assert cursor.fetchone()[0] == 0


@pytest.mark.integration
def test_atomic_gold_loading_retry_is_idempotent(monkeypatch):
    """Retrying the same market batch must not change Gold facts or indicators."""

    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    record = MarketDataRecord(
        symbol="RETRYIND27",
        observation_date=date(2026, 10, 9),
        open=Decimal("100.00000000"),
        high=Decimal("105.00000000"),
        low=Decimal("98.00000000"),
        close=Decimal("102.00000000"),
        volume=1000,
        source="integration_test",
        extracted_at=datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    )

    try:
        first_counts = load_market_records_with_indicators([record])
        retry_counts = load_market_records_with_indicators([record])

        assert first_counts == {
            "market": {
                "inserted": 1,
                "updated": 0,
                "unchanged": 0,
                "rejected": 0,
            },
            "indicators": {
                "updated": 0,
                "unchanged": 1,
            },
        }

        assert retry_counts == {
            "market": {
                "inserted": 0,
                "updated": 0,
                "unchanged": 1,
                "rejected": 0,
            },
            "indicators": {
                "updated": 0,
                "unchanged": 1,
            },
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
                      AND a.symbol = %s
                    """,
                    ("integration_test", "RETRYIND27"),
                )

                assert cursor.fetchone()[0] == 1

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
                    )
                    """,
                    ("integration_test", "RETRYIND27"),
                )

                cursor.execute(
                    """
                    DELETE FROM dim_asset
                    WHERE source = %s AND symbol = %s
                    """,
                    ("integration_test", "RETRYIND27"),
                )


@pytest.mark.integration
def test_atomic_gold_loading_recalculates_after_committed_correction(monkeypatch):
    """A correction in a later batch updates downstream Gold indicators."""

    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    first = MarketDataRecord(
        symbol="ATOMICCORR27",
        observation_date=date(2026, 10, 8),
        open=Decimal("100.00000000"),
        high=Decimal("110.00000000"),
        low=Decimal("98.00000000"),
        close=Decimal("100.00000000"),
        volume=1000,
        source="integration_test",
        extracted_at=datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    )

    second = replace(
        first,
        observation_date=date(2026, 10, 9),
        close=Decimal("105.00000000"),
    )

    corrected_first = replace(
        first,
        close=Decimal("104.00000000"),
        extracted_at=datetime(
            2026, 10, 9, 19, 0, tzinfo=timezone.utc
        ),
    )

    try:
        initial_counts = load_market_records_with_indicators(
            [first, second]
        )

        assert initial_counts["market"]["inserted"] == 2

        correction_counts = load_market_records_with_indicators(
            [corrected_first]
        )

        assert correction_counts["market"]["updated"] == 1

        with connect_to_database() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT f.close, f.price_change
                    FROM fact_market_metrics AS f
                    JOIN dim_asset AS a
                        ON a.asset_key = f.asset_key
                    WHERE a.source = %s
                      AND a.symbol = %s
                      AND f.date_key = %s
                    """,
                    ("integration_test", "ATOMICCORR27", 20261009),
                )

                assert cursor.fetchone() == (
                    Decimal("105.00000000"),
                    Decimal("1.00000000"),
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
                    )
                    """,
                    ("integration_test", "ATOMICCORR27"),
                )

                cursor.execute(
                    """
                    DELETE FROM dim_asset
                    WHERE source = %s AND symbol = %s
                    """,
                    ("integration_test", "ATOMICCORR27"),
                )


@pytest.mark.integration
def test_rejected_market_batch_rolls_back_all_changes(monkeypatch):
    """A rejected observation rolls back earlier valid inserts."""

    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")

    base = MarketDataRecord(
        symbol="REJECT27",
        observation_date=date(2026, 10, 8),
        open=Decimal("100.00000000"),
        high=Decimal("110.00000000"),
        low=Decimal("98.00000000"),
        close=Decimal("102.00000000"),
        volume=1000,
        source="integration_test",
        extracted_at=datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    )

    valid = base

    conflicting = replace(
        base,
        close=Decimal("104.00000000"),
    )

    with pytest.raises(ValueError, match="rejected"):
        load_market_records_with_indicators(
            [valid, conflicting]
        )

    # Verify the transaction inserted nothing permanently.
    with connect_to_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM dim_asset
                WHERE source = %s
                  AND symbol = %s
                """,
                ("integration_test", "REJECT27"),
            )

            assert cursor.fetchone()[0] == 0