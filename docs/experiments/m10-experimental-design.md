# M10 — Reproducible experimental design and metric definitions (#81)

**Status:** methodology approved for implementation review; **no performance results collected** by this issue. This document describes proposed experiments, not claims about observed throughput, accuracy, or production capacity.

## 1. System and measurement inventory

The existing flow is provider ingestion → preserved Raw JSON → parsing and financial validation → Silver Parquet or quarantine JSON → optional Gold PostgreSQL load. In the current implementation:

- `ingest_market_symbols()` returns `files_written`, symbols, and paths; **file count is not observation count**. No record-throughput claim can be derived from this stage alone.
- `process_raw_market_data()` returns `total_records`, `valid_count`, `invalid_count`, Silver paths, quarantine paths, and a `quality_report`.
- `build_quality_report()` counts each rejected **observation once**, even when one observation has multiple violations. `violation_counts` counts **violation occurrences**. Its acceptance/rejection rates are rounded to four decimals, with `0.0` for an empty batch.
- `load_silver_paths_to_gold()` returns `records_read`, `inserted`, `updated`, `unchanged`, `rejected`. Gold `inserted + updated` is the number applied; `unchanged` is not a failure and Gold `rejected` is not equivalent to Raw-to-Silver `invalid_count`.
- `build_pipeline_counters()` fills `records_extracted`, `records_validated`, `records_transformed`, `records_loaded`, `records_rejected` from successful Silver/Gold results. `records_extracted` is zero if Silver was not run; ingestion's `files_written` is deliberately not treated as a count of observations. `records_rejected` combines Silver and Gold rejections and is not an independently deduplicated record count across stages.
- Tracking `duration_seconds` is a PostgreSQL-calculated whole-DAG duration rounded to three decimal places, including waits and disabled stages. It is **not** a stage-level benchmark measurement.
- No dedicated benchmarking scripts or collected run-level resource measurements were identified in the provided source inventory.

Existing coverage includes parsed/financially invalid input, quarantine, Raw-to-Silver replay/idempotency, aggregate quality reporting, orchestration counters, Gold outcome handling, and bounded pipeline-health cases. These are functional tests; they are **not** performance measurements.

## 2. Research questions and falsifiable hypotheses

| Question | Proposed hypothesis, subject to measurement | Primary metrics |
| --- | --- | --- |
| RQ1: How does Raw-to-Silver runtime change as parsed-observation count increases? | Within a fixed local environment and fixture mix, median measured duration increases with input size. | elapsed seconds, parsed observations/sec, medians and dispersion |
| RQ2: Are financial-rule rejection outcomes invariant to workload size at a fixed injected-error fraction? | Observed invalid-record fraction matches the generator's labeled invalid fraction for structurally parseable fixtures. | invalid_count / total_records, mismatch count, per-code violation occurrences |
| RQ3: Does replay preserve logical Silver/Gold outcomes? | Reprocessing identical inputs does not increase unique Silver facts; Gold reports unchanged outcomes on replay where applicable. | unique observation identities, inserted/updated/unchanged/rejected, state checksums |
| RQ4: What variability occurs across repeated runs? | Under stable conditions, measured dispersion remains quantifiable rather than asserted to be zero. | per-run elapsed seconds, median, min/max, optional IQR |
| RQ5: How are failures represented? | Structural parse failures and unauthorized/DB-unavailable operations do not produce successful quality or throughput results. | failure reason/category, stage, no-success-metric assertion |

Hypotheses above are **proposed**. No result, p-value, threshold achievement, or empirical performance conclusion is asserted here.

## 3. Metric semantics

| Metric | Unit | Definition / denominator | Zero / missing behavior |
| --- | --- | --- | --- |
| Stage elapsed time | seconds | `time.perf_counter_ns()` stop-start around precisely one named stage; convert nanoseconds to seconds | Zero/nonpositive measurement invalid for throughput; missing duration is not zero |
| Whole-run elapsed | seconds | Same monotonic boundaries around an explicitly declared sequence of stages | Do not substitute Airflow tracking duration without labeling its different boundaries |
| Throughput | observations/s | **Named completed record count** / measured positive stage elapsed seconds | Zero records yields 0; nonpositive elapsed invalid |
| Acceptance fraction | fraction [0,1] | `valid_count / total_records` after successful parsing | Undefined (`null`) for zero denominator in experimental results |
| Rejection fraction | fraction [0,1] | `invalid_count / total_records` after successful parsing | Undefined (`null`) for zero denominator in experimental results |
| Violation occurrences | count by code | Count each triggered validation rule; one rejected record may contribute several codes | Empty map if no violations; **not** a rejection-rate denominator |
| Gold outcome fractions | fraction [0,1] | Per-outcome count / `records_read`, only for completed load | Undefined if no records read |
| Applied Gold records | records | `inserted + updated` for a completed Gold load | `unchanged` is excluded; no automatic claim of business-value improvement |
| Repeatability | dimensionless and seconds | Compare logical state and aggregate timing distributions of repeated fixed-fixture runs | Do not infer deterministic wall-clock time |
| Failure rate | failures / attempted runs | Run failure count divided by all attempted runs in that scenario | Undefined for zero attempts |

`experiments.metrics` introduces *pure definitions* for quality fractions, throughput and Gold outcome balance. It neither changes production `quality_report`'s four-decimal/empty-batch conventions nor changes ETL behavior. Report raw numerator/denominator alongside derived values; defer display rounding to the reporting layer. Do not compute a quality rate for parser-rejected batches: parser failure is a **failed attempted batch**, not a batch of `invalid_count` financial observations.

## 4. Controlled datasets and identity

- Use synthetic, deterministic provider-shaped JSON or canonical records with fixed seed (proposed default `20261001`), symbol subset, dates, and stable observation ordering. Generator and input SHA-256 should be recorded once fixture generation is implemented.
- Initial proposed tiers: **100**, **1,000**, and **10,000** parsed observations, provided fixtures can represent unique valid dates across symbols and the machine has sufficient resources. These are experimental parameters, **not measured capacities**.
- Include a clean OHLCV case, a mixed valid/invalid financial-rule case, an invalid-only financial-rule case, and a separately labeled structurally malformed/duplicate-date failure case. Never conflate the last case with ordinary `invalid_count`.
- For replay, run from identical Raw bytes, fresh temporary Raw/Silver/quarantine directories, and if Gold is exercised, a specifically approved isolated `financial_market_test` database. Record the intended initial state and restore/clean it by an explicitly reviewed test fixture procedure; **do not truncate or drop a persistent operator database**.
- A single provider response cannot contain two observations with the same date. Multiple symbols or appropriately separated fixture batches are required for larger workloads. The Silver writer organizes one partition per symbol and year and merges by symbol/date: this may affect runtime, and must be disclosed.
- No live Twelve Data call, API key, production DB, externally hosted workload, or real market dataset is required.

## 5. Protocol proposed for later issues

1. Identify the exact source revision, Python and dependency versions, OS, CPU/memory, Docker/PostgreSQL variants if used, fixture seed and SHA-256, workload tier, stage, run ID, and baseline Gold state.
2. Start with an isolated **unmeasured warm-up** for each scenario where useful. Do not mix warm-ups into aggregate results.
3. For each size/scenario, perform a proposed **five measured repetitions**. Use a monotonic timer around the named operation. Capture raw elapsed nanoseconds and success/failure, even when the attempt fails.
4. Use fresh temporary directories for independent trials. Distinguish cold/warm filesystem cache, first dependency load, concurrent workloads, and database state; do not silently compare dissimilar conditions.
5. Verify counts and invariants before accepting the measurement: `total=valid+invalid`, one quarantine path per rejected financial observation, and `Gold records_read=inserted+updated+unchanged+rejected` for completed Gold batches.
6. Preserve one row per attempt including failed attempts and reasons. Summarize median, min/max, optional IQR, and explicitly reported attempt count. Report failure rate with the attempted-run denominator.
7. Generate charts only from recorded measurements, with units, scenario names, and visible limitations. Never imply inference from fixture tiers or one-off trial results.

**Resource monitoring:** CPU/RSS metrics are optional and require an explicit cross-platform collection method in a later issue. This design makes no claim that they are currently measured.

## 6. Machine-readable result schema (planned, not yet implemented)

One JSONL record per attempt. This is an illustrative structure; the runner and artifact storage come in later M10 issues:

```json
{
  "schema_version": 1,
  "experiment_id": "raw-silver-100-clean",
  "git_sha": "<commit-sha>",
  "fixture_sha256": "<fixture-hash>",
  "seed": 20261001,
  "stage": "raw_to_silver",
  "scenario": "clean",
  "attempt": 1,
  "warmup": false,
  "status": "success",
  "elapsed_ns": null,
  "total_records": null,
  "valid_count": null,
  "invalid_count": null,
  "throughput_records_per_second": null,
  "failure_category": null
}
```

`null` explicitly means no actual measurement has been supplied. Never check in illustrative `null` values as if they were collected performance observations. Do not store raw payloads, credentials, secret-bearing environment snapshots, or provider responses in measurement artifacts. Store actual result JSONL outside Git by default; publish a reviewed, sanitized sample only after evidence review.

## 7. Threats to validity and future reporting

Local host load, disk cache, PyArrow and PostgreSQL version differences, Python GC, fixture construction overhead, symbol/year partition distribution, database indexing/initial state, and different sequencing of stages all influence comparisons. Synthetic-fixture measurements cannot establish live-provider throughput, market representativeness, internet latency, service availability, or production SLAs. Tests exercise well-defined behavior, but a passing unit suite is not benchmark evidence. Report variability, failed runs, and excluded observations explicitly.

## 8. Issue #81 definition of done

- Source-backed inventory, questions, hypotheses, denominators, dataset protocol and limitations documented.
- Pure metric contracts with unit coverage; no network, database, or file writes by metric functions.
- Ordered implementation plan created for subsequent M10 issues.
- Ruff, full tests, seven CI jobs green on the PR before merging.
