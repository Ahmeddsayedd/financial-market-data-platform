"""Read-only monitoring integration tests using only financial_market_test."""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from financial_data_platform.analytics.pipeline_monitoring import (
    list_pipeline_runs,
    list_pipeline_sources,
)
from financial_data_platform.warehouse.db import (
    connect_to_database,
    get_database_config,
)

pytestmark = pytest.mark.integration
TEST_DATABASE = "financial_market_test"


@pytest.fixture
def seeded_pipeline_runs(monkeypatch):
    """Commit unique test-owned runs; remove only those UUIDs afterward."""
    monkeypatch.setenv("POSTGRES_DB", TEST_DATABASE)
    assert get_database_config()["dbname"] == TEST_DATABASE

    ids = [uuid4(), uuid4()]
    # Dates are far in the future to distinguish fixtures from actual runs.
    times = [
        datetime(2090, 5, 20, 23, 59, tzinfo=timezone.utc),
        datetime(2090, 5, 21, 0, 0, tzinfo=timezone.utc),
    ]
    with connect_to_database() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database()")
            assert cursor.fetchone()[0] == TEST_DATABASE
            for run_id, started_at, status, source in zip(
                ids, times, ("success", "failed"), ("monitoring_fixture", None)
            ):
                cursor.execute(
                    """
                    INSERT INTO pipeline_run (
                        run_id, dag_id, started_at, finished_at, status,
                        source, records_extracted, records_validated,
                        records_transformed, records_loaded, records_rejected,
                        duration_seconds
                    ) VALUES (
                        %s, 'monitoring_test', %s, %s, %s, %s,
                        10, 8, 8, 7, 2, 60.000
                    )
                    """,
                    (
                        run_id,
                        started_at,
                        started_at + timedelta(minutes=1),
                        status,
                        source,
                    ),
                )

    try:
        yield ids, times
    finally:
        with connect_to_database() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT current_database()")
                if cursor.fetchone()[0] != TEST_DATABASE:
                    raise RuntimeError("Refusing cleanup outside test database")
                cursor.execute(
                    "DELETE FROM pipeline_run WHERE run_id = ANY(%s)", (ids,)
                )


def test_monitoring_reads_committed_pipeline_run(seeded_pipeline_runs):
    ids, _ = seeded_pipeline_runs
    runs = list_pipeline_runs(source="monitoring_fixture", limit=500)
    matching = [run for run in runs if run.run_id == ids[0]]
    assert len(matching) == 1
    assert matching[0].status == "success"
    assert matching[0].records_rejected == 2
    assert matching[0].duration_seconds == Decimal("60.000")
    assert "monitoring_fixture" in list_pipeline_sources()


def test_monitoring_status_and_inclusive_utc_date_filter(seeded_pipeline_runs):
    ids, _ = seeded_pipeline_runs
    runs = list_pipeline_runs(
        status="success", start_date=date(2090, 5, 20), end_date=date(2090, 5, 20)
    )
    assert any(run.run_id == ids[0] for run in runs)
    assert all(run.run_id != ids[1] for run in runs)


def test_monitoring_newest_first_and_null_source_visible(seeded_pipeline_runs):
    ids, _ = seeded_pipeline_runs
    runs = list_pipeline_runs(start_date=date(2090, 5, 20), end_date=date(2090, 5, 21))
    positions = {run.run_id: index for index, run in enumerate(runs)}
    assert ids[0] in positions and ids[1] in positions
    assert positions[ids[1]] < positions[ids[0]]
    null_source_run = next(run for run in runs if run.run_id == ids[1])
    assert null_source_run.source is None
