"""Tests for the Silver-to-Gold orchestration adapter."""

from unittest.mock import patch

import pytest

from financial_data_platform.orchestration.gold import (
    load_silver_paths_to_gold,
)


def create_silver_file(tmp_path, name="symbol=AAPL/year=2026/data.parquet"):
    root = tmp_path / "silver"
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"mock-parquet")
    return root, name


def test_loads_selected_silver_file(tmp_path):
    root, relative_path = create_silver_file(tmp_path)
    sample_records = [object(), object()]

    with (
        patch(
            "financial_data_platform.orchestration.gold.read_silver_parquet",
            return_value=sample_records,
        ) as reader,
        patch(
            "financial_data_platform.orchestration.gold.load_market_records",
            return_value={
                "inserted": 2,
                "updated": 0,
                "unchanged": 0,
                "rejected": 0,
            },
        ) as loader,
    ):
        result = load_silver_paths_to_gold(
            relative_paths=[relative_path],
            silver_base_dir=root,
        )

    assert result["status"] == "success"
    assert result["files_loaded"] == 1
    assert result["records_read"] == 2
    assert result["inserted"] == 2
    reader.assert_called_once()
    loader.assert_called_once_with(sample_records)


def test_multiple_files_use_one_database_transaction(tmp_path):
    root, first = create_silver_file(
        tmp_path, "symbol=AAPL/year=2026/data.parquet"
    )
    _, second = create_silver_file(
        tmp_path, "symbol=MSFT/year=2026/data.parquet"
    )

    with (
        patch(
            "financial_data_platform.orchestration.gold.read_silver_parquet",
            side_effect=[["aapl"], ["msft"]],
        ),
        patch(
            "financial_data_platform.orchestration.gold.load_market_records",
            return_value={
                "inserted": 2,
                "updated": 0,
                "unchanged": 0,
                "rejected": 0,
            },
        ) as loader,
    ):
        result = load_silver_paths_to_gold(
            relative_paths=[first, second],
            silver_base_dir=root,
        )

    assert result["files_loaded"] == 2
    assert result["records_read"] == 2
    loader.assert_called_once_with(["aapl", "msft"])


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "../outside.parquet",
        "../../secrets.parquet",
        "/tmp/outside.parquet",
    ],
)
def test_rejects_paths_outside_silver_root(tmp_path, unsafe_path):
    with pytest.raises(ValueError):
        load_silver_paths_to_gold(
            relative_paths=[unsafe_path],
            silver_base_dir=tmp_path,
        )


def test_rejects_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_silver_paths_to_gold(
            relative_paths=["symbol=AAPL/year=2026/data.parquet"],
            silver_base_dir=tmp_path,
        )


def test_rejects_duplicate_files(tmp_path):
    root, relative_path = create_silver_file(tmp_path)

    with pytest.raises(ValueError, match="Duplicate"):
        load_silver_paths_to_gold(
            relative_paths=[relative_path, relative_path],
            silver_base_dir=root,
        )


def test_rejects_empty_file_selection(tmp_path):
    with pytest.raises(ValueError, match="At least one"):
        load_silver_paths_to_gold(
            relative_paths=[],
            silver_base_dir=tmp_path,
        )


def test_rejects_non_parquet_file(tmp_path):
    root, _ = create_silver_file(tmp_path, "records.json")

    with pytest.raises(ValueError, match="Parquet"):
        load_silver_paths_to_gold(
            relative_paths=["records.json"],
            silver_base_dir=root,
        )


def test_database_failure_is_propagated(tmp_path):
    root, relative_path = create_silver_file(tmp_path)

    with (
        patch(
            "financial_data_platform.orchestration.gold.read_silver_parquet",
            return_value=["record"],
        ),
        patch(
            "financial_data_platform.orchestration.gold.load_market_records",
            side_effect=RuntimeError("Database unavailable"),
        ),
    ):
        with pytest.raises(RuntimeError, match="Database unavailable"):
            load_silver_paths_to_gold(
                relative_paths=[relative_path],
                silver_base_dir=root,
            )


def test_empty_parquet_records_do_not_open_database(tmp_path):
    root, relative_path = create_silver_file(tmp_path)

    with (
        patch(
            "financial_data_platform.orchestration.gold.read_silver_parquet",
            return_value=[],
        ),
        patch(
            "financial_data_platform.orchestration.gold.load_market_records",
        ) as loader,
    ):
        with pytest.raises(ValueError, match="no records"):
            load_silver_paths_to_gold(
                relative_paths=[relative_path],
                silver_base_dir=root,
            )

    loader.assert_not_called()