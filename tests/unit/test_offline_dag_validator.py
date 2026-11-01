"""Guard offline DAG validation against metadata-database access."""

import ast
from pathlib import Path


VALIDATOR = Path(__file__).resolve().parents[2] / "scripts" / "validate_airflow_dag.py"


def test_offline_validator_uses_parsed_dag_dictionary():
    """The validator must not use DagBag.get_dag(), which can query the DB."""
    tree = ast.parse(VALIDATOR.read_text(encoding="utf-8"))
    calls = [node.func for node in ast.walk(tree) if isinstance(node, ast.Call)]
    assert any(
        isinstance(call, ast.Attribute)
        and call.attr == "get"
        and isinstance(call.value, ast.Attribute)
        and call.value.attr == "dags"
        for call in calls
    )
    assert not any(
        isinstance(call, ast.Attribute) and call.attr == "get_dag" for call in calls
    )
