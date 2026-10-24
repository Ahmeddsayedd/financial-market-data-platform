"""First Airflow DAG for the Financial Market Data Platform.

Issue #31: Demonstrate task orchestration without accessing
external financial APIs or modifying the Gold warehouse.
"""
import os
from pathlib import Path

from datetime import datetime, timedelta, timezone

from airflow.sdk import DAG, get_current_context, task  # pyright: ignore[reportMissingImports]


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


@task(dag=dag, retries=0)
def ingest_raw_market_data(
    configuration: dict[str, str],
) -> dict[str, object]:
    """Optionally ingest one symbol into the Raw data layer.

    Disabled by default to protect the Twelve Data free API quota.
    """
    if configuration["status"] != "configuration_valid":
        raise ValueError("Pipeline configuration is invalid")

    # Both environmental permission and explicit DAG-run authorization
    # are required before any real Twelve Data request.
    environment_enabled = (
        os.getenv("ENABLE_TWELVE_DATA_INGESTION", "false").lower()
        == "true"
    )

    context = get_current_context()
    dag_run = context["dag_run"]
    run_configuration = dag_run.conf or {}

    run_authorized = (
        run_configuration.get("allow_live_ingestion") is True
    )

    if not (environment_enabled and run_authorized):
        print("Live Twelve Data ingestion disabled; no request sent.")
        return {
            "status": "disabled",
            "provider": "twelve_data",
            "symbols": [],
            "files_written": 0,
            "raw_paths": [],
        }

    # Imported only when live ingestion is explicitly enabled.
    from financial_data_platform.orchestration.ingestion import (
        ingest_market_symbols,
    )

    return ingest_market_symbols(
        symbols=("AAPL",),
        raw_base_dir=Path("/opt/financial-data/raw"),
    )

@task(dag=dag, retries=0)
def process_raw_to_silver(
    ingestion_result: dict[str, object],
) -> dict[str, object]:
    """Transform one explicitly selected Raw file into Silver Parquet.

    Can use a file produced by this DAG run or an existing Raw file
    selected through DAG run configuration. No API call occurs here.
    """
    from financial_data_platform.orchestration.silver import (
        process_raw_file_to_silver,
    )

    raw_base_dir = Path("/opt/financial-data/raw")

    context = get_current_context()
    run_configuration = context["dag_run"].conf or {}

    explicit_path = run_configuration.get("raw_relative_path")

    if explicit_path is not None:
        if not isinstance(explicit_path, str) or not explicit_path:
            raise ValueError(
                "raw_relative_path must be a nonempty string"
            )
        selected_path = explicit_path
    elif ingestion_result["status"] == "success":
        raw_paths = ingestion_result["raw_paths"]

        if not isinstance(raw_paths, list) or len(raw_paths) != 1:
            raise ValueError(
                "Exactly one ingested Raw path is required"
            )

        selected_path = str(
            Path(raw_paths[0]).relative_to(raw_base_dir)
        )
    else:
        print(
            "Raw-to-Silver processing disabled: "
            "no Raw file was selected."
        )
        return {
            "status": "disabled",
            "total_records": 0,
            "valid_count": 0,
            "invalid_count": 0,
            "silver_paths": [],
            "quarantine_paths": [],
        }

    return process_raw_file_to_silver(
        raw_relative_path=selected_path,
        raw_base_dir=raw_base_dir,
        silver_base_dir=Path("/opt/financial-data/silver"),
        quarantine_base_dir=Path("/opt/financial-data/quarantine"),
    )

@task(dag=dag, retries=0)
def load_silver_to_gold(
    silver_result: dict[str, object],
) -> dict[str, object]:
    """Load selected Silver partitions into the test Gold warehouse."""

    context = get_current_context()
    run_configuration = context["dag_run"].conf or {}

    environment_enabled = (
        os.getenv("ENABLE_GOLD_LOADING", "false").lower() == "true"
    )
    run_authorized = run_configuration.get("allow_gold_loading") is True

    if not (environment_enabled and run_authorized):
        print("Gold loading disabled; no database write attempted.")
        return {
            "status": "disabled",
            "files_loaded": 0,
            "records_read": 0,
        }

    # Additional development safeguard: never write to the main
    # Gold database during Issue #37.
    if os.getenv("POSTGRES_DB") != "financial_market_test":
        raise ValueError(
            "Gold loading is restricted to financial_market_test"
        )

    silver_root = Path("/opt/financial-data/silver")

    explicit_paths = run_configuration.get("silver_relative_paths")

    if explicit_paths is not None:
        if (
            not isinstance(explicit_paths, list)
            or not explicit_paths
            or not all(
                isinstance(path, str) and path
                for path in explicit_paths
            )
        ):
            raise ValueError(
                "silver_relative_paths must be a nonempty list of strings"
            )

        selected_paths = explicit_paths

    elif silver_result["status"] == "success":
        absolute_paths = silver_result["silver_paths"]

        if not isinstance(absolute_paths, list) or not absolute_paths:
            raise ValueError(
                "Successful Silver processing must provide output paths"
            )

        selected_paths = [
            str(Path(path).relative_to(silver_root))
            for path in absolute_paths
        ]

    else:
        print("Gold loading disabled: no Silver file selected.")
        return {
            "status": "disabled",
            "files_loaded": 0,
            "records_read": 0,
        }

    from financial_data_platform.orchestration.gold import (
        load_silver_paths_to_gold,
    )

    return load_silver_paths_to_gold(
        relative_paths=selected_paths,
        silver_base_dir=silver_root,
    )

# TaskFlow automatically creates dependencies when one task's
# output is passed as another task's argument.
configuration = check_pipeline_configuration()
prepared_run = prepare_pipeline_run(configuration)
completion_summary = summarize_pipeline_run(prepared_run)
raw_ingestion = ingest_raw_market_data(configuration)
silver_processing = process_raw_to_silver(raw_ingestion)
gold_loading = load_silver_to_gold(silver_processing)