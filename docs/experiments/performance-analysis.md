# M10 — Offline ETL performance analysis (M10 item 6)

This tool **analyzes existing Issue #85 JSONL measurements**. It does not run the ETL pipeline, access PostgreSQL, call Twelve Data, produce new timing samples, or make claims about production performance. It accepts schema-v1 Raw-to-Silver benchmark rows only.

## Usage (Git Bash, repository root)

Generate two verified fixtures with the existing Issue #83 generator and benchmark each with Issue #85. Use new ignored output paths; do not overwrite prior evidence. Example (replace these filenames if they exist):

```bash
python scripts/generate_synthetic_workloads.py \
  --output data/experiments/perf-small-fixture \
  --profile small --scenario clean --seed 20261001
python scripts/generate_synthetic_workloads.py \
  --output data/experiments/perf-medium-fixture \
  --profile medium --scenario clean --seed 20261001

python scripts/run_etl_benchmark.py \
  --dataset data/experiments/perf-small-fixture \
  --output data/experiments/perf-small-results.jsonl \
  --warmups 1 --repetitions 5
python scripts/run_etl_benchmark.py \
  --dataset data/experiments/perf-medium-fixture \
  --output data/experiments/perf-medium-results.jsonl \
  --warmups 1 --repetitions 5
```

Use the analyzer (repeat `--input` for 1–20 previously generated result files):

```bash
python scripts/analyze_etl_performance.py \
  --input data/experiments/perf-small-results.jsonl \
  --input data/experiments/perf-medium-results.jsonl \
  --json-output data/experiments/performance-analysis.json \
  --markdown-output data/experiments/performance-analysis.md
```

The CLI prints the number of groups and valid cross-tier comparisons, **not claimed speedups**. Select unused output filenames for future runs. The result parent directory must exist; repository-local outputs must be under ignored `data/experiments/`. Inputs are read-only. Neither generated inputs nor reports should be committed without review. No `.env` or database credentials are needed.

## Evidence validation and grouping

- Each bounded UTF-8 JSONL input (at most 2 MB and 100 rows) must contain only the existing benchmark `schema_version=1`, the supported `raw_to_silver` stage, and one consistent fixture/runtime identity.
- Check exact metadata (profile, scenario, seed, symbol count, fixture SHA-256, Git SHA, Python version, expected observations), contiguous one-based attempts, warm-ups preceding measured trials, and successful/failed metric semantics.
- A successful attempt must include a positive `elapsed_ns`, consistent parsed record counts, rates and throughput. A failure may include an observed elapsed time but must not claim any successful counts, quality rates or throughput; it must have a failure category.
- Exclude warm-ups from measured distributions. Count failed measured attempts by category; **never** substitute zeros or extrapolate partial work as successful performance.
- Combine files for exactly matching fixture/runtime identities, rejecting identical input file digests to avoid duplicate trials. Distinct fixture identities remain separate groups.
- Reports contain input SHA-256 digests, not user-specific local file paths, and omit execution timestamps. Identical evidence yields byte-identical JSON and Markdown regardless of input ordering.

## Metric definitions

All descriptive distributions describe **successful measured attempts** only:

| Metric | Definition |
| --- | --- |
| Elapsed seconds | `elapsed_ns / 1,000,000,000` |
| Throughput, records/second | Issue #85 observation count / measured elapsed seconds |
| Seconds/record | Measured elapsed seconds / parsed observation count |
| Minimum, maximum, median, mean | Unweighted statistics across successful measured attempts |
| Population standard deviation | `ddof=0`, descriptive variation among observed attempts |
| p95 nearest rank | Sorted observation at one-based index `ceil(0.95 × n)`; with small samples, equals or approaches the maximum |
| Cross-tier record ratio | Larger tier observations / smaller tier observations |
| Median elapsed ratio | Larger tier median elapsed seconds / smaller tier median elapsed seconds |
| Median throughput ratio | Larger tier median of per-attempt throughput / smaller tier median of per-attempt throughput |

**Important:** Median throughput is the median of individually measured throughputs; it is not necessarily the throughput computed from median elapsed time. Comparisons require a matching scenario, seed, symbol count, Git revision and Python version, different supported workload size tiers, and an unambiguous single fixture per compared tier. The report retains exact fixture SHA-256 values. If there are no successful measured attempts or no comparable tiers, the analysis reports `null`/`n/a`; it does not invent a comparison.

## Limitations and interpretation

The Issue #85 timer covers sequential `process_raw_market_data` calls, including parsing, validation, Parquet output and quarantine output. It does **not** measure individual substage contributions, fixture generation, preflight, data copying, whole-DAG elapsed time, Gold persistence or network calls. Therefore the tool cannot isolate parsing-vs-Parquet bottlenecks and intentionally makes no such claim.

Host hardware, host load, filesystem cache, PyArrow and other dependency versions are not captured in the JSONL. Matching code revision and Python version are necessary but **not sufficient** for controlled scaling comparisons. Increasing workloads is a comparison of observed samples, not evidence of causality, benchmark certification, production throughput or a performance target. Warm-up timing is retained only in source evidence, not summarized. Experimental `small`, `medium` and `large` tiers have 100, 1,000 and 10,000 observations respectively. All values are machine-specific and must be collected locally; this patch does not ship fabricated measurement data.

## Verification

```bash
python -m pytest -q tests/unit/test_performance_analysis.py
python -m ruff check .
python -m ruff format --check .
python scripts/run_tests.py
```

Review the two local outputs and capture all seven CI statuses before merging.
