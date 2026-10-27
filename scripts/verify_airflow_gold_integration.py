"""Controlled Silver-to-Gold integration verification.

Run inside the Airflow scheduler container.
Writes only to financial_market_test.
"""

from pathlib import Path

from financial_data_platform.orchestration.gold import (
    load_silver_paths_to_gold,
)
from financial_data_platform.warehouse.db import (
    connect_to_database,
)


SILVER_ROOT = Path("/opt/financial-data/silver")
SILVER_FILE = "symbol=AAPL/year=2026/data.parquet"
EXPECTED_DATABASE = "financial_market_test"


def count_aapl_rows():
    connection = connect_to_database()

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            database = cursor.fetchone()[0]

            if database != EXPECTED_DATABASE:
                raise RuntimeError(f"Refusing database operation against {database}")

            cursor.execute(
                """
                SELECT COUNT(*)
                FROM fact_market_metrics AS fact
                JOIN dim_asset AS asset
                  ON asset.asset_key = fact.asset_key
                WHERE asset.symbol = %s
                  AND asset.source = %s
                """,
                ("AAPL", "twelve_data"),
            )

            return cursor.fetchone()[0]
    finally:
        connection.close()


def main():
    silver_path = SILVER_ROOT / SILVER_FILE

    if not silver_path.is_file():
        raise FileNotFoundError(silver_path)

    before = count_aapl_rows()
    print("AAPL Gold rows before:", before)

    first = load_silver_paths_to_gold(
        relative_paths=[SILVER_FILE],
        silver_base_dir=SILVER_ROOT,
    )

    print("First load:", first)

    after_first = count_aapl_rows()
    print("AAPL Gold rows after first load:", after_first)

    second = load_silver_paths_to_gold(
        relative_paths=[SILVER_FILE],
        silver_base_dir=SILVER_ROOT,
    )

    print("Second load:", second)

    after_second = count_aapl_rows()
    print("AAPL Gold rows after second load:", after_second)

    assert first["records_read"] == 30
    assert second["records_read"] == 30

    assert after_second == after_first, (
        "Repeated loading unexpectedly increased the number of Gold rows"
    )

    assert second["inserted"] == 0
    assert second["updated"] == 0
    assert second["unchanged"] == 30

    print("PASS: Silver-to-Gold loading")
    print("PASS: Repeated loading is idempotent")


if __name__ == "__main__":
    main()
