"""Offline replay preparation: no API calls or databases involved."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from financial_data_platform.orchestration.replay_demo import (
    ReplayPreparationError,
    prepare_airflow_replay,
)

STAMP = "20261102T230104258952Z.json"
REL = f"twelve_data/AAPL/2026/11/02/{STAMP}"


def make_raw(tmp_path: Path, symbol="AAPL"):
    experiments = tmp_path / "data/experiments"
    source = experiments / "issue103-live/raw" / REL
    source.parent.mkdir(parents=True, exist_ok=True)
    source.write_text(
        json.dumps(
            {"meta": {"symbol": symbol}, "values": [{"datetime": "2026-11-02"}]}
        ),
        encoding="utf-8",
    )
    return experiments, source, tmp_path / "data/raw"


def stage(tmp_path, **changes):
    experiments, source, raw_root = make_raw(tmp_path)
    arguments = dict(
        source=source,
        experiment_root=experiments,
        airflow_raw_root=raw_root,
        symbol="AAPL",
    )
    arguments.update(changes)
    return prepare_airflow_replay(**arguments)


def test_stages_raw_without_network_and_returns_guarded_configuration(tmp_path):
    with patch("socket.socket", side_effect=AssertionError("network not allowed")):
        result = stage(tmp_path)
    assert result["status"] == "READY"
    assert result["api_requests"] == 0
    assert result["copy_performed"] is True
    assert result["raw_relative_path"] == REL
    assert result["dag_run_conf"] == {
        "allow_live_ingestion": False,
        "allow_gold_loading": True,
        "raw_relative_path": REL,
    }
    assert (tmp_path / "data/raw" / REL).is_file()


def test_replay_staging_same_bytes_is_idempotent(tmp_path):
    first = stage(tmp_path)
    second = stage(tmp_path)
    assert second["copy_performed"] is False
    assert first["raw_sha256"] == second["raw_sha256"]


def test_refuses_to_replace_different_existing_raw(tmp_path):
    experiments, source, raw_root = make_raw(tmp_path)
    target = raw_root / REL
    target.parent.mkdir(parents=True)
    target.write_text("different", encoding="utf-8")
    with pytest.raises(ReplayPreparationError, match="different contents"):
        prepare_airflow_replay(
            source=source,
            experiment_root=experiments,
            airflow_raw_root=raw_root,
            symbol="AAPL",
        )
    assert target.read_text() == "different"


def test_rejects_external_file_and_symlink_escape(tmp_path):
    experiments, source, raw_root = make_raw(tmp_path)
    outside = tmp_path / "outside.json"
    outside.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    with pytest.raises(ReplayPreparationError, match="data/experiments"):
        prepare_airflow_replay(
            source=outside,
            experiment_root=experiments,
            airflow_raw_root=raw_root,
            symbol="AAPL",
        )


def test_rejects_mismatched_symbol(tmp_path):
    experiments, source, raw_root = make_raw(tmp_path, symbol="MSFT")
    with pytest.raises(ReplayPreparationError, match="Response symbol"):
        prepare_airflow_replay(
            source=source,
            experiment_root=experiments,
            airflow_raw_root=raw_root,
            symbol="AAPL",
        )


def test_rejects_invalid_json(tmp_path):
    experiments, source, raw_root = make_raw(tmp_path)
    source.write_text("not json")
    with pytest.raises(ReplayPreparationError, match="Invalid Raw JSON"):
        prepare_airflow_replay(
            source=source,
            experiment_root=experiments,
            airflow_raw_root=raw_root,
            symbol="AAPL",
        )


def test_rejects_invalid_symbol(tmp_path):
    with pytest.raises(ReplayPreparationError, match="uppercase symbol"):
        stage(tmp_path, symbol="../AAPL")
