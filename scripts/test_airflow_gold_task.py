"""Behavioral tests for Gold loading authorization in Airflow.

Run inside the Airflow scheduler container.
The Gold loader is mocked, so no database writes occur.
"""

import importlib.util
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

DAG_FILE = Path("/opt/airflow/dags/financial_market_pipeline.py")

spec = importlib.util.spec_from_file_location(
    "financial_market_gold_authorization_test", DAG_FILE
)
if spec is None or spec.loader is None:
    raise RuntimeError("Cannot load Airflow DAG")

module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

SILVER_RELATIVE_PATH = "symbol=AAPL/year=2026/data.parquet"

MOCK_RESULT = {
    "status": "success",
    "files_loaded": 1,
    "records_read": 30,
    "inserted": 30,
    "updated": 0,
    "unchanged": 0,
    "rejected": 0,
    "silver_paths": [
        "/opt/financial-data/silver/" + SILVER_RELATIVE_PATH
    ],
}

DISABLED_SILVER = {
    "status": "disabled",
    "silver_paths": [],
}


def run_case(
    *,
    environment_enabled,
    run_authorized,
    database="financial_market_test",
    silver_result=DISABLED_SILVER,
    explicit_paths=None,
):
    run_conf = {"allow_gold_loading": run_authorized}
    if explicit_paths is not None:
        run_conf["silver_relative_paths"] = explicit_paths

    context = {
        "dag_run": SimpleNamespace(conf=run_conf)
    }

    with (
        patch.dict(
            os.environ,
            {
                "ENABLE_GOLD_LOADING": (
                    "true" if environment_enabled else "false"
                ),
                "POSTGRES_DB": database,
            },
        ),
        patch.object(
            module,
            "get_current_context",
            return_value=context,
        ),
        patch(
            "financial_data_platform.orchestration.gold."
            "load_silver_paths_to_gold",
            return_value=MOCK_RESULT,
        ) as mocked_loader,
    ):
        result = module.load_silver_to_gold.function(silver_result)

    return result, mocked_loader


# Neither authorization is present.
result, loader = run_case(
    environment_enabled=False,
    run_authorized=False,
)
assert result["status"] == "disabled"
loader.assert_not_called()
print("PASS: Both permissions absent — no Gold write")


# Only the DAG-run permission is present.
result, loader = run_case(
    environment_enabled=False,
    run_authorized=True,
)
assert result["status"] == "disabled"
loader.assert_not_called()
print("PASS: Environment permission absent — no Gold write")


# Only the environment permission is present.
result, loader = run_case(
    environment_enabled=True,
    run_authorized=False,
)
assert result["status"] == "disabled"
loader.assert_not_called()
print("PASS: Run permission absent — no Gold write")


# Both permissions are present, with an explicit Silver file.
result, loader = run_case(
    environment_enabled=True,
    run_authorized=True,
    explicit_paths=[SILVER_RELATIVE_PATH],
)
assert result == MOCK_RESULT
loader.assert_called_once()
assert loader.call_args.kwargs["relative_paths"] == [
    SILVER_RELATIVE_PATH
]
print("PASS: Both permissions present — mocked Gold load")


# Even an authorized run must reject the main Gold database.
try:
    run_case(
        environment_enabled=True,
        run_authorized=True,
        database="financial_market",
        explicit_paths=[SILVER_RELATIVE_PATH],
    )
except ValueError as exc:
    assert "financial_market_test" in str(exc)
    print("PASS: Main Gold database is protected")
else:
    raise AssertionError("Main Gold database should be rejected")


# No Silver input means no Gold load, even when authorized.
result, loader = run_case(
    environment_enabled=True,
    run_authorized=True,
)
assert result["status"] == "disabled"
loader.assert_not_called()
print("PASS: No Silver input — no Gold write")


print("PASS: All six Gold task scenarios")