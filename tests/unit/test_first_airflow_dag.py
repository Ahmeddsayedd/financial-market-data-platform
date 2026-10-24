"""Static structural tests for the first Airflow DAG.

Airflow itself is tested inside its Docker container.
These tests do not require installing Airflow on Windows.
"""

import ast
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DAG_FILE = (
    PROJECT_ROOT
    / "airflow"
    / "dags"
    / "financial_market_pipeline.py"
)

EXPECTED_TASKS = {
    "check_pipeline_configuration",
    "prepare_pipeline_run",
    "summarize_pipeline_run",
}


def load_dag_source() -> str:
    """Read the DAG source code."""
    return DAG_FILE.read_text(encoding="utf-8")


def load_dag_ast() -> ast.Module:
    """Parse the DAG without importing Apache Airflow locally."""
    return ast.parse(load_dag_source())


def get_function_names() -> set[str]:
    """Extract declared functions from the DAG file."""
    return {
        node.name
        for node in load_dag_ast().body
        if isinstance(node, ast.FunctionDef)
    }


def test_dag_file_exists():
    """The financial market DAG must exist."""
    assert DAG_FILE.is_file()


def test_dag_source_has_valid_python_syntax():
    """The DAG source must parse as valid Python."""
    assert isinstance(load_dag_ast(), ast.Module)


def test_dag_id_is_correct():
    """The DAG must use its stable project identifier."""
    assert 'dag_id="financial_market_pipeline"' in load_dag_source()


def test_all_three_tasks_are_defined():
    """The DAG must declare its three demonstration tasks."""
    assert EXPECTED_TASKS.issubset(get_function_names())


def test_all_tasks_use_taskflow_decorator():
    """The three task functions must be decorated with @task."""
    task_functions = {
        node.name: node
        for node in load_dag_ast().body
        if isinstance(node, ast.FunctionDef)
        and node.name in EXPECTED_TASKS
    }

    for function in task_functions.values():
        assert any(
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Name)
            and decorator.func.id == "task"
            for decorator in function.decorator_list
        )


def test_daily_schedule_is_configured():
    """The DAG must run on a daily schedule when enabled."""
    assert 'schedule="@daily"' in load_dag_source()


def test_historical_catchup_is_disabled():
    """Historical DAG runs must not be generated automatically."""
    assert "catchup=False" in load_dag_source()


def test_dag_starts_paused():
    """The DAG must not schedule runs automatically on creation."""
    assert "is_paused_upon_creation=True" in load_dag_source()


def test_dag_uses_utc_timezone():
    """The start date must be timezone-aware."""
    assert "timezone.utc" in load_dag_source()


def test_taskflow_dependency_chain():
    """Task outputs must connect the three stages in order."""
    source = load_dag_source()

    assert (
        "configuration = check_pipeline_configuration()"
        in source
    )
    assert (
        "prepared_run = prepare_pipeline_run(configuration)"
        in source
    )
    assert (
        "completion_summary = summarize_pipeline_run(prepared_run)"
        in source
    )


def test_no_external_data_dependencies():
    """The demonstration must not require real market services."""
    source = load_dag_source()

    forbidden = (
        "import requests",
        "import psycopg",
        "TWELVE_DATA_API_KEY",
        "POSTGRES_PASSWORD",
    )

    for value in forbidden:
        assert value not in source