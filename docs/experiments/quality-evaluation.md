# M10 — Financial data-quality evaluation (#87)

Issue #87 adds a **read-only evidence evaluator** for the deterministic workload
manifests from #83 and the per-attempt Raw-to-Silver JSONL evidence from #85.
It does not run the ETL pipeline, change validation rules, fetch live market data,
or write to PostgreSQL. It compares **observed** attempts against the manifest's
**expected** outcomes, without manufacturing any results.

## Run locally (Git Bash, repository root)

Use your existing `data/experiments/small-mixed` synthetic fixture if present,
or generate a new dataset in a directory that does not already exist:

```bash
python scripts/generate_synthetic_workloads.py \
  --output data/experiments/quality-87-mixed \
  --profile small --scenario mixed --invalid-count 10 --seed 20261001
python scripts/run_etl_benchmark.py \
  --dataset data/experiments/quality-87-mixed \
  --output data/experiments/quality-87-mixed-benchmark.jsonl \
  --warmups 1 --repetitions 2
python scripts/evaluate_market_data_quality.py \
  --dataset data/experiments/quality-87-mixed \
  --results data/experiments/quality-87-mixed-benchmark.jsonl \
  --output data/experiments/quality-87-mixed-report.json
```

All output names above must be unused before running; **no overwrites**.
Results and generated data are ignored by Git under `data/experiments/`.
External explicit output directories are supported, but report parents must
already exist. Do not commit local measurement artifacts without review.

For an intentional parser failure, generate `--scenario duplicate_date` and
run the same benchmark and evaluation sequence with **new file names**. The
benchmark CLI exits with nonzero status because its attempts fail parsing; its
JSONL evidence remains available and is evaluated as an *expected parser
failure* by this tool. No parser failure is counted as a financial rejection.

## Evidence contract

The evaluator first verifies the synthetic manifest against the generator,
including its file inventory, per-file SHA-256 and aggregate dataset checksum.
It then reads the benchmark schema-v1 JSONL, rejecting malformed, oversized,
incompatible or mixed-fixture evidence. Attempt IDs are sequential, warm-ups
precede measurements, and recorded Git/Python versions agree across attempts.
The bounded input accepts at most five warm-ups and twenty measurements.

A successful attempt must have positive elapsed nanoseconds; nonnegative
`total_records`, `valid_count` and `invalid_count`; the identity
`total_records = valid_count + invalid_count`; valid finite quality fractions
and throughput consistent with elapsed nanoseconds and parsed-record count;
and positive per-code violation occurrences. An attempt with `status=failed`
must have a recognized bounded failure category and **null** success metrics.
Only documented fields are accepted, preventing arbitrary extra payload text
from being carried into quality reports.

For `clean`, `mixed`, and `invalid_only` fixtures, comparison checks each
measured attempt's status, parsed counts and violation occurrences against
manifest expectations. Counts are **unique parsed observations**, not Raw
files. Financial rejection rate is `invalid_count / total_records` only for a
successfully parsed batch. One record may have more than one violation code,
so summed `violation_counts` is **not** the number of rejected records.

For `duplicate_date`, the expected outcome is `status=failed` with
`failure_category=parser_error`. Counts, acceptance/rejection fractions and
throughput must remain `null` as required by the benchmark schema. This is
**one expected parser-failed batch per attempt**, not a 100% financial rejection
rate. An observed parser failure is a measured execution failure even when
it correctly matches the scenario; its failure rate therefore remains 1.0.

## Report interpretation

The output `schema_version=1` JSON contains fixture SHA-256, seed, profile,
scenario, sanitized Git revision/Python version, `expected_per_attempt`,
`attempts`, and `summary`. Each attempt records its **observed** outcomes,
warm-up label, bounded failure category, `matches_expected` and discrepancy
codes. Warm-ups remain visible but do **not** contribute to measured totals.
`summary.all_matched` means expected-versus-observed agreement, **not**
perfect real-market data quality, live-provider availability or an SLA.

The summary reports `measured_attempts`, matching/mismatching attempts,
successes, failures, parser failures and `measured_failure_rate` with the
attempted-run denominator. A correctly expected parser-failure scenario can
have `all_matched=true` and `measured_failure_rate=1.0` simultaneously.

Any outcome mismatch is preserved in the output and gives the CLI a nonzero
exit code. Invalid or tampered evidence is rejected during preflight without
creating a report. No exception message, stack trace, dataset path or raw
provider payload is written to the report. The report does not include
performance medians or claim deterministic runtimes; those belong in a later
M10 analysis issue.

## Scope and limitations

This instrument assesses **deterministic synthetic expectations**. It cannot
establish real-world anomaly prevalence, financial accuracy beyond the
programmed rules, precision/recall against an independently labeled dataset,
or production throughput. Warm-up and measurement times were collected by the
#85 runner on the operator's machine; this evaluator does **not** produce fresh
execution timings. A matching manifest is an internal consistency check,
not independently verified ground truth.

## Validation

```bash
python -m pytest -q tests/unit/test_quality_evaluation.py
python -m ruff check .
python -m ruff format --check .
python scripts/run_tests.py
```

Require all seven GitHub Actions jobs to pass before merging Issue #87.
