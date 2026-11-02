"""No-network, no-DB unit tests for Issue #104 evidence collection."""

import hashlib
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from financial_data_platform.experiments import end_to_end_evidence as evidence
from financial_data_platform.experiments.live_market_verification import (
    VerificationError,
)

REPO = Path(__file__).resolve().parents[2]
SAFE = REPO / "data/experiments"


def _setup():
    SAFE.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.TemporaryDirectory(dir=SAFE)
    root = Path(tmp.name)
    raw = root / "raw/twelve_data/AAPL/2026/11/02/response.json"
    raw.parent.mkdir(parents=True)
    raw.write_text('{"synthetic_test_fixture":true}', encoding="utf-8")
    return tmp, root, raw


def _summary(raw, root, valid=100):
    return {
        "api_requests": 0,
        "gold_write_enabled": False,
        "raw_sha256": hashlib.sha256(raw.read_bytes()).hexdigest(),
        "raw_file": raw.relative_to(root).as_posix(),
        "records_parsed": valid,
        "earliest_date": "2026-06-11",
        "latest_date": "2026-11-02",
        "silver_files": 1,
        "quality": {
            "total_records": valid,
            "valid_count": valid,
            "invalid_count": 0,
            "acceptance_rate": 1.0,
            "rejection_rate": 0.0,
            "violation_counts": {},
        },
        "fetch_or_replay_seconds": 0.001,
        "raw_to_silver_seconds": 0.6,
    }


def test_distributions_are_measured_not_extrapolated():
    assert evidence._distribution([0.1, 0.3, 0.2])["median"] == 0.2
    assert evidence._distribution([0.3, 0.3])["population_stddev"] == 0


def test_offline_replay_report_contains_only_measured_results():
    tmp, root, raw = _setup()
    try:
        with patch.object(
            evidence, "verify_market_data", return_value=_summary(raw, root)
        ) as call:
            result = evidence.run_replay_experiment(
                root=root,
                raw_path=raw,
                symbol="AAPL",
                report_path=root / "report.json",
                repetitions=3,
                warmups=1,
            )
        assert call.call_count == 4
        assert all(
            kwargs.kwargs["write_gold"] is False for kwargs in call.call_args_list
        )
        assert result["repetitions"] == 3 and result["warmups"] == 1
        assert result["api_requests"] == result["gold_writes"] == 0
        assert result["raw_to_silver_seconds"]["median"] == 0.6
        assert (
            json.loads((root / "report.json").read_text())["quality"]["valid_count"]
            == 100
        )
        with pytest.raises(VerificationError, match="overwrite"):
            evidence.run_replay_experiment(
                root=root,
                raw_path=raw,
                symbol="AAPL",
                report_path=root / "report.json",
            )
    finally:
        tmp.cleanup()


def test_changed_quality_fails_and_does_not_publish_report():
    tmp, root, raw = _setup()
    try:
        with patch.object(
            evidence,
            "verify_market_data",
            side_effect=[
                _summary(raw, root),
                _summary(raw, root, valid=99),
            ],
        ):
            with pytest.raises(VerificationError, match="Inconsistent"):
                evidence.run_replay_experiment(
                    root=root,
                    raw_path=raw,
                    symbol="AAPL",
                    report_path=root / "report.json",
                    repetitions=2,
                    warmups=0,
                )
        assert not (root / "report.json").exists()
    finally:
        tmp.cleanup()


def test_incorrect_provenance_is_rejected():
    tmp, root, raw = _setup()
    try:
        summary = _summary(raw, root)
        summary["api_requests"] = 1
        with patch.object(evidence, "verify_market_data", return_value=summary):
            with pytest.raises(VerificationError, match="provenance"):
                evidence.run_replay_experiment(
                    root=root,
                    raw_path=raw,
                    symbol="AAPL",
                    report_path=root / "report.json",
                    repetitions=2,
                    warmups=0,
                )
    finally:
        tmp.cleanup()


@pytest.mark.parametrize("repetitions,warmups", [(1, 0), (11, 0), (True, 0), (2, 4)])
def test_invalid_repetition_bounds(repetitions, warmups):
    with pytest.raises(VerificationError):
        evidence.run_replay_experiment(
            root=SAFE,
            raw_path=Path("missing"),
            symbol="AAPL",
            report_path=SAFE / "report.json",
            repetitions=repetitions,
            warmups=warmups,
        )


def test_gold_audit_refuses_wrong_database_before_connection(monkeypatch):
    monkeypatch.setenv("POSTGRES_DB", "financial_market")
    with patch.object(evidence, "require_isolated_database") as identity:
        with pytest.raises(VerificationError, match="financial_market_test"):
            evidence.audit_test_gold(
                symbol="AAPL", confirmation="financial_market_test"
            )
    identity.assert_not_called()


def test_raw_outside_experiment_is_refused():
    tmp, root, raw = _setup()
    try:
        external = root / "outside.json"
        external.write_text("{}", encoding="utf-8")
        with pytest.raises(VerificationError, match="experiment/raw"):
            evidence.run_replay_experiment(
                root=root,
                raw_path=external,
                symbol="AAPL",
                report_path=root / "report.json",
            )
    finally:
        tmp.cleanup()


def test_gold_audit_is_read_only_and_parameterized(monkeypatch):
    from datetime import date
    from unittest.mock import MagicMock
    from types import ModuleType
    import sys

    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.side_effect = [
        ("financial_market_test",),
        (100, date(2026, 6, 11), date(2026, 11, 2), 100, 100, 81, 51, 86, 99, 80, 80),
    ]
    db = ModuleType("financial_data_platform.warehouse.db")
    db.connect_to_database = lambda: connection
    with (
        patch.object(evidence, "require_isolated_database") as preflight,
        patch.dict(sys.modules, {"financial_data_platform.warehouse.db": db}),
    ):
        audit = evidence.audit_test_gold(
            symbol="AAPL", confirmation="financial_market_test"
        )
    preflight.assert_called_once_with(confirmation="financial_market_test")
    assert audit["row_count"] == audit["distinct_dates"] == 100
    assert audit["indicator_non_null_counts"]["sma_50"] == 51
    assert cursor.execute.call_args_list[0].args == ("SET TRANSACTION READ ONLY",)
    assert cursor.execute.call_args_list[-1].args[1] == ("twelve_data", "AAPL")
    connection.rollback.assert_called_once()
    connection.close.assert_called_once()


def test_cli_denies_db_audit_without_confirmation():
    from scripts import collect_thesis_evidence as cli

    result = cli.main(
        [
            "--replay-raw",
            "not-a-file",
            "--output",
            "unused.json",
            "--audit-test-gold",
        ]
    )
    assert result == 1
