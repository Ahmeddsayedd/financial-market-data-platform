# M9 — Read-only pipeline health assessment (#73)

The **Pipeline monitoring** page now displays a separate operational health
summary, always assessed from the latest **unfiltered** `pipeline_run` records.
Changing the page's source, status, or date filters does not hide failures in the
health summary. Existing filters, nine displayed counters, and the run table still
apply to the user-selected results only.

## Rules and defaults

`financial_data_platform.analytics.pipeline_health.assess_pipeline_health` is
pure Python. `HealthThresholds` accepts positive integer durations in hours,
up to 8760. Its defaults are:

| Rule | Default | Interpretation |
| --- | --- | --- |
| Recent failure | 24 hours | A failed run completed within this window is degraded |
| Stale running | 2 hours | A run still marked running for at least this long is degraded |
| Recent success | 48 hours | A recent successful completion supports healthy |

**Degraded** takes priority when a recent failed execution or stale running
execution is present. **Healthy** means at least one recent success and no
recent failures or stale running runs *in the examined records*. **Unknown**
means no history, no recent success, future-dated timestamps, or a full 500-run
result whose older history cannot be inspected. At exact threshold boundaries,
the event qualifies (inclusive comparison). Failure recency uses `finished_at`
when available, falling back to `started_at`.

Zero extracted, loaded, or rejected counters are **not** a health signal.
Data-quality rejection counts are not equivalent to an operational failure.
The assessment is not an Airflow heartbeat or a guarantee that a paused DAG will
run in the future. Neither healthy nor unknown means the market feed is fresh.

## Read-only query boundary

The dashboard reuses the existing `list_pipeline_runs` function. That function
executes fixed, parameterized `SELECT` statements in a PostgreSQL transaction
with `SET TRANSACTION READ ONLY`. For unfiltered page views the same retrieved
rows are used twice, without another query. If any page filter is applied, a
separate unfiltered `list_pipeline_runs(limit=500)` reads the health history;
this deliberately prevents a `status=success` filter from hiding failures.
If that additional read fails, the dashboard shows a generic health-unavailable
message without printing connection strings or exceptions.

The 500-run cap is intentional: assessment cannot prove global health when the
history is truncated. No migrations, mutations, retries, background refresh,
external alerts, or live provider requests are added.

## Local verification

```bash
python -m pytest -q tests/unit/test_pipeline_health.py tests/unit/test_dashboard_pipeline_health.py
python -m ruff check .
python -m ruff format --check .
python scripts/run_tests.py
python scripts/smoke_dashboard.py
```

The latest complete-suite baseline before #73 was **485 tests**; report fresh
results rather than assuming a particular total. All six existing GitHub
Actions jobs must remain green.
