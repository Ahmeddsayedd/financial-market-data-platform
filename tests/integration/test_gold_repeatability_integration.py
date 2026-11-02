"""Isolated PostgreSQL verification: successful experiments leave no writes."""

import pytest

from financial_data_platform.experiments.gold_repeatability import (
    run_gold_repeatability,
)

pytestmark = pytest.mark.integration


def test_rollback_only_gold_scenarios(tmp_path, monkeypatch):
    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")
    evidence = run_gold_repeatability(
        output=tmp_path / "gold-evaluation.json", authorize_test_db=True
    )
    assert [row["scenario"] for row in evidence["scenarios"]] == [
        "initial",
        "replay",
        "newer_update",
        "stale_replay",
        "equal_time_conflict",
    ]
    assert all(row["matches_expected"] for row in evidence["scenarios"])
    assert evidence["rolled_back"] is True
