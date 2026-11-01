# M10 — Isolated Raw-to-Silver benchmark runner (#85)

This **opt-in**, offline tool measures execution of the **existing** `process_raw_market_data` pipeline against the synthetic, SHA-256-verified fixtures from #83. It does not call Twelve Data, Airflow, Gold PostgreSQL, or production services. Performance observations must be attributed to the actual machine and fixture used; this implementation adds an instrument, **not a performance conclusion**.

## Quick start (Git Bash, repository root)

Create a dataset in a **new** ignored directory (omit this command if you already have a suitable dataset):

```bash
python scripts/generate_synthetic_workloads.py \
  --output data/experiments/benchmark-clean \
  --profile small --scenario clean --seed 20261001
```

Run the bounded benchmark into a **new** `.jsonl` filename; both dataset directory and result parent must already exist:

```bash
python scripts/run_etl_benchmark.py \
  --dataset data/experiments/benchmark-clean \
  --output data/experiments/benchmark-clean-results.jsonl \
  --warmups 1 --repetitions 5
```

Do **not** commit the generated dataset or JSONL measurements without review. Results in the repository are permitted only under ignored `data/experiments/`; explicit external paths are also allowed. The benchmark refuses overwrites, and it refuses to write result files into the input fixture directory. `--repetitions` must be 1–20 and `--warmups` 0–5. Make a new output filename for another run; the same input fixture may be reused.

## Timing boundary

- Before timing: validate fixture manifest, generator parameters, per-file SHA-256 and aggregate mapping digest; copy input Raw JSON into a fresh temporary Raw directory; instantiate fresh Silver and quarantine writers.
- **Timed stage:** sequentially call `process_raw_market_data` once per symbol-file, including Raw JSON reads, parser, financial validation, Parquet writes and quarantine writes. The timer uses `time.perf_counter_ns()`.
- After timing: verify total, accepted, rejected, quarantine-path and violation-code invariants against the generator manifest; calculate experimental quality fractions and throughput; serialize results to the new JSONL output.
- All trials, including warm-ups and failures, use new temporary directories and leave no Raw/Silver/quarantine outputs behind. Input fixture files are read, never altered.
- Timing is **per entire Raw-to-Silver file sequence**, not individual parsing/validation/Parquet subtasks or end-to-end Airflow DAG duration. Fixture generation, preflight, per-trial copying, result checks and report writing are excluded. Filesystem cache and other host effects remain potential sources of variability.

## JSONL schema

Each line is a JSON object (`schema_version=1`) with `experiment_id`, `git_sha` (or `null` if unavailable), `fixture_sha256`, `seed`, `profile`, `scenario`, `symbol_count`, `expected_unique_observations`, `python_version`, `stage=raw_to_silver`, one-based `attempt`, `warmup`, `status`, `elapsed_ns`, `total_records`, `valid_count`, `invalid_count`, `violation_counts`, `acceptance_rate`, `rejection_rate`, `throughput_records_per_second`, and `failure_category`.

`status=success` means all batches parsed and the observed counts and violation occurrences matched the manifest. Throughput is **parsed observations divided by positive measured seconds**. Rates are unrounded fractions; `violation_counts` counts rule occurrences, not distinct rejected records. A `duplicate_date` fixture causes a parser failure, *not* an inferred rejection percentage.

A failed attempt carries `status=failed`, a bounded failure category (e.g. `parser_error`, `invalid_json`, `file_io_error`, `validation_error`, `outcome_mismatch`, `processing_error`), and elapsed nanoseconds when observed. **Counts, rates and throughput remain `null` on failure**, even if some temporary batches completed. Exception text and tracebacks are never included in result rows. The CLI exits nonzero if any measured attempt failed; the JSONL is still preserved for analysis. Warm-ups are labeled `warmup=true` and must be excluded from measured-run summaries, but they remain recorded as evidence.

## Safety, interpretation and limitations

- The runner accepts only synthetic Issue #83 schema-v1 manifests with supported profiles and bounded generator configuration; checks file names, inventory, SHA-256 and generator-derived expectations before attempting ETL. Hashes check file integrity, not an external signature or attestation.
- All output folders are temporary, except the explicit JSONL result; no database connections or provider calls are used by this Raw-to-Silver path. Do not enable ingestion or Gold-loading environment flags for experimental validation.
- `large` fixtures may take more time and disk space. Default to `small`; use larger tiers deliberately.
- Repeatability means fixture identity, schema and procedure are reproducible; wall-clock durations are **not** guaranteed identical.
- Report the Git SHA, Python/PyArrow versions, OS/hardware, dataset digest and run parameters when interpreting results. PyArrow version and host specifications can be recorded separately using locally reviewed commands; the JSONL currently captures Python version but does not capture host hardware or every dependency.
- The tool **does not** aggregate medians or publish charts. Later M10 issues analyze results, quality scenarios and reliability. Avoid comparing numbers from different host/load/cache conditions without qualification.
- There is no automatic registry upload, external logging, credential serialization, or production use.

## Verification

```bash
python -m pytest -q tests/unit/test_etl_benchmark.py
python -m ruff check .
python -m ruff format --check .
python scripts/run_tests.py
```

After a PR, all seven GitHub Actions jobs must pass; offline unit tests exercise the benchmark contract without executing an unbounded benchmark campaign in CI.
