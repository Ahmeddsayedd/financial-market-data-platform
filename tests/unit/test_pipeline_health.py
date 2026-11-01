"""Deterministic health assessments, without PostgreSQL or Streamlit."""

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from financial_data_platform.analytics.pipeline_health import (
    HealthThresholds,
    assess_pipeline_health,
)
from financial_data_platform.analytics.pipeline_monitoring import PipelineRun

NOW = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def run(status="success", *, started_hours=1, finished_hours=0.5):
    return PipelineRun(
        uuid4(),
        "financial_market_pipeline",
        NOW - timedelta(hours=started_hours),
        None if status == "running" else NOW - timedelta(hours=finished_hours),
        status,
        0,
        0,
        0,
        0,
        0,
        Decimal("1.000"),
        "twelve_data",
    )


def check(runs, **kwargs):
    return assess_pipeline_health(runs, now=NOW, **kwargs)


def test_empty_history_is_unknown():
    result = check([])
    assert result.status == "unknown"
    assert result.examined_runs == 0


def test_success_with_zero_counters_is_healthy():
    result = check([run()])
    assert result.status == "healthy"
    assert result.recent_successes == 1


def test_recent_failure_is_degraded_even_with_success():
    result = check([run(), run("failed")])
    assert result.status == "degraded"
    assert result.recent_failures == 1


def test_failure_window_uses_finish_time():
    result = check([run("failed", started_hours=72, finished_hours=1)])
    assert result.status == "degraded"


def test_older_failure_does_not_degrade():
    assert (
        check([run(), run("failed", started_hours=80, finished_hours=30)]).status
        == "healthy"
    )


def test_stale_running_is_degraded():
    result = check([run("running", started_hours=3)])
    assert result.stale_running == 1
    assert result.status == "degraded"


def test_young_running_without_success_is_unknown():
    assert check([run("running", started_hours=1)]).status == "unknown"


def test_old_success_is_unknown():
    assert check([run(started_hours=80, finished_hours=72)]).status == "unknown"


def test_failure_boundary_inclusive():
    assert (
        check([run("failed", started_hours=25, finished_hours=24)]).status == "degraded"
    )


def test_stale_boundary_inclusive():
    assert check([run("running", started_hours=2)]).status == "degraded"


def test_success_boundary_inclusive():
    assert check([run(started_hours=49, finished_hours=48)]).status == "healthy"


def test_timezone_offsets_are_normalized():
    offset = timezone(timedelta(hours=2))
    success = run()
    success = replace(
        success,
        started_at=success.started_at.astimezone(offset),
        finished_at=success.finished_at.astimezone(offset),
    )
    assert check([success]).status == "healthy"


def test_future_timestamp_is_unknown():
    assert check([run(started_hours=-1, finished_hours=-2)]).status == "unknown"


def test_500_run_limit_does_not_create_false_healthy_status():
    assert check([run()] * 500).status == "unknown"


def test_500_run_limit_still_detects_failures():
    assert check([run("failed"), *([run()] * 499)]).status == "degraded"


@pytest.mark.parametrize("value", [0, -1, 1.5, True, "4", 8761])
def test_invalid_thresholds_rejected(value):
    with pytest.raises(ValueError):
        HealthThresholds(recent_failure_hours=value)


def test_configurable_thresholds():
    thresholds = HealthThresholds(stale_running_hours=4)
    assert (
        check([run("running", started_hours=3)], thresholds=thresholds).status
        == "unknown"
    )


def test_naive_now_rejected():
    with pytest.raises(ValueError):
        assess_pipeline_health([run()], now=datetime(2026, 11, 1))


def test_naive_run_timestamp_rejected():
    with pytest.raises(ValueError):
        check([replace(run(), started_at=datetime(2026, 11, 1))])


def test_invalid_status_rejected():
    with pytest.raises(ValueError):
        check([replace(run(), status="unknown")])


def test_oversized_history_rejected():
    with pytest.raises(ValueError):
        check([run()] * 501)
