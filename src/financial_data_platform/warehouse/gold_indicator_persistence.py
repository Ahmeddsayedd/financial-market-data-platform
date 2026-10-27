from financial_data_platform.analytics.indicators import (
    MarketIndicators,
    calculate_market_indicators,
)
from financial_data_platform.models.market_data import MarketDataRecord
from financial_data_platform.warehouse.gold_indicator_mapping import (
    to_gold_indicator_values,
)
from financial_data_platform.warehouse.gold_mapping import to_date_key
from financial_data_platform.warehouse.gold_market_history import (
    read_gold_market_records,
)
from financial_data_platform.warehouse.db import connect_to_database
from financial_data_platform.warehouse.gold_loader import (
    ensure_asset,
    load_market_batch,
)


def update_gold_indicators(
    cursor,
    asset_key: int,
    indicators: MarketIndicators,
) -> bool:
    """Update financial indicators for an existing Gold market fact."""

    values = to_gold_indicator_values(indicators)
    date_key = to_date_key(indicators.record.observation_date)

    cursor.execute(
        """
        SELECT extracted_at
        FROM fact_market_metrics
        WHERE asset_key = %s
        AND date_key = %s
        FOR UPDATE
        """,
        (asset_key, date_key),
    )

    row = cursor.fetchone()

    if row is None:
        raise ValueError(
            f"Gold market fact not found: asset_key={asset_key}, date_key={date_key}"
        )

    stored_extracted_at = row[0]

    if stored_extracted_at != indicators.record.extracted_at:
        raise ValueError(
            f"Stale market observation: asset_key={asset_key}, date_key={date_key}"
        )

    cursor.execute(
        """
        UPDATE fact_market_metrics
        SET
            price_change = %s,
            daily_return_pct = %s,
            sma_7 = %s,
            sma_30 = %s
        WHERE asset_key = %s
        AND date_key = %s
        AND extracted_at = %s
        AND (
            price_change IS DISTINCT FROM %s
            OR daily_return_pct IS DISTINCT FROM %s
            OR sma_7 IS DISTINCT FROM %s
            OR sma_30 IS DISTINCT FROM %s
        )
        """,
        (
            values["price_change"],
            values["daily_return_pct"],
            values["sma_7"],
            values["sma_30"],
            asset_key,
            date_key,
            indicators.record.extracted_at,
            values["price_change"],
            values["daily_return_pct"],
            values["sma_7"],
            values["sma_30"],
        ),
    )

    return cursor.rowcount == 1


def persist_market_indicators(
    cursor,
    indicators_list: list[MarketIndicators],
) -> dict[str, int]:
    """Persist indicators for existing Gold facts using the caller's transaction."""

    counts = {
        "updated": 0,
        "unchanged": 0,
    }

    for indicators in indicators_list:
        record = indicators.record

        asset_key = ensure_asset(
            cursor,
            source=record.source,
            symbol=record.symbol,
        )

        updated = update_gold_indicators(
            cursor=cursor,
            asset_key=asset_key,
            indicators=indicators,
        )

        if updated:
            counts["updated"] += 1
        else:
            counts["unchanged"] += 1

    return counts


def calculate_and_persist_indicators(
    cursor,
    records: list[MarketDataRecord],
) -> dict[str, int]:
    """Recalculate Gold indicators using complete history per asset.

    Incoming market records must already exist in Gold.
    The caller owns the database transaction.
    """
    identities = sorted({(record.source, record.symbol) for record in records})

    calculated: list[MarketIndicators] = []

    for source, symbol in identities:
        history = read_gold_market_records(
            cursor=cursor,
            source=source,
            symbol=symbol,
        )

        calculated.extend(calculate_market_indicators(history))

    return persist_market_indicators(cursor, calculated)


def load_market_records_with_indicators(
    records: list[MarketDataRecord],
) -> dict[str, dict[str, int]]:
    """Atomically load market facts and recalculate Gold indicators."""

    connection = connect_to_database()

    try:
        with connection.cursor() as cursor:
            market_counts = load_market_batch(cursor, records)

            if market_counts["rejected"] > 0:
                raise ValueError(
                    f"Market batch contains "
                    f"{market_counts['rejected']} rejected observation(s)"
                )

            indicator_counts = calculate_and_persist_indicators(cursor, records)

        connection.commit()

        return {
            "market": market_counts,
            "indicators": indicator_counts,
        }

    except Exception:
        connection.rollback()
        raise

    finally:
        connection.close()
