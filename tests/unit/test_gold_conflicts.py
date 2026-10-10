from datetime import datetime, timezone
from decimal import Decimal

from financial_data_platform.warehouse.gold_conflicts import (
    decide_fact_action,
)


def test_new_observation_should_be_inserted():
    """Insert a market observation when no Gold fact exists."""

    incoming = {
        "open": Decimal("250.00000000"),
        "high": Decimal("255.00000000"),
        "low": Decimal("248.00000000"),
        "close": Decimal("253.00000000"),
        "volume": 1000000,
        "extracted_at": datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    }

    result = decide_fact_action(
        existing=None,
        incoming=incoming,
    )

    assert result == "insert"


def test_identical_observation_should_remain_unchanged():
    """Reprocessing an identical observation must not change Gold."""

    existing = {
        "open": Decimal("250.00000000"),
        "high": Decimal("255.00000000"),
        "low": Decimal("248.00000000"),
        "close": Decimal("253.00000000"),
        "volume": 1000000,
        "extracted_at": datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    }

    incoming = existing.copy()

    result = decide_fact_action(
        existing=existing,
        incoming=incoming,
    )

    assert result == "unchanged"


def test_newer_extraction_with_changed_prices_should_update():
    """Newer corrected market data should replace older Gold values."""

    existing = {
        "open": Decimal("250.00000000"),
        "high": Decimal("255.00000000"),
        "low": Decimal("248.00000000"),
        "close": Decimal("253.00000000"),
        "volume": 1000000,
        "extracted_at": datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    }

    incoming = {
        **existing,
        "close": Decimal("254.50000000"),
        "extracted_at": datetime(
            2026, 10, 9, 19, 0, tzinfo=timezone.utc
        ),
    }

    result = decide_fact_action(
        existing=existing,
        incoming=incoming,
    )

    assert result == "update"


def test_older_extraction_should_remain_unchanged():
    """Older market data must not overwrite a newer Gold observation."""

    existing = {
        "open": Decimal("250.00000000"),
        "high": Decimal("255.00000000"),
        "low": Decimal("248.00000000"),
        "close": Decimal("254.50000000"),
        "volume": 1000000,
        "extracted_at": datetime(
            2026, 10, 9, 19, 0, tzinfo=timezone.utc
        ),
    }

    incoming = {
        **existing,
        "close": Decimal("253.00000000"),
        "extracted_at": datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    }

    result = decide_fact_action(
        existing=existing,
        incoming=incoming,
    )

    assert result == "unchanged"


def test_equal_timestamp_with_different_prices_should_reject():
    """Reject conflicting values with identical extraction timestamps."""

    existing = {
        "open": Decimal("250.00000000"),
        "high": Decimal("255.00000000"),
        "low": Decimal("248.00000000"),
        "close": Decimal("253.00000000"),
        "volume": 1000000,
        "extracted_at": datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    }

    incoming = {
        **existing,
        "close": Decimal("254.50000000"),
    }

    result = decide_fact_action(
        existing=existing,
        incoming=incoming,
    )

    assert result == "reject"


def test_same_prices_with_newer_extraction_should_update():
    """Advance the extraction timestamp even when prices are unchanged."""

    existing = {
        "open": Decimal("250.00000000"),
        "high": Decimal("255.00000000"),
        "low": Decimal("248.00000000"),
        "close": Decimal("253.00000000"),
        "volume": 1000000,
        "extracted_at": datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    }

    incoming = {
        **existing,
        "extracted_at": datetime(
            2026, 10, 9, 19, 0, tzinfo=timezone.utc
        ),
    }

    result = decide_fact_action(
        existing=existing,
        incoming=incoming,
    )

    assert result == "update"


def test_same_prices_with_older_extraction_should_remain_unchanged():
    """Preserve the latest extraction timestamp when prices match."""

    existing = {
        "open": Decimal("250.00000000"),
        "high": Decimal("255.00000000"),
        "low": Decimal("248.00000000"),
        "close": Decimal("253.00000000"),
        "volume": 1000000,
        "extracted_at": datetime(
            2026, 10, 9, 19, 0, tzinfo=timezone.utc
        ),
    }

    incoming = {
        **existing,
        "extracted_at": datetime(
            2026, 10, 9, 18, 0, tzinfo=timezone.utc
        ),
    }

    result = decide_fact_action(
        existing=existing,
        incoming=incoming,
    )

    assert result == "unchanged"