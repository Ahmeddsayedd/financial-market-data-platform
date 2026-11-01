"""Static, offline M9 verification contracts; no containers, DB, or API calls."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_JOBS = {
    "lint",
    "unit-tests",
    "integration-tests",
    "compose-validation",
    "release-dashboard-image",
    "airflow-smoke",
    "dashboard-smoke",
}


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_all_seven_ci_jobs_are_present():
    workflow = read(".github/workflows/ci.yml")
    jobs = workflow.split("\njobs:\n", 1)[1]
    found = set(re.findall(r"^  ([a-z][a-z0-9-]+):\s*$", jobs, flags=re.M))
    assert EXPECTED_JOBS <= found
    assert "pull_request:" in workflow


def test_no_automated_registry_release_or_production_deploy():
    workflow = read(".github/workflows/ci.yml")
    assert not re.search(r"\bdocker\s+(?:push|login)\b", workflow)
    assert not re.search(r"\b(?:kubectl\s+apply|helm\s+upgrade)\b", workflow)


def test_dashboard_image_context_excludes_sensitive_content():
    rules = read(".dockerignore").splitlines()
    # The existing release image build uses a default-deny context.
    assert any(line.strip() in {"*", "**"} for line in rules)
    assert any(line.strip() == "!pyproject.toml" for line in rules)
    assert any(line.strip() == "!src/" for line in rules)
    assert not any(
        line.strip() in {"!.env", "!data/", "!airflow/logs/"} for line in rules
    )


def test_dashboard_image_uses_nonroot_runtime():
    dockerfile = read("Dockerfile.dashboard")
    assert re.search(r"(?m)^USER\s+\S+", dockerfile)
    assert "streamlit" in dockerfile.lower()
    assert "8501" in dockerfile


def test_airflow_safety_defaults_and_write_restriction():
    dag = read("airflow/dags/financial_market_pipeline.py")
    compose = read("compose.airflow.yaml")
    assert "is_paused_upon_creation=True" in dag
    assert "catchup=False" in dag
    assert 'run_configuration.get("allow_live_ingestion") is True' in dag
    assert 'run_configuration.get("allow_gold_loading") is True' in dag
    assert '"financial_market_test"' in dag
    assert (
        "ENABLE_TWELVE_DATA_INGESTION: ${ENABLE_TWELVE_DATA_INGESTION:-false}"
        in compose
    )
    assert "ENABLE_GOLD_LOADING: ${ENABLE_GOLD_LOADING:-false}" in compose


def test_read_only_dashboard_query_boundaries():
    for path in (
        "src/financial_data_platform/analytics/queries.py",
        "src/financial_data_platform/analytics/pipeline_monitoring.py",
    ):
        source = read(path)
        assert 'cursor.execute("SET TRANSACTION READ ONLY")' in source


def test_compose_health_and_offline_runtime_checks_are_maintained():
    ci = read(".github/workflows/ci.yml")
    assert "scripts/validate_airflow_dag.py" in ci
    assert "scripts/smoke_dashboard.py" in ci
    assert "scripts/verify_dashboard_image.py" in ci
    assert "scripts/validate_compose_health.py" in ci
    assert "--network none" in ci
    assert "docker build" in ci


def test_final_review_documentation_is_linked_and_not_prematurely_signed_off():
    index = read("docs/operations/README.md")
    plan = read("docs/operations/m9-implementation-plan.md")
    report = read("docs/operations/m9-final-verification.md")
    assert "m9-final-verification.md" in index
    assert "#79" in plan
    assert "PENDING" in report
    assert "527 tests passed" in report  # historical baseline, not current proof
    assert "Do not close" in report
