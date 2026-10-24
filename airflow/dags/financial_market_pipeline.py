"""First Airflow DAG for the Financial Market Data Platform.

Issue #31: Demonstrate task orchestration without accessing
external financial APIs or modifying the Gold warehouse.
"""

from datetime import datetime, timedelta, timezone

from airflow.sdk import DAG, task # pyright: ignore[reportMissingImports]


dag = DAG(
    dag_id="financial_market_pipeline",
    description="Demonstration financial market orchestration workflow",
    start_date=datetime(2026, 10, 1, tzinfo=timezone.utc),
    schedule="@daily",
    catchup=False,
    is_paused_upon_creation=True,
    default_args={
        "retries": 1,
        "retry_delay": timedelta(minutes=1),
    },
    max_active_runs=1,
    tags=["financial-market", "development"],
)


@task(dag=dag)
def check_pipeline_configuration() -> dict[str, str]:
    """Validate the non-sensitive demonstration configuration."""
    pipeline_name = "financial_market_pipeline"
    execution_mode = "demonstration"

    if not pipeline_name:
        raise ValueError("Pipeline name must not be empty")

    configuration = {
        "pipeline": pipeline_name,
        "mode": execution_mode,
        "status": "configuration_valid",
    }

    print(f"Configuration validated for {pipeline_name}")
    return configuration


@task(dag=dag)
def prepare_pipeline_run(
    configuration: dict[str, str],
) -> dict[str, str]:
    """Prepare deterministic metadata for a demonstration run."""
    if configuration["status"] != "configuration_valid":
        raise ValueError("Pipeline configuration is not valid")

    run_metadata = {
        "pipeline": configuration["pipeline"],
        "mode": configuration["mode"],
        "stage": "prepared",
        "data_source": "none",
    }

    print("Demonstration pipeline run prepared")
    return run_metadata


@task(dag=dag)
def summarize_pipeline_run(
    run_metadata: dict[str, str],
) -> dict[str, str]:
    """Summarize successful completion of the demonstration run."""
    if run_metadata["stage"] != "prepared":
        raise ValueError("Pipeline run was not prepared")

    summary = {
        "pipeline": run_metadata["pipeline"],
        "status": "success",
        "mode": run_metadata["mode"],
        "message": "Airflow demonstration completed successfully",
    }

    print(summary["message"])
    return summary


# TaskFlow automatically creates dependencies when one task's
# output is passed as another task's argument.
configuration = check_pipeline_configuration()
prepared_run = prepare_pipeline_run(configuration)
completion_summary = summarize_pipeline_run(prepared_run)