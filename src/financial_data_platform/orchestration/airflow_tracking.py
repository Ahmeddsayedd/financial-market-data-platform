"""Lifecycle callbacks for Airflow execution tracking."""

from datetime import datetime, timezone

from financial_data_platform.orchestration.execution_tracking import (
    finish_pipeline_tracking,
    start_pipeline_tracking,
)


def _execution_identity(context: dict) -> tuple[str, str]:
    """Get stable identifiers from an Airflow callback context."""
    dag = context["dag"]
    dag_id = dag.dag_id

    airflow_run_id = context.get("run_id")

    if not airflow_run_id:
        dag_run = context.get("dag_run")
        airflow_run_id = getattr(dag_run, "run_id", None)

    if not airflow_run_id:
        raise ValueError("Airflow callback is missing its run ID")

    return dag_id, airflow_run_id


def _execution_start(context: dict) -> datetime:
    """Use the DAG run start time when available."""
    dag_run = context.get("dag_run")
    started_at = getattr(dag_run, "start_date", None)

    if started_at is None:
        started_at = datetime.now(timezone.utc)

    return started_at


def finalize_airflow_execution(
    context: dict,
    *,
    status: str,
) -> None:
    """Persist the final DAG status, even if initialization was missed."""
    dag_id, airflow_run_id = _execution_identity(context)

    # The start operation is idempotent. It also provides a fallback
    # if the start task failed before creating its tracking row.
    start_pipeline_tracking(
        dag_id=dag_id,
        airflow_run_id=airflow_run_id,
        started_at=_execution_start(context),
    )

    finish_pipeline_tracking(
        dag_id=dag_id,
        airflow_run_id=airflow_run_id,
        finished_at=datetime.now(timezone.utc),
        status=status,
    )

    print(f"Pipeline execution tracking finalized: dag_id={dag_id}, status={status}")


def on_airflow_success(context: dict) -> None:
    """Record successful DAG execution."""
    finalize_airflow_execution(context, status="success")


def on_airflow_failure(context: dict) -> None:
    """Record failed DAG execution."""
    finalize_airflow_execution(context, status="failed")
