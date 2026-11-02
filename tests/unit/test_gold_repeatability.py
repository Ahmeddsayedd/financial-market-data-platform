"""Offline Gold experiment guards and logical-state contracts."""

from dataclasses import replace
from datetime import timedelta

import pytest

from financial_data_platform.experiments import gold_repeatability as gold
from financial_data_platform.warehouse.gold_conflicts import decide_fact_action


def test_synthetic_fixture_is_valid_and_repeatable():
    first, digest_a = gold._fixture(20261001, "M10TEST")
    second, digest_b = gold._fixture(20261001, "M10TEST")
    assert first == second
    assert digest_a == digest_b
    assert len(first) == 2
    assert all(record.source == gold.SOURCE for record in first)
    assert len({record.observation_date for record in first}) == 2


@pytest.mark.parametrize("seed", [-1, True, "1"])
def test_reject_invalid_seed(seed):
    with pytest.raises(ValueError, match="seed"):
        gold._fixture(seed, "M10TEST")


def test_different_seed_changes_fixture_digest():
    assert gold._fixture(1, "X")[1] != gold._fixture(2, "X")[1]


def test_requires_explicit_authorization(monkeypatch):
    monkeypatch.setenv("POSTGRES_DB", gold.TEST_DB)
    with pytest.raises(ValueError, match="authorization"):
        gold._ensure_test_database(False)


@pytest.mark.parametrize("name", ["financial_market", "financial_market_test_copy", ""])
def test_refuses_non_test_database(monkeypatch, name):
    monkeypatch.setenv("POSTGRES_DB", name)
    with pytest.raises(ValueError, match="POSTGRES_DB"):
        gold._ensure_test_database(True)


def test_missing_password_fails_before_connection(monkeypatch):
    monkeypatch.setenv("POSTGRES_DB", gold.TEST_DB)
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    with pytest.raises(ValueError, match="POSTGRES_PASSWORD"):
        gold._ensure_test_database(True)


def test_output_is_never_overwritten(tmp_path):
    path = tmp_path / "report.json"
    path.write_text("original", encoding="utf8")
    with pytest.raises(FileExistsError):
        gold._output_path(path)
    assert path.read_text(encoding="utf8") == "original"


@pytest.mark.parametrize("filename", ["result.jsonl", "result.txt"])
def test_output_must_be_json(tmp_path, filename):
    with pytest.raises(ValueError, match=".json"):
        gold._output_path(tmp_path / filename)


def test_output_parent_must_exist(tmp_path):
    with pytest.raises(ValueError, match="parent"):
        gold._output_path(tmp_path / "missing" / "result.json")


def test_conflict_decisions_cover_all_gold_scenarios():
    initial, _ = gold._fixture(123, "M10TEST")
    record = initial[0]
    incoming = {
        "open": record.open,
        "high": record.high,
        "low": record.low,
        "close": record.close,
        "volume": record.volume,
        "extracted_at": record.extracted_at,
    }
    assert decide_fact_action(None, incoming) == "insert"
    assert decide_fact_action(incoming, incoming) == "unchanged"
    new = dict(incoming, extracted_at=record.extracted_at + timedelta(minutes=1))
    assert decide_fact_action(incoming, new) == "update"
    assert decide_fact_action(new, incoming) == "unchanged"
    assert decide_fact_action(new, dict(new, volume=new["volume"] + 1)) == "reject"


def test_state_hash_stable_and_changes_with_observation(monkeypatch):
    class Reader:
        pass

    cursor = Reader()
    records, _ = gold._fixture(123, "M10TEST")
    monkeypatch.setattr(gold, "read_gold_market_records", lambda *args: records)
    digest_a, count_a, _ = gold._state(cursor, "M10TEST")
    digest_b, count_b, _ = gold._state(cursor, "M10TEST")
    assert count_a == count_b == 2
    assert digest_a == digest_b
    records[0] = replace(records[0], volume=records[0].volume + 1)
    assert gold._state(cursor, "M10TEST")[0] != digest_a


def test_no_db_connection_without_authorization(tmp_path, monkeypatch):
    def forbidden():
        raise AssertionError("Unexpected connection")

    monkeypatch.setattr(gold, "connect_to_database", forbidden)
    with pytest.raises(ValueError, match="authorization"):
        gold.run_gold_repeatability(output=tmp_path / "r.json")


class FakeConnection:
    def __init__(self, server_db=gold.TEST_DB):
        self.server_db = server_db
        self.autocommit = False
        self.records = []
        self.rollback_calls = 0
        self.closed = False

    def cursor(self):
        return FakeCursor(self)

    def rollback(self):
        self.rollback_calls += 1
        self.records = []

    def close(self):
        self.closed = True


class FakeCursor:
    def __init__(self, connection):
        self.connection = connection
        self.last = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        if "current_database()" in sql:
            self.last = (self.connection.server_db,)
        elif "COUNT(*) FROM dim_asset" in sql:
            self.last = (0,)
        elif sql.startswith("SET LOCAL"):
            pass
        else:
            raise AssertionError("Unexpected SQL")

    def fetchone(self):
        return self.last


def _fake_gold(monkeypatch, connection):
    monkeypatch.setenv("POSTGRES_DB", gold.TEST_DB)
    monkeypatch.setenv("POSTGRES_PASSWORD", "unit-test-placeholder")
    monkeypatch.setattr(gold, "connect_to_database", lambda: connection)
    monkeypatch.setattr(
        gold,
        "read_gold_market_records",
        lambda cursor, source, symbol: sorted(
            connection.records, key=lambda record: record.observation_date
        ),
    )

    def load(cursor, records):
        counts = dict(inserted=0, updated=0, unchanged=0, rejected=0)
        for incoming in records:
            existing = next(
                (
                    r
                    for r in connection.records
                    if r.observation_date == incoming.observation_date
                ),
                None,
            )
            if existing is None:
                counts["inserted"] += 1
                connection.records.append(incoming)
                continue
            fields = ("open", "high", "low", "close", "volume", "extracted_at")
            action = decide_fact_action(
                {key: getattr(existing, key) for key in fields},
                {key: getattr(incoming, key) for key in fields},
            )
            counts[
                {"update": "updated", "unchanged": "unchanged", "reject": "rejected"}[
                    action
                ]
            ] += 1
            if action == "update":
                connection.records[connection.records.index(existing)] = incoming
        return counts

    monkeypatch.setattr(gold, "load_market_batch", load)


def test_successful_experiment_rolls_back_all_data(tmp_path, monkeypatch):
    connection = FakeConnection()
    _fake_gold(monkeypatch, connection)
    output = tmp_path / "evidence.json"
    result = gold.run_gold_repeatability(output=output, authorize_test_db=True)
    assert [row["scenario"] for row in result["scenarios"]] == list(gold.SCENARIOS)
    assert [row["inserted"] for row in result["scenarios"]] == [2, 0, 0, 0, 0]
    assert [row["updated"] for row in result["scenarios"]] == [0, 0, 1, 0, 0]
    assert [row["rejected"] for row in result["scenarios"]] == [0, 0, 0, 0, 1]
    assert result["rolled_back"] is True
    assert connection.rollback_calls == 1
    assert connection.closed and not connection.records
    assert output.is_file()
    assert all(row["elapsed_ns"] > 0 for row in result["scenarios"])


def test_server_database_guard_rolls_back(tmp_path, monkeypatch):
    connection = FakeConnection(server_db="financial_market")
    _fake_gold(monkeypatch, connection)
    with pytest.raises(ValueError, match="Server-side"):
        gold.run_gold_repeatability(
            output=tmp_path / "evidence.json", authorize_test_db=True
        )
    assert connection.rollback_calls == 1 and connection.closed
    assert not (tmp_path / "evidence.json").exists()


def test_failure_rolls_back_and_does_not_publish_evidence(tmp_path, monkeypatch):
    connection = FakeConnection()
    _fake_gold(monkeypatch, connection)

    def fail(cursor, records):
        raise RuntimeError("simulated error")

    monkeypatch.setattr(gold, "load_market_batch", fail)
    with pytest.raises(RuntimeError, match="simulated"):
        gold.run_gold_repeatability(
            output=tmp_path / "evidence.json", authorize_test_db=True
        )
    assert connection.rollback_calls == 1 and connection.closed
    assert not (tmp_path / "evidence.json").exists()


def test_reject_autocommit_connection_before_any_gold_write(tmp_path, monkeypatch):
    connection = FakeConnection()
    connection.autocommit = True
    _fake_gold(monkeypatch, connection)
    with pytest.raises(ValueError, match="rollback-capable"):
        gold.run_gold_repeatability(
            output=tmp_path / "evidence.json", authorize_test_db=True
        )
    assert connection.rollback_calls == 1 and connection.closed
    assert not (tmp_path / "evidence.json").exists()
