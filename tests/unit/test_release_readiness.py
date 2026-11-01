"""Contract checks for Issue #77 release safety and documentation."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_dockerignore_defaults_to_deny():
    rules = _read(".dockerignore").splitlines()
    assert "*" in rules
    assert "!src/" in rules
    assert "!src/**" in rules
    assert "!scripts/verify_dashboard_image.py" in rules
    assert not any(line.startswith("!data") for line in rules)
    assert not any(line.startswith("!.env") for line in rules)


def test_dashboard_dockerfile_restricts_copy_and_runs_non_root():
    content = _read("Dockerfile.dashboard")
    assert "COPY . ." not in content
    assert "COPY src/ ./src/" in content
    assert "COPY pyproject.toml README.md ./" in content
    assert "USER dashboard" in content
    assert "--server.address=0.0.0.0" in content
    assert "_stcore/health" in content
    assert ".env" not in content


def test_offline_verifier_has_strict_network_isolation_in_ci():
    workflow = _read(".github/workflows/ci.yml")
    job = workflow.split("  release-dashboard-image:", 1)[1].split(
        "  airflow-smoke:", 1
    )[0]
    assert "docker build" in job
    assert "Dockerfile.dashboard" in job
    assert "--network none" in job
    assert "verify_dashboard_image.py" in job
    assert "docker push" not in workflow
    assert "docker login" not in workflow


def test_dashboard_verifier_uses_only_offline_credentials():
    content = _read("scripts/verify_dashboard_image.py")
    assert '"POSTGRES_PORT": "1"' in content
    assert '"ENABLE_TWELVE_DATA_INGESTION": "false"' in content
    assert '"ENABLE_GOLD_LOADING": "false"' in content
    assert '"TWELVE_DATA_API_KEY": ""' in content
    assert "subprocess.DEVNULL" in content


def test_existing_airflow_dag_smoke_is_preserved():
    workflow = _read(".github/workflows/ci.yml")
    assert "Dockerfile.airflow" in workflow
    assert "validate_airflow_dag.py" in workflow
    assert "--network none" in workflow


def test_documentation_describes_provenance_and_limits():
    doc = _read("docs/operations/release-readiness.md")
    for term in (
        "commit SHA",
        "image digest/ID",
        "version ranges",
        "rollback",
        "operator approval",
        "not digest-pinned",
        "--network none",
        "down --volumes",
    ):
        assert term.lower() in doc.lower()
    index = _read("docs/operations/README.md")
    assert "[Release readiness](release-readiness.md)" in index
    assert "(**#77**)" in _read("docs/operations/m9-implementation-plan.md")
