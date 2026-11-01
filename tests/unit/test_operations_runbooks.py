"""Static contracts for the M9 operator-only documentation (#75)."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OPS = ROOT / "docs" / "operations"


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_operations_documents_and_index_links_exist():
    index = read("docs/operations/README.md")
    for filename in (
        "secrets-and-least-privilege.md",
        "operations-runbook.md",
        "backup-and-recovery.md",
        "airflow-compose-health.md",
        "structured-pipeline-logging.md",
        "pipeline-health-assessment.md",
    ):
        assert (OPS / filename).is_file()
        assert f"]({filename})" in index


def test_readme_links_to_operations_index():
    assert "](docs/operations/README.md)" in read("README.md")


def test_secrets_document_has_distinct_db_roles_and_safe_verification():
    doc = read("docs/operations/secrets-and-least-privilege.md")
    for required in (
        "AIRFLOW_POSTGRES_PASSWORD",
        "POSTGRES_PASSWORD",
        "AIRFLOW_JWT_SECRET",
        "TWELVE_DATA_API_KEY",
        "dashboard_reader",
        "GRANT SELECT",
        "has_table_privilege",
        "SET TRANSACTION READ ONLY",
    ):
        assert required in doc
    assert "no database-level" in doc.lower()


def test_backup_is_manual_and_guarded():
    doc = read("docs/operations/backup-and-recovery.md")
    assert "operator approval" in doc.lower()
    assert "pg_dump" in doc and "pg_restore" in doc
    assert "new isolated restore target" in doc.lower()
    assert "--volumes" in doc  # Warning, not an executable action
    assert "```bash\npg_restore " not in doc


def test_runbook_does_not_enable_live_execution():
    doc = read("docs/operations/operations-runbook.md")
    assert "docker compose -f compose.airflow.yaml ps -a" in doc
    assert "python scripts/validate_compose_health.py" in doc
    assert "down --volumes" in doc  # An explicit warning
    assert "ENABLE_TWELVE_DATA_INGESTION=true" not in doc
    assert "ENABLE_GOLD_LOADING=true" not in doc


def test_airflow_setup_reflects_current_seven_task_dag():
    doc = read("docs/airflow-local-setup.md")
    assert "seven" in doc.lower()
    assert "load_silver_to_gold" in doc
    assert "start_execution_tracking" in doc
    assert "No custom financial ETL DAGs are included" not in doc
