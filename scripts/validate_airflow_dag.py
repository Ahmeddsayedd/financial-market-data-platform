"""Validate the financial market DAG using Apache Airflow itself.

Run this script inside the Airflow Docker container.
"""

from pathlib import Path

from airflow.models.dagbag import DagBag # pyright: ignore[reportMissingImports]


DAG_ID = "financial_market_pipeline"
DAG_FOLDER = Path("/opt/airflow/dags")

EXPECTED_DEPENDENCIES = {
    "check_pipeline_configuration": {
        "prepare_pipeline_run",
        "ingest_raw_market_data",
    },
    "prepare_pipeline_run": {
        "summarize_pipeline_run",
    },
    "summarize_pipeline_run": set(),
    "ingest_raw_market_data": {
        "process_raw_to_silver",
    },
    "process_raw_to_silver": set(),
}


def main() -> None:
    dag_bag = DagBag(
        dag_folder=str(DAG_FOLDER),
        include_examples=False,
    )

    assert not dag_bag.import_errors, (
        f"DAG import errors: {dag_bag.import_errors}"
    )

    dag = dag_bag.get_dag(DAG_ID)
    assert dag is not None, f"DAG not found: {DAG_ID}"

    assert set(dag.task_ids) == set(EXPECTED_DEPENDENCIES)
    assert dag.catchup is False
    assert dag.is_paused_upon_creation is True
    assert dag.start_date.utcoffset().total_seconds() == 0

    for task_id, expected_downstream in EXPECTED_DEPENDENCIES.items():
        actual_downstream = dag.get_task(task_id).downstream_task_ids
        assert actual_downstream == expected_downstream, (
            f"{task_id}: expected {expected_downstream}, "
            f"got {actual_downstream}"
        )

    ingestion_task = dag.get_task("ingest_raw_market_data")
    assert ingestion_task.retries == 0

    print("PASS: DAG imports successfully")
    print("PASS: All five tasks are registered")
    print("PASS: Task dependency chain is correct")
    print("PASS: UTC start date, catchup, and paused defaults")


if __name__ == "__main__":
    main()