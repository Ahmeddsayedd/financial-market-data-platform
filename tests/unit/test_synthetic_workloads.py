"""Offline contract tests for M10 deterministic synthetic workloads."""

import hashlib
import json
from datetime import datetime, timezone

import pytest

from financial_data_platform.experiments.workloads import (
    DEFAULT_SEED,
    PROFILES,
    build_payloads,
    write_workload,
)
from financial_data_platform.providers.twelve_data.parser import (
    TwelveDataParseError,
    parse_time_series,
)
from financial_data_platform.validation.market_data import (
    partition_market_data_records,
)


EXTRACTED_AT = datetime(2026, 10, 2, tzinfo=timezone.utc)


def _actual_counts(payloads):
    total = valid = invalid = 0
    violations = {}
    for payload in payloads.values():
        result = partition_market_data_records(
            parse_time_series(payload, extracted_at=EXTRACTED_AT)
        )
        total += len(result.valid_records) + len(result.invalid_records)
        valid += len(result.valid_records)
        invalid += len(result.invalid_records)
        for rejected in result.invalid_records:
            for violation in rejected.violations:
                violations[violation.code] = violations.get(violation.code, 0) + 1
    return total, valid, invalid, violations


@pytest.mark.parametrize("profile", PROFILES)
def test_clean_profiles_parse_and_validate(profile):
    payloads, manifest = build_payloads(profile=profile, symbol_count=4)
    total, valid, invalid, violations = _actual_counts(payloads)
    assert total == valid == PROFILES[profile]
    assert invalid == 0
    assert violations == {}
    assert manifest["expected_unique_observations"] == total


@pytest.mark.parametrize(
    ("scenario", "invalid_count"), [("mixed", 23), ("invalid_only", 0)]
)
def test_labeled_invalid_observations_match_real_validation(scenario, invalid_count):
    payloads, manifest = build_payloads(
        scenario=scenario, invalid_count=invalid_count, symbol_count=7
    )
    total, valid, invalid, violations = _actual_counts(payloads)
    assert total == 100
    assert valid == manifest["expected_financial_valid"]
    assert invalid == manifest["expected_financial_rejections"]
    assert violations == manifest["expected_violation_occurrences_by_code"]
    assert len(violations) == 6


def test_duplicate_date_is_a_parser_failure_not_financial_rejection():
    payloads, manifest = build_payloads(scenario="duplicate_date")
    with pytest.raises(TwelveDataParseError, match="Duplicate observation date"):
        parse_time_series(next(iter(payloads.values())), extracted_at=EXTRACTED_AT)
    assert manifest["expected_parser_failed_batches"] == 1
    assert manifest["expected_financial_rejections"] is None


def test_reproducible_bytes_and_manifest_are_identical(tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    manifest_a = write_workload(output_dir=first, scenario="mixed", invalid_count=11)
    manifest_b = write_workload(output_dir=second, scenario="mixed", invalid_count=11)
    assert manifest_a == manifest_b
    for relative_path, expected in manifest_a["file_sha256"].items():
        a = (first / relative_path).read_bytes()
        b = (second / relative_path).read_bytes()
        assert a == b
        assert hashlib.sha256(a).hexdigest() == expected
    assert (first / "manifest.json").read_bytes() == (
        second / "manifest.json"
    ).read_bytes()
    assert manifest_a["seed"] == DEFAULT_SEED
    assert "tmp" not in json.dumps(manifest_a)


def test_different_seed_changes_dataset(tmp_path):
    first = write_workload(output_dir=tmp_path / "a", seed=1)
    second = write_workload(output_dir=tmp_path / "b", seed=2)
    assert first["dataset_sha256"] != second["dataset_sha256"]


def test_refuses_overwrite_without_changing_original(tmp_path):
    output = tmp_path / "dataset"
    write_workload(output_dir=output)
    original = (output / "manifest.json").read_bytes()
    with pytest.raises(FileExistsError):
        write_workload(output_dir=output, seed=999)
    assert (output / "manifest.json").read_bytes() == original


@pytest.mark.parametrize(
    "config",
    [
        {"symbol_count": 0},
        {"symbol_count": 101},
        {"seed": -1},
        {"seed": True},
        {"invalid_count": -1},
        {"scenario": "mixed", "invalid_count": 0},
        {"scenario": "mixed", "invalid_count": 100},
        {"scenario": "clean", "invalid_count": 1},
        {"scenario": "bogus"},
        {"profile": "bogus"},
    ],
)
def test_invalid_configuration_is_rejected(config):
    with pytest.raises(ValueError):
        build_payloads(**config)


def test_no_network_or_db_required(tmp_path, monkeypatch):
    import socket

    def deny(*args, **kwargs):
        raise AssertionError("Unexpected network connection")

    monkeypatch.setattr(socket, "create_connection", deny)
    manifest = write_workload(output_dir=tmp_path / "offline")
    assert manifest["expected_unique_observations"] == 100


def test_generates_valid_unique_dates_with_single_symbol():
    payloads, _ = build_payloads(profile="medium", symbol_count=1)
    records = parse_time_series(
        next(iter(payloads.values())), extracted_at=EXTRACTED_AT
    )
    assert len(records) == 1000
    assert len({item.observation_date for item in records}) == 1000
