"""Issue #101: rollback-only Gold persistence and query verification."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from financial_data_platform.analytics.indicators import calculate_market_indicators
from financial_data_platform.analytics.queries import get_market_history
from financial_data_platform.models.market_data import MarketDataRecord
from financial_data_platform.warehouse.db import connect_to_database
from financial_data_platform.warehouse.gold_indicator_persistence import (
    persist_market_indicators,
)
from financial_data_platform.warehouse.gold_loader import (
    ensure_asset,
    ensure_date,
    insert_market_fact,
)

pytestmark = pytest.mark.integration
TEST_DATABASE = "financial_market_test"


def test_advanced_metrics_write_read_and_replay_in_rollback_transaction(monkeypatch):
    """Never commit or touch non-test databases; clean up by rollback."""
    monkeypatch.setenv("POSTGRES_DB", TEST_DATABASE)
    symbol = "ADV" + uuid4().hex[:12].upper()
    rows = []
    for i in range(55):
        close = Decimal(100 + (i % 17))
        rows.append(
            MarketDataRecord(
                symbol=symbol,
                source="integration_test",
                observation_date=date(2026, 1, 1) + timedelta(days=i),
                open=close,
                high=close + 1,
                low=close - 1,
                close=close,
                volume=1000 + 3 * i,
                extracted_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            )
        )

    connection = connect_to_database()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            assert cursor.fetchone()[0] == TEST_DATABASE
            asset_key = ensure_asset(cursor, "integration_test", symbol)
            for record in rows:
                ensure_date(cursor, record.observation_date)
                assert insert_market_fact(cursor, record, asset_key) == "insert"
            calculated = calculate_market_indicators(rows)
            first = persist_market_indicators(cursor, calculated)
            assert first == {"updated": 55, "unchanged": 0}
            assert persist_market_indicators(cursor, calculated) == {
                "updated": 0,
                "unchanged": 55,
            }
            cursor.execute(
                """
                SELECT period_return, log_return, sma_20, sma_50,
                       rolling_volatility_20d, rsi_14, drawdown, volume_zscore
                FROM fact_market_metrics
                WHERE asset_key = %s AND date_key = %s
                """,
                (asset_key, int(rows[-1].observation_date.strftime("%Y%m%d"))),
            )
            values = cursor.fetchone()
            assert values is not None
            assert all(value is not None for value in values)
            assert Decimal(0) <= values[5] <= Decimal(100)
            assert values[6] <= Decimal(0)

        # No commit: the caller's transaction still owns all writes.
        # get_market_history would use a separate connection, so verify via
        # this transaction's own SELECT above instead.
    finally:
        connection.rollback()
        connection.close()


def test_advanced_queries_use_test_database_only(monkeypatch):
    """Read-only query behavior is already exercised in the existing query suite."""
    monkeypatch.setenv("POSTGRES_DB", TEST_DATABASE)
    with connect_to_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            assert cursor.fetchone()[0] == TEST_DATABASE
    # An unknown asset is a harmless SELECT and must produce no rows.
    assert get_market_history("integration_test", "NOT_A_REAL_101_ASSET") == []
