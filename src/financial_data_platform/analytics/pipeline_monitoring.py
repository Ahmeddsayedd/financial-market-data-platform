"""Read-only access to recorded Gold pipeline executions."""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from financial_data_platform.warehouse.db import connect_to_database

MAX_RUNS = 500
STATUSES = frozenset({"running", "success", "failed"})


@dataclass(frozen=True)
class PipelineRun:
    run_id: UUID
    dag_id: str | None
    started_at: datetime
    finished_at: datetime | None
    status: str
    records_extracted: int
    records_validated: int
    records_transformed: int
    records_loaded: int
    records_rejected: int
    duration_seconds: Decimal | None
    source: str | None


@dataclass(frozen=True)
class PipelineRunSummary:
    run_count: int
    success_count: int
    failed_count: int
    running_count: int
    records_extracted: int
    records_validated: int
    records_transformed: int
    records_loaded: int
    records_rejected: int


def _read_rows(query: str, params: tuple = ()) -> list[tuple]:
    """Run a fixed SELECT through a PostgreSQL read-only transaction."""
    with connect_to_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SET TRANSACTION READ ONLY")
            cursor.execute(query, params)
            return cursor.fetchall()


def list_pipeline_sources() -> list[str]:
    """List known non-null sources in alphabetical order."""
    rows = _read_rows(
        "SELECT DISTINCT source FROM pipeline_run "
        "WHERE source IS NOT NULL ORDER BY source ASC"
    )
    return [row[0] for row in rows]


def list_pipeline_runs(
    *,
    source: str | None = None,
    status: str | None = None,
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = MAX_RUNS,
) -> list[PipelineRun]:
    """Fetch newest recorded runs, filtering on inclusive UTC start dates.

    A source filter of None also includes records with a NULL source.
    Returned rows are limited; the result is not a count of all matching runs.
    """
    if source is not None and (not isinstance(source, str) or not source.strip()):
        raise ValueError("source must be a nonblank string or None")
    if status is not None and (not isinstance(status, str) or status not in STATUSES):
        raise ValueError("invalid pipeline status")
    for name, value in (("start_date", start_date), ("end_date", end_date)):
        if value is not None and type(value) is not date:
            raise ValueError(f"{name} must be a date or None")
    if start_date is not None and end_date is not None and start_date > end_date:
        raise ValueError("start_date must not be after end_date")
    if type(limit) is not int or not 1 <= limit <= MAX_RUNS:
        raise ValueError("limit must be an integer between 1 and 500")

    query = """
        SELECT run_id, dag_id, started_at, finished_at, status,
               records_extracted, records_validated, records_transformed,
               records_loaded, records_rejected, duration_seconds, source
        FROM pipeline_run
        WHERE TRUE
    """
    params: list = []
    if source is not None:
        query += " AND source = %s"
        params.append(source)
    if status is not None:
        query += " AND status = %s"
        params.append(status)
    if start_date is not None:
        query += " AND (started_at AT TIME ZONE 'UTC') >= %s::date"
        params.append(start_date)
    if end_date is not None:
        query += " AND (started_at AT TIME ZONE 'UTC') < (%s::date + INTERVAL '1 day')"
        params.append(end_date)
    query += " ORDER BY started_at DESC, run_id DESC LIMIT %s"
    params.append(limit)
    return [PipelineRun(*row) for row in _read_rows(query, tuple(params))]


def summarize_pipeline_runs(runs: list[PipelineRun]) -> PipelineRunSummary:
    """Aggregate returned run records, not all database history."""
    return PipelineRunSummary(
        run_count=len(runs),
        success_count=sum(run.status == "success" for run in runs),
        failed_count=sum(run.status == "failed" for run in runs),
        running_count=sum(run.status == "running" for run in runs),
        records_extracted=sum(run.records_extracted for run in runs),
        records_validated=sum(run.records_validated for run in runs),
        records_transformed=sum(run.records_transformed for run in runs),
        records_loaded=sum(run.records_loaded for run in runs),
        records_rejected=sum(run.records_rejected for run in runs),
    )
