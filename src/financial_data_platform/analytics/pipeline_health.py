"""Deterministic, database-independent health checks for recorded pipeline runs.

This is an assessment of *observed* execution history, not proof that Airflow,
PostgreSQL, or scheduled ingestion is currently operational.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Literal, Sequence

from financial_data_platform.analytics.pipeline_monitoring import MAX_RUNS, PipelineRun

HealthStatus = Literal["healthy", "degraded", "unknown"]


@dataclass(frozen=True)
class HealthThresholds:
    """Positive duration limits in hours (not driven by untrusted env values)."""

    recent_failure_hours: int = 24
    stale_running_hours: int = 2
    recent_success_hours: int = 48

    def __post_init__(self) -> None:
        for name in (
            "recent_failure_hours",
            "stale_running_hours",
            "recent_success_hours",
        ):
            value = getattr(self, name)
            if type(value) is not int or value <= 0 or value > 8760:
                raise ValueError(f"{name} must be an integer between 1 and 8760")


@dataclass(frozen=True)
class PipelineHealth:
    status: HealthStatus
    assessed_at: datetime
    reasons: tuple[str, ...]
    recent_failures: int
    stale_running: int
    recent_successes: int
    examined_runs: int
    history_truncated: bool


def assess_pipeline_health(
    runs: Sequence[PipelineRun],
    *,
    now: datetime | None = None,
    thresholds: HealthThresholds | None = None,
) -> PipelineHealth:
    """Assess latest unfiltered run history without I/O or counter-based alarms.

    Boundaries are inclusive. A full MAX_RUNS page cannot prove absence of
    older failures, so a non-degraded result remains unknown in that case.
    """
    limits = thresholds if thresholds is not None else HealthThresholds()
    if not isinstance(limits, HealthThresholds):
        raise ValueError("thresholds must be HealthThresholds")
    observed_at = datetime.now(timezone.utc) if now is None else now
    if not isinstance(observed_at, datetime) or observed_at.utcoffset() is None:
        raise ValueError("now must be a timezone-aware datetime")
    observed_at = observed_at.astimezone(timezone.utc)
    if len(runs) > MAX_RUNS:
        raise ValueError("health history exceeds the supported 500-run limit")

    failure_cutoff = observed_at - timedelta(hours=limits.recent_failure_hours)
    running_cutoff = observed_at - timedelta(hours=limits.stale_running_hours)
    success_cutoff = observed_at - timedelta(hours=limits.recent_success_hours)
    future_timestamp = False
    failures = 0
    stale = 0
    successes = 0

    for run in runs:
        if run.status not in {"success", "failed", "running"}:
            raise ValueError("unknown pipeline run status")
        if run.started_at.utcoffset() is None or (
            run.finished_at is not None and run.finished_at.utcoffset() is None
        ):
            raise ValueError("run timestamps must be timezone-aware")
        started_at = run.started_at.astimezone(timezone.utc)
        finished_at = (
            run.finished_at.astimezone(timezone.utc)
            if run.finished_at is not None
            else None
        )
        if started_at > observed_at or (
            finished_at is not None and finished_at > observed_at
        ):
            future_timestamp = True
            continue
        if run.status == "failed" and (finished_at or started_at) >= failure_cutoff:
            failures += 1
        elif run.status == "running" and started_at <= running_cutoff:
            stale += 1
        elif run.status == "success" and (finished_at or started_at) >= success_cutoff:
            successes += 1

    truncated = len(runs) == MAX_RUNS
    if failures or stale:
        reasons = []
        if failures:
            reasons.append(f"{failures} failed execution(s) within the failure window.")
        if stale:
            reasons.append(f"{stale} running execution(s) exceeded the age threshold.")
        state: HealthStatus = "degraded"
    elif future_timestamp:
        state = "unknown"
        reasons = ["Future-dated execution timestamps require clock verification."]
    elif truncated:
        state = "unknown"
        reasons = ["The 500-run limit prevents a complete health assessment."]
    elif not runs:
        state = "unknown"
        reasons = ["No pipeline execution history is available."]
    elif successes:
        state = "healthy"
        reasons = [
            "A recent successful run was observed with no recent failures "
            "or stale runs."
        ]
    else:
        state = "unknown"
        reasons = ["No recent successful execution is available to establish health."]

    return PipelineHealth(
        status=state,
        assessed_at=observed_at,
        reasons=tuple(reasons),
        recent_failures=failures,
        stale_running=stale,
        recent_successes=successes,
        examined_runs=len(runs),
        history_truncated=truncated,
    )
