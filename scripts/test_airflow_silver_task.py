"""Behavioral tests for the Raw-to-Silver Airflow task.

Run inside the Airflow scheduler container.
The Silver processing adapter is mocked.
"""

import importlib.util
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


DAG_FILE = Path("/opt/airflow/dags/financial_market_pipeline.py")

spec = importlib.util.spec_from_file_location(
    "financial_market_pipeline_silver_test",
    DAG_FILE,
)

if spec is None or spec.loader is None:
    raise RuntimeError("Cannot load Airflow DAG")

module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

RAW_RELATIVE_PATH = "twelve_data/AAPL/2026/10/24/20261024T160953206116Z.json"

RAW_ABSOLUTE_PATH = "/opt/financial-data/raw/" + RAW_RELATIVE_PATH

MOCK_RESULT = {
    "status": "success",
    "raw_path": RAW_ABSOLUTE_PATH,
    "total_records": 30,
    "valid_count": 30,
    "invalid_count": 0,
    "silver_paths": ["/mock/silver.parquet"],
    "quarantine_paths": [],
}


def execute_task(*, run_conf, ingestion_result):
    context = {"dag_run": SimpleNamespace(conf=run_conf)}

    with (
        patch.object(
            module,
            "get_current_context",
            return_value=context,
        ),
        patch(
            "financial_data_platform.orchestration.silver.process_raw_file_to_silver",
            return_value=MOCK_RESULT,
        ) as mocked_processor,
    ):
        result = module.process_raw_to_silver.function(ingestion_result)

    return result, mocked_processor


disabled_ingestion = {
    "status": "disabled",
    "raw_paths": [],
}

successful_ingestion = {
    "status": "success",
    "raw_paths": [RAW_ABSOLUTE_PATH],
}


# Scenario 1: No file and no live ingestion.
result, processor = execute_task(
    run_conf={},
    ingestion_result=disabled_ingestion,
)

assert result["status"] == "disabled"
processor.assert_not_called()
print("PASS: No selected Raw file disables processing")


# Scenario 2: An explicitly selected existing Raw file.
result, processor = execute_task(
    run_conf={"raw_relative_path": RAW_RELATIVE_PATH},
    ingestion_result=disabled_ingestion,
)

assert result == MOCK_RESULT
processor.assert_called_once()
assert processor.call_args.kwargs["raw_relative_path"] == RAW_RELATIVE_PATH
print("PASS: Explicit Raw file is processed offline")


# Scenario 3: Consume the file produced by ingestion.
result, processor = execute_task(
    run_conf={},
    ingestion_result=successful_ingestion,
)

assert result == MOCK_RESULT
processor.assert_called_once()
assert processor.call_args.kwargs["raw_relative_path"] == RAW_RELATIVE_PATH
print("PASS: Newly ingested Raw file is selected")


# Scenario 4: An invalid explicit file selection.
try:
    execute_task(
        run_conf={"raw_relative_path": ""},
        ingestion_result=disabled_ingestion,
    )
except ValueError:
    print("PASS: Empty Raw path is rejected")
else:
    raise AssertionError("Empty Raw path should be rejected")


print("PASS: All four Silver task scenarios")
