"""Isolated Raw -> Silver -> Gold PostgreSQL integration tests."""

import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

from financial_data_platform.orchestration.gold import (
    load_silver_paths_to_gold,
)
from financial_data_platform.orchestration.silver import (
    process_raw_file_to_silver,
)
from financial_data_platform.warehouse.db import (
    connect_to_database,
    get_database_config,
)


pytestmark = pytest.mark.integration

TEST_DATABASE = "financial_market_test"
TEST_SOURCE = "twelve_data"
RAW_FILENAME = "20261024T160953206116Z.json"


@pytest.fixture
def isolated_asset(monkeypatch):
    """Allocate a unique symbol and remove only its Gold records."""
    monkeypatch.setenv("POSTGRES_DB", TEST_DATABASE)

    # Check the configured database before attempting a connection.
    assert get_database_config()["dbname"] == TEST_DATABASE

    symbol = "E2E" + uuid4().hex[:12].upper()

    # Verify the actual server-side database identity.
    with connect_to_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            assert cursor.fetchone()[0] == TEST_DATABASE

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM dim_asset
                WHERE source = %s AND symbol = %s
                """,
                (TEST_SOURCE, symbol),
            )
            assert cursor.fetchone()[0] == 0

    try:
        yield symbol
    finally:
        # The Gold loader commits its own transaction.
        # Remove facts first, then only this test-owned asset.
        with connect_to_database() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_database()")
                if cursor.fetchone()[0] != TEST_DATABASE:
                    raise RuntimeError("Refusing cleanup outside the test database")

                cursor.execute(
                    """
                    DELETE FROM fact_market_metrics
                    WHERE asset_key IN (
                        SELECT asset_key
                        FROM dim_asset
                        WHERE source = %s AND symbol = %s
                    )
                    """,
                    (TEST_SOURCE, symbol),
                )

                cursor.execute(
                    """
                    DELETE FROM dim_asset
                    WHERE source = %s AND symbol = %s
                    """,
                    (TEST_SOURCE, symbol),
                )


def observation(day, *, close="102.00", volume="1000"):
    return {
        "datetime": day,
        "open": "100.00",
        "high": "105.00",
        "low": "98.00",
        "close": close,
        "volume": volume,
    }


def run_raw_to_silver(tmp_path, symbol, values):
    raw_root = tmp_path / "raw"
    silver_root = tmp_path / "silver"

    relative_name = f"twelve_data/{symbol}/2026/10/24/{RAW_FILENAME}"
    raw_path = raw_root / relative_name
    raw_path.parent.mkdir(parents=True, exist_ok=True)

    raw_path.write_text(
        json.dumps(
            {
                "meta": {"symbol": symbol},
                "values": values,
            }
        ),
        encoding="utf-8",
    )

    result = process_raw_file_to_silver(
        raw_relative_path=relative_name,
        raw_base_dir=raw_root,
        silver_base_dir=silver_root,
        quarantine_base_dir=tmp_path / "quarantine",
        detected_at=datetime(2026, 10, 24, 18, 0, tzinfo=timezone.utc),
    )

    return result, silver_root


def load_result_to_gold(silver_result, silver_root):
    relative_paths = [
        Path(filename).relative_to(silver_root).as_posix()
        for filename in silver_result["silver_paths"]
    ]

    return load_silver_paths_to_gold(
        relative_paths=relative_paths,
        silver_base_dir=silver_root,
    )


def read_gold_facts(symbol):
    with connect_to_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    d.full_date,
                    f.open,
                    f.high,
                    f.low,
                    f.close,
                    f.volume,
                    f.extracted_at
                FROM fact_market_metrics AS f
                JOIN dim_asset AS a
                  ON a.asset_key = f.asset_key
                JOIN dim_date AS d
                  ON d.date_key = f.date_key
                WHERE a.source = %s
                  AND a.symbol = %s
                ORDER BY d.full_date
                """,
                (TEST_SOURCE, symbol),
            )
            return cursor.fetchall()


def test_valid_raw_observations_reach_gold(
    tmp_path,
    isolated_asset,
):
    symbol = isolated_asset

    silver, silver_root = run_raw_to_silver(
        tmp_path,
        symbol,
        [
            observation("2026-10-21"),
            observation("2026-10-22", close="103.00"),
        ],
    )

    assert silver["total_records"] == 2
    assert silver["valid_count"] == 2
    assert silver["invalid_count"] == 0
    assert silver["quality_report"]["acceptance_rate"] == 1.0

    gold = load_result_to_gold(silver, silver_root)

    assert gold["status"] == "success"
    assert gold["records_read"] == 2
    assert gold["inserted"] == 2
    assert gold["updated"] == 0
    assert gold["rejected"] == 0

    rows = read_gold_facts(symbol)

    assert len(rows) == 2
    assert [row[4] for row in rows] == [
        Decimal("102.00000000"),
        Decimal("103.00000000"),
    ]
    assert [row[5] for row in rows] == [1000, 1000]
    assert rows[0][1:4] == (
        Decimal("100.00000000"),
        Decimal("105.00000000"),
        Decimal("98.00000000"),
    )
    assert all(
        row[6]
        == datetime(
            2026,
            10,
            24,
            16,
            9,
            53,
            206116,
            tzinfo=timezone.utc,
        )
        for row in rows
    )


def test_invalid_raw_observation_never_reaches_gold(
    tmp_path,
    isolated_asset,
):
    symbol = isolated_asset

    silver, silver_root = run_raw_to_silver(
        tmp_path,
        symbol,
        [
            observation("2026-10-21"),
            observation(
                "2026-10-22",
                close="NaN",
                volume="-100",
            ),
        ],
    )

    assert silver["valid_count"] == 1
    assert silver["invalid_count"] == 1

    report = silver["quality_report"]
    assert report["violation_counts"] == {
        "NEGATIVE_VOLUME": 1,
        "NON_FINITE_CLOSE": 1,
    }

    assert len(silver["quarantine_paths"]) == 1

    quarantined = json.loads(
        Path(silver["quarantine_paths"][0]).read_text(encoding="utf-8")
    )
    assert {item["code"] for item in quarantined["violations"]} == {
        "NEGATIVE_VOLUME",
        "NON_FINITE_CLOSE",
    }

    gold = load_result_to_gold(silver, silver_root)

    assert gold["records_read"] == 1
    assert gold["inserted"] == 1
    assert gold["rejected"] == 0

    rows = read_gold_facts(symbol)

    assert len(rows) == 1
    assert rows[0][4] == Decimal("102.00000000")
    assert rows[0][5] == 1000


def test_replaying_raw_file_does_not_duplicate_gold_facts(
    tmp_path,
    isolated_asset,
):
    symbol = isolated_asset
    values = [
        observation("2026-10-21"),
        observation("2026-10-22", close="103.00"),
    ]

    first_silver, silver_root = run_raw_to_silver(tmp_path, symbol, values)
    first_gold = load_result_to_gold(first_silver, silver_root)

    second_silver, silver_root = run_raw_to_silver(tmp_path, symbol, values)
    second_gold = load_result_to_gold(second_silver, silver_root)

    assert first_gold["inserted"] == 2
    assert second_gold["inserted"] == 0
    assert second_gold["updated"] == 0
    assert second_gold["unchanged"] == 2
    assert second_gold["rejected"] == 0

    assert first_silver["quality_report"] == (second_silver["quality_report"])
    assert len(read_gold_facts(symbol)) == 2
