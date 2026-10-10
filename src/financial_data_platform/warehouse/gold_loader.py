"""Load validated market observations into the PostgreSQL Gold warehouse."""
from datetime import date
from financial_data_platform.models.market_data import MarketDataRecord
from financial_data_platform.warehouse.gold_mapping import (
    to_date_dimension,
    to_market_fact,
)
from financial_data_platform.warehouse.gold_conflicts import decide_fact_action
from financial_data_platform.warehouse.db import connect_to_database
from financial_data_platform.storage.silver_reader import read_silver_parquet

def ensure_asset(cursor, source: str, symbol: str) -> int:
    """Insert an asset or return its existing surrogate key."""

    cursor.execute(
        """
        INSERT INTO dim_asset (source, symbol)
        VALUES (%s, %s)
        ON CONFLICT (source, symbol)
        DO UPDATE SET symbol = EXCLUDED.symbol
        RETURNING asset_key;
        """,
        (source, symbol),
    )

    row = cursor.fetchone()
    return row[0]


def ensure_date(cursor, observation_date: date) -> int:
    """Insert a calendar date if needed and return its Gold date key."""

    values = to_date_dimension(observation_date)

    cursor.execute(
        """
        INSERT INTO dim_date (
            date_key,
            full_date,
            day,
            month,
            quarter,
            year,
            day_of_week
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (date_key) DO NOTHING;
        """,
        (
            values["date_key"],
            values["full_date"],
            values["day"],
            values["month"],
            values["quarter"],
            values["year"],
            values["day_of_week"],
        ),
    )

    return values["date_key"]


def insert_market_fact(
    cursor,
    record: MarketDataRecord,
    asset_key: int,
) -> str:
    """Insert a Gold fact or identify an unchanged observation."""

    values = to_market_fact(record, asset_key)

    cursor.execute(
        """
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
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (asset_key, date_key) DO NOTHING
        RETURNING asset_key;
        """,
        (
            values["asset_key"],
            values["date_key"],
            values["open"],
            values["high"],
            values["low"],
            values["close"],
            values["volume"],
            values["extracted_at"],
        ),
    )

    if cursor.fetchone() is not None:
        return "insert"

    cursor.execute(
        """
        SELECT open, high, low, close, volume, extracted_at
        FROM fact_market_metrics
        WHERE asset_key = %s AND date_key = %s
        FOR UPDATE;
        """,
        (values["asset_key"], values["date_key"]),
    )

    row = cursor.fetchone()

    if row is None:
        raise RuntimeError("Existing Gold fact could not be resolved")

    existing = dict(
        zip(
            ("open", "high", "low", "close", "volume", "extracted_at"),
            row,
        )
    )

    action = decide_fact_action(
        existing=existing,
        incoming={
            key: values[key]
            for key in ("open", "high", "low", "close", "volume", "extracted_at")
        },
    )

    if action == "unchanged":
        return "unchanged"

    if action == "update":
        cursor.execute(
            """
            UPDATE fact_market_metrics
            SET
                open = %s,
                high = %s,
                low = %s,
                close = %s,
                volume = %s,
                extracted_at = %s
            WHERE asset_key = %s
            AND date_key = %s
            AND extracted_at < %s;
            """,
            (
                values["open"],
                values["high"],
                values["low"],
                values["close"],
                values["volume"],
                values["extracted_at"],
                values["asset_key"],
                values["date_key"],
                values["extracted_at"],
            ),
        )

        if cursor.rowcount != 1:
            raise RuntimeError(
                "Gold fact update did not affect exactly one row"
            )

        return "update"

    if action == "reject":
        return "reject"

    raise ValueError(f"Unexpected Gold fact action: {action}")


def load_market_batch(
    cursor,
    records: list[MarketDataRecord],
) -> dict[str, int]:
    """Load a batch of canonical market observations into Gold."""

    counts = {
        "inserted": 0,
        "updated": 0,
        "unchanged": 0,
        "rejected": 0,
    }

    if not records:
        return counts

    for record in records:
        asset_key = ensure_asset(
            cursor,
            source=record.source,
            symbol=record.symbol,
        )

        ensure_date(cursor, record.observation_date)

        action = insert_market_fact(cursor, record, asset_key)

        if action not in ("insert", "update", "unchanged", "reject"):
            raise ValueError(f"Unexpected Gold fact action: {action}")

        count_key = {
            "insert": "inserted",
            "update": "updated",
            "unchanged": "unchanged",
            "reject": "rejected",
        }[action]

        counts[count_key] += 1

    return counts


def load_market_records(
    records: list[MarketDataRecord],
) -> dict[str, int]:
    """Load market records in a single PostgreSQL transaction."""

    connection = connect_to_database()

    try:
        with connection.cursor() as cursor:
            counts = load_market_batch(cursor, records)

        connection.commit()
        return counts

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()


def load_silver_file(parquet_path: str) -> dict[str, int]:
    """Read a Silver Parquet file and load its records into Gold."""

    records = read_silver_parquet(parquet_path)
    return load_market_records(records)