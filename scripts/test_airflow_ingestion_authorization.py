"""Behavioral authorization checks for the Airflow ingestion task.

Run inside the Airflow scheduler container.
All ingestion calls are mocked; this script sends no HTTP requests.
"""

import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch


DAG_FILE = Path("/opt/airflow/dags/financial_market_pipeline.py")

spec = importlib.util.spec_from_file_location(
    "financial_market_pipeline_authorization_test",
    DAG_FILE,
)

if spec is None or spec.loader is None:
    raise RuntimeError("Unable to load the Airflow DAG module")

dag_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dag_module)

configuration = {
    "status": "configuration_valid",
    "pipeline": "financial_market_pipeline",
}


def verify_case(
    *,
    environment_enabled: bool,
    run_authorized: bool,
    expected_calls: int,
) -> None:
    """Exercise the real decorated task function with mocked dependencies."""

    environment_value = "true" if environment_enabled else "false"

    context = {
        "dag_run": SimpleNamespace(conf={"allow_live_ingestion": run_authorized})
    }

    mocked_result = {
        "provider": "twelve_data",
        "status": "success",
        "symbols": ["AAPL"],
        "files_written": 1,
        "raw_paths": ["/mocked/path.json"],
    }

    with (
        patch.dict(
            os.environ,
            {"ENABLE_TWELVE_DATA_INGESTION": environment_value},
        ),
        patch.object(
            dag_module,
            "get_current_context",
            return_value=context,
        ),
        patch(
            "financial_data_platform.orchestration.ingestion.ingest_market_symbols",
            return_value=mocked_result,
        ) as mocked_ingestion,
    ):
        result = dag_module.ingest_raw_market_data.function(configuration)

    assert mocked_ingestion.call_count == expected_calls, (
        f"Expected {expected_calls} ingestion calls, got {mocked_ingestion.call_count}"
    )

    if expected_calls == 0:
        assert result["status"] == "disabled"
        assert result["files_written"] == 0
    else:
        assert result == mocked_result

    print(
        "PASS:",
        f"environment={environment_value},",
        f"run_authorized={run_authorized},",
        f"ingestion_calls={mocked_ingestion.call_count}",
    )


verify_case(
    environment_enabled=False,
    run_authorized=False,
    expected_calls=0,
)

verify_case(
    environment_enabled=False,
    run_authorized=True,
    expected_calls=0,
)

verify_case(
    environment_enabled=True,
    run_authorized=False,
    expected_calls=0,
)

verify_case(
    environment_enabled=True,
    run_authorized=True,
    expected_calls=1,
)

print("PASS: All four authorization scenarios")
