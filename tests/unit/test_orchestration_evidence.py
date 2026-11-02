"""Read-only orchestration evidence: isolation, provenance and failure modes."""

import json
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from financial_data_platform.experiments import orchestration_evidence as evidence
from scripts import collect_orchestration_evidence as cli

RUN = "manual__2026-11-03T10:00:00+00:00"


def test_untrusted_run_and_database_names_are_rejected(monkeypatch):
    monkeypatch.setenv("POSTGRES_DB", evidence.TEST_DATABASE)
    for run_id in ("", "../../../etc", "a" * 201):
        with pytest.raises(evidence.EvidenceError):
            evidence.validate_inputs(
                airflow_run_id=run_id,
                symbol="AAPL",
                confirmation=evidence.TEST_DATABASE,
            )
    with pytest.raises(evidence.EvidenceError):
        evidence.validate_inputs(
            airflow_run_id=RUN, symbol="aapl", confirmation=evidence.TEST_DATABASE
        )
    monkeypatch.setenv("POSTGRES_DB", "financial_market")
    with pytest.raises(evidence.EvidenceError):
        evidence.validate_inputs(
            airflow_run_id=RUN, symbol="AAPL", confirmation=evidence.TEST_DATABASE
        )


def _connection(
    *, database="financial_market_test", run_status="success", missing=False
):
    connection = MagicMock()
    cursor = connection.cursor.return_value.__enter__.return_value
    cursor.fetchone.side_effect = [
        (database,),
        None
        if missing
        else (
            "financial_market_pipeline",
            run_status,
            datetime(2026, 11, 3, tzinfo=timezone.utc),
            datetime(2026, 11, 3, tzinfo=timezone.utc),
            Decimal("1.200"),
            100,
            100,
            100,
            100,
            0,
            "twelve_data",
        ),
        (100, 100, date(2026, 6, 11), date(2026, 11, 2), 99, 81, 51, 80, 86, 100, 80),
    ]
    return connection, cursor


def test_collect_exact_run_and_gold_read_only(monkeypatch):
    monkeypatch.setenv("POSTGRES_DB", evidence.TEST_DATABASE)
    conn, cursor = _connection()
    with (
        patch.object(evidence, "_connect_database", return_value=conn),
        patch.object(evidence, "_source_commit", return_value="a" * 40),
    ):
        result = evidence.collect_orchestration_evidence(
            airflow_run_id=RUN, symbol="AAPL", confirmation=evidence.TEST_DATABASE
        )
    assert result["airflow_tracking"]["status"] == "success"
    assert result["gold_snapshot"]["row_count"] == 100
    assert result["gold_snapshot"]["indicator_non_null_counts"]["sma_50"] == 51
    assert result["api_requests"] == result["database_writes"] == 0
    assert conn.rollback.call_count == 1
    assert conn.commit.call_count == 0
    assert conn.close.call_count == 1
    statements = [c.args[0] for c in cursor.execute.call_args_list]
    assert statements[0] == "SET TRANSACTION READ ONLY"
    assert all("INSERT" not in s and "UPDATE" not in s for s in statements)
    assert cursor.execute.call_args_list[3].args[1] == ("twelve_data", "AAPL")


def test_unexpected_db_and_missing_run_fail_without_write(monkeypatch):
    monkeypatch.setenv("POSTGRES_DB", evidence.TEST_DATABASE)
    for kwargs in ({"database": "financial_market"}, {"missing": True}):
        conn, _ = _connection(**kwargs)
        with patch.object(evidence, "_connect_database", return_value=conn):
            with pytest.raises(evidence.EvidenceError):
                evidence.collect_orchestration_evidence(
                    airflow_run_id=RUN,
                    symbol="AAPL",
                    confirmation=evidence.TEST_DATABASE,
                )
        conn.commit.assert_not_called()
        conn.close.assert_called_once()


def test_nonterminal_tracking_is_not_presented_as_success(monkeypatch):
    monkeypatch.setenv("POSTGRES_DB", evidence.TEST_DATABASE)
    conn, _ = _connection(run_status="running")
    with patch.object(evidence, "_connect_database", return_value=conn):
        result = evidence.collect_orchestration_evidence(
            airflow_run_id=RUN, symbol="AAPL", confirmation=evidence.TEST_DATABASE
        )
    assert not result["interpretation"]["tracking_terminal_success"]


def test_cli_never_overwrites_and_requires_test_database(monkeypatch, tmp_path):
    monkeypatch.setenv("POSTGRES_DB", "financial_market")
    output = tmp_path / "report.json"
    assert (
        cli.main(
            [
                "--airflow-run-id",
                RUN,
                "--confirm-test-db",
                evidence.TEST_DATABASE,
                "--output",
                str(output),
            ]
        )
        == 1
    )
    assert not output.exists()
    monkeypatch.setenv("POSTGRES_DB", evidence.TEST_DATABASE)
    with (
        patch.object(cli, "EXPERIMENT_DIR", tmp_path),
        patch.object(
            cli,
            "collect_orchestration_evidence",
            return_value={
                "airflow_tracking": {"status": "success"},
                "gold_snapshot": {"row_count": 100},
            },
        ) as collector,
    ):
        assert (
            cli.main(
                [
                    "--airflow-run-id",
                    RUN,
                    "--confirm-test-db",
                    evidence.TEST_DATABASE,
                    "--output",
                    str(output),
                ]
            )
            == 0
        )
        assert json.loads(output.read_text())["gold_snapshot"]["row_count"] == 100
        assert (
            cli.main(
                [
                    "--airflow-run-id",
                    RUN,
                    "--confirm-test-db",
                    evidence.TEST_DATABASE,
                    "--output",
                    str(output),
                ]
            )
            == 1
        )
        assert collector.call_count == 1
