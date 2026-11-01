"""Explicit, test-database-only fixtures for populated dashboard review.

This module is not imported or called by the Streamlit dashboard.
"""

import re
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import NAMESPACE_URL, uuid4, uuid5

from financial_data_platform.models.market_data import MarketDataRecord
from financial_data_platform.warehouse.db import (
    connect_to_database,
    get_database_config,
)
from financial_data_platform.warehouse.gold_loader import (
    ensure_asset,
    ensure_date,
    insert_market_fact,
)

TEST_DATABASE = "financial_market_test"
DEMO_SOURCE = "dashboard_demo"
DEMO_DAG = "dashboard_demo_review"
DEMO_DAYS = 35
FIRST_DATE = date(2026, 9, 1)
_SYMBOL_PATTERN = re.compile(r"DEMO[A-F0-9]{12}\Z")
_QUANT = Decimal("0.00000001")


def new_demo_symbol() -> str:
    """Generate an asset identifier unique to one demonstration session."""
    return "DEMO" + uuid4().hex[:12].upper()


def _validate_symbol(symbol: str) -> None:
    if not isinstance(symbol, str) or _SYMBOL_PATTERN.fullmatch(symbol) is None:
        raise ValueError("Expected an issued DEMO identifier (DEMO plus 12 hex digits)")


def _check_database(cursor) -> None:
    """Check both configured and actual database identity before writing."""
    if get_database_config()["dbname"] != TEST_DATABASE:
        raise ValueError("Dashboard demo is restricted to financial_market_test")
    cursor.execute("SELECT current_database()")
    if cursor.fetchone()[0] != TEST_DATABASE:
        raise ValueError("Connected database is not financial_market_test")


def _run_id(symbol: str, status: str):
    return uuid5(NAMESPACE_URL, f"financial-market-dashboard-demo:{symbol}:{status}")


def _prices(index: int) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    """A fixed, deterministic OHLC series with valid price ranges."""
    close = Decimal(100 + index) + Decimal(index % 3) / Decimal(4)
    return close - 1, close + 2, close - 2, close


def _indicators(index: int, closes: list[Decimal]):
    """Deterministic demonstration values, not a production indicator engine."""
    if index == 0:
        change = None
        ret = None
    else:
        change = (closes[index] - closes[index - 1]).quantize(_QUANT)
        ret = (
            (closes[index] - closes[index - 1]) / closes[index - 1] * Decimal(100)
        ).quantize(_QUANT)
    sma_7 = (
        (sum(closes[index - 6 : index + 1]) / Decimal(7)).quantize(_QUANT)
        if index >= 6
        else None
    )
    sma_30 = (
        (sum(closes[index - 29 : index + 1]) / Decimal(30)).quantize(_QUANT)
        if index >= 29
        else None
    )
    return change, ret, sma_7, sma_30


def seed_demo_data(symbol: str) -> None:
    """Commit 35 facts and three run statuses into the isolated test DB only."""
    _validate_symbol(symbol)
    with connect_to_database() as connection:
        with connection.cursor() as cursor:
            _check_database(cursor)
            cursor.execute(
                "SELECT 1 FROM dim_asset WHERE source = %s AND symbol = %s",
                (DEMO_SOURCE, symbol),
            )
            if cursor.fetchone() is not None:
                raise ValueError(
                    "This demo asset already exists; refusing to overwrite"
                )
            run_ids = [
                _run_id(symbol, status) for status in ("success", "failed", "running")
            ]
            cursor.execute(
                "SELECT 1 FROM pipeline_run WHERE run_id = ANY(%s)",
                (run_ids,),
            )
            if cursor.fetchone() is not None:
                raise ValueError("Demo run IDs already exist; refusing to overwrite")

            asset_key = ensure_asset(cursor, DEMO_SOURCE, symbol)
            closes = [_prices(i)[3] for i in range(DEMO_DAYS)]
            for index in range(DEMO_DAYS):
                day = FIRST_DATE + timedelta(days=index)
                opening, high, low, close = _prices(index)
                record = MarketDataRecord(
                    symbol=symbol,
                    observation_date=day,
                    open=opening,
                    high=high,
                    low=low,
                    close=close,
                    volume=1000 + index * 100,
                    source=DEMO_SOURCE,
                    extracted_at=datetime(2026, 10, 10, 18, tzinfo=timezone.utc),
                )
                date_key = ensure_date(cursor, day)
                if insert_market_fact(cursor, record, asset_key) != "insert":
                    raise RuntimeError("Expected a new test-owned market observation")
                cursor.execute(
                    """UPDATE fact_market_metrics
                    SET price_change = %s, daily_return_pct = %s,
                        sma_7 = %s, sma_30 = %s
                    WHERE asset_key = %s AND date_key = %s""",
                    (*_indicators(index, closes), asset_key, date_key),
                )

            for offset, status in enumerate(("success", "failed", "running")):
                start = datetime(2026, 10, 10 + offset, 12, tzinfo=timezone.utc)
                finish = start + timedelta(seconds=45) if status != "running" else None
                duration = Decimal("45.000") if finish else None
                cursor.execute(
                    """INSERT INTO pipeline_run (
                        run_id, dag_id, started_at, finished_at, status,
                        records_extracted, records_validated, records_transformed,
                        records_loaded, records_rejected, duration_seconds, source
                    ) VALUES (%s, %s, %s, %s, %s, 35, 33, 33, 30, 2, %s, %s)""",
                    (
                        _run_id(symbol, status),
                        DEMO_DAG,
                        start,
                        finish,
                        status,
                        duration,
                        DEMO_SOURCE,
                    ),
                )


def cleanup_demo_data(symbol: str) -> None:
    """Remove only the specified demo asset/facts and its three known run IDs."""
    _validate_symbol(symbol)
    with connect_to_database() as connection:
        with connection.cursor() as cursor:
            _check_database(cursor)
            cursor.execute(
                "SELECT asset_key FROM dim_asset WHERE source = %s AND symbol = %s",
                (DEMO_SOURCE, symbol),
            )
            row = cursor.fetchone()
            if row is not None:
                asset_key = row[0]
                cursor.execute(
                    "DELETE FROM fact_market_metrics WHERE asset_key = %s", (asset_key,)
                )
                cursor.execute(
                    "DELETE FROM dim_asset WHERE asset_key = %s", (asset_key,)
                )
            cursor.execute(
                "DELETE FROM pipeline_run WHERE run_id = ANY(%s) AND source = %s "
                "AND dag_id = %s",
                (
                    [
                        _run_id(symbol, status)
                        for status in ("success", "failed", "running")
                    ],
                    DEMO_SOURCE,
                    DEMO_DAG,
                ),
            )
            # Shared dim_date records are intentionally retained. They may be
            # referenced by independent market facts or other test fixtures.
