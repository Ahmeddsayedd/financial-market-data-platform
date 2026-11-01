"""Read-only analytics queries against the isolated PostgreSQL test warehouse."""

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from financial_data_platform.analytics.queries import (
    get_indicator_history,
    get_market_history,
    list_assets,
)
from financial_data_platform.warehouse.db import connect_to_database


pytestmark = pytest.mark.integration
TEST_DATABASE = "financial_market_test"


@pytest.fixture
def seeded_asset(monkeypatch):
    """Commit a unique test-owned fact, then remove only that fact and asset."""
    monkeypatch.setenv("POSTGRES_DB", TEST_DATABASE)
    symbol = "QUERY" + uuid4().hex[:12].upper()
    source = "integration_test"
    asset_key = None
    day = date(2026, 10, 9)

    with connect_to_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            assert cursor.fetchone()[0] == TEST_DATABASE
            cursor.execute(
                "INSERT INTO dim_asset (source, symbol) VALUES (%s, %s) RETURNING asset_key",
                (source, symbol),
            )
            asset_key = cursor.fetchone()[0]
            cursor.execute(
                """
                INSERT INTO dim_date
                    (date_key, full_date, day, month, quarter, year, day_of_week)
                VALUES (20261009, %s, 9, 10, 4, 2026, 5)
                ON CONFLICT (date_key) DO NOTHING
                """,
                (day,),
            )
            cursor.execute(
                """
                INSERT INTO fact_market_metrics
                    (asset_key, date_key, open, high, low, close, volume,
                     extracted_at, price_change, daily_return_pct, sma_7, sma_30)
                VALUES (%s, 20261009, 100, 105, 98, 102, 1000,
                        %s, 2, 2, NULL, 101.5)
                """,
                (asset_key, datetime(2026, 10, 9, 18, tzinfo=timezone.utc)),
            )

    try:
        yield source, symbol, day
    finally:
        with connect_to_database() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_database()")
                if cursor.fetchone()[0] != TEST_DATABASE:
                    raise RuntimeError("Refusing cleanup outside the test database")
                cursor.execute(
                    "DELETE FROM fact_market_metrics WHERE asset_key = %s", (asset_key,)
                )
                cursor.execute(
                    "DELETE FROM dim_asset WHERE asset_key = %s", (asset_key,)
                )


def test_assets_include_seeded_asset(seeded_asset):
    source, symbol, _ = seeded_asset
    assets = list_assets(source=source)
    assert any(asset.symbol == symbol and asset.source == source for asset in assets)
    assert assets == sorted(assets, key=lambda asset: (asset.source, asset.symbol))


def test_history_reads_exact_gold_values_and_date_filters(seeded_asset):
    source, symbol, day = seeded_asset
    records = get_market_history(source, symbol, start_date=day, end_date=day)
    assert len(records) == 1
    record = records[0]
    assert record.observation_date == day
    assert record.close == Decimal("102.00000000")
    assert record.volume == 1000
    assert record.price_change == Decimal("2.00000000")
    assert record.sma_7 is None
    assert record.sma_30 == Decimal("101.50000000")
    assert get_market_history(source, symbol, start_date=date(2026, 10, 10)) == []


def test_indicators_read_persisted_values(seeded_asset):
    source, symbol, day = seeded_asset
    indicators = get_indicator_history(source, symbol)
    assert len(indicators) == 1
    assert indicators[0].observation_date == day
    assert indicators[0].daily_return_pct == Decimal("2.00000000")
    assert indicators[0].sma_7 is None
    assert indicators[0].sma_30 == Decimal("101.50000000")
