"""Static safety tests for Airflow's real ingestion task."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DAG_FILE = ROOT / "airflow" / "dags" / "financial_market_pipeline.py"
COMPOSE_FILE = ROOT / "compose.airflow.yaml"


def get_ingestion_task() -> ast.FunctionDef:
    tree = ast.parse(DAG_FILE.read_text(encoding="utf-8"))

    return next(
        node
        for node in tree.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "ingest_raw_market_data"
    )


def test_ingestion_task_exists():
    assert get_ingestion_task().name == "ingest_raw_market_data"


def test_ingestion_has_no_airflow_retries():
    task_node = get_ingestion_task()

    assert any(
        isinstance(decorator, ast.Call)
        and any(
            keyword.arg == "retries"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value == 0
            for keyword in decorator.keywords
        )
        for decorator in task_node.decorator_list
    )


def test_live_ingestion_is_explicitly_gated():
    """Live API calls require both environment and per-run permission."""
    source = DAG_FILE.read_text(encoding="utf-8")

    assert "ENABLE_TWELVE_DATA_INGESTION" in source
    assert '"false"' in source
    assert "get_current_context()" in source
    assert 'run_configuration.get("allow_live_ingestion") is True' in source
    assert "if not (environment_enabled and run_authorized):" in source


def test_dag_reuses_existing_ingestion_adapter():
    source = DAG_FILE.read_text(encoding="utf-8")

    assert "from financial_data_platform.orchestration.ingestion import" in source
    assert "ingest_market_symbols(" in source


def test_ingestion_is_connected_to_configuration_task():
    source = DAG_FILE.read_text(encoding="utf-8")

    assert "raw_ingestion = ingest_raw_market_data(configuration)" in source


def test_scheduler_mounts_source_and_raw_storage():
    compose = COMPOSE_FILE.read_text(encoding="utf-8")

    assert "./src:/opt/financial-data/src:ro" in compose
    assert "./data/raw:/opt/financial-data/raw" in compose
    assert "PYTHONPATH: /opt/financial-data/src" in compose
    assert "ENABLE_TWELVE_DATA_INGESTION: ${ENABLE_TWELVE_DATA_INGESTION:-false}" in compose


def test_ingestion_requires_per_run_authorization():
    """Environment permission alone must not authorize API requests."""
    source = DAG_FILE.read_text(encoding="utf-8")

    assert "get_current_context()" in source
    assert 'run_configuration.get("allow_live_ingestion") is True' in source
    assert "environment_enabled and run_authorized" in source


def test_ingestion_task_has_no_automatic_retry():
    """Airflow should not multiply API requests after a failure."""
    source = DAG_FILE.read_text(encoding="utf-8")

    assert "@task(dag=dag, retries=0)" in source