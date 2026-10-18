from financial_data_platform.models.market_data import MarketDataRecord


def read_gold_market_records(
    cursor,
    source: str,
    symbol: str,
) -> list[MarketDataRecord]:
    """Read historical daily observations for one asset from Gold."""

    cursor.execute(
        """
        SELECT
            a.symbol,
            d.full_date,
            f.open,
            f.high,
            f.low,
            f.close,
            f.volume,
            a.source,
            f.extracted_at
        FROM fact_market_metrics AS f
        JOIN dim_asset AS a
            ON a.asset_key = f.asset_key
        JOIN dim_date AS d
            ON d.date_key = f.date_key
        WHERE a.source = %s
          AND a.symbol = %s
        ORDER BY d.full_date ASC
        """,
        (source, symbol),
    )

    rows = cursor.fetchall()

    return [
        MarketDataRecord(
            symbol=row[0],
            observation_date=row[1],
            open=row[2],
            high=row[3],
            low=row[4],
            close=row[5],
            volume=row[6],
            source=row[7],
            extracted_at=row[8],
        )
        for row in rows
    ]