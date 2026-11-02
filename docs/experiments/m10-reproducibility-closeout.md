# M10 — Reproducibility guide, evidence inventory and closeout

**Scope:** M10 Experiments & Evaluation (#81, #83, #85, #87, #89, #91, final closeout issue). This is an operational review protocol, **not** a claim that historical measurements can be reproduced bit-for-bit or that production performance has been measured.

## Inventory and dependency chain

| Issue | Instrument / evidence | Input | Output | Meaning and boundary |
| --- | --- | --- | --- | --- |
| #81 methodology | [`m10-experimental-design.md`](m10-experimental-design.md) and `experiments/metrics.py` | metric contracts | definitions/tests | denominators, rates, timing definitions; **no measured performance** |
| #83 fixtures | `scripts/generate_synthetic_workloads.py` | seed, profile, scenario | `manifest.json` + `raw/SYN*.json` | deterministic synthetic provider-shaped input; manifest hashes bind its files |
| #85 benchmark | `scripts/run_etl_benchmark.py` | verified fixture directory | JSONL schema v1 | timed **Raw-to-Silver only**, warm-ups, per-attempt outcomes |
| #87 quality | `scripts/evaluate_market_data_quality.py` | verified fixture + matching benchmark JSONL | quality report JSON | expected-vs-observed synthetic outcome consistency, not real-market accuracy |
| #89 Gold | `scripts/evaluate_gold_repeatability.py` | authorization, isolated PostgreSQL test DB, synthetic seed | rollback-only JSON | Gold replay/conflict behavior inside **rolled-back transaction**, not durability of commits |
| #91 analysis | `scripts/analyze_etl_performance.py` | one or more schema-v1 benchmark JSONL files | JSON + Markdown | distributions and eligible tier scaling, **not** unmeasured substage bottlenecks |
| Closeout | `scripts/review_m10_evidence.py` | generated files above | console PASS / nonzero error | read-only provenance and selected cross-report consistency checks; not a replacement for the producer's validators |

For detailed contracts, see [synthetic workloads](synthetic-workloads.md), [benchmark runner](etl-benchmark-runner.md), [quality evaluation](quality-evaluation.md), [Gold repeatability](gold-repeatability.md) and [performance analysis](performance-analysis.md).

## Prerequisites and safe execution

From the **repository root**, use Python 3.11 with the development dependencies installed. Use `python` below. Local Windows Git Bash users who configured a working `pt` alias may substitute `pt` for `python`; `pt` automatically loads their own `.env` and selects `financial_market_test`. **Never commit, print, upload, or paste `.env` or `POSTGRES_PASSWORD`.** Offline Raw-to-Silver commands **do not require** database credentials or an API key.

Use **new filenames/directories** for every reproduction; these commands deliberately refuse overwrites. All example outputs are inside ignored `data/experiments/`; ensure its parent directory exists:

```bash
mkdir -p data/experiments
```

Run the following once per fresh local evidence namespace (the `m10-closeout-*` names below are examples; change them if present).

### A — Generate two deterministic fixtures (#83)

```bash
python scripts/generate_synthetic_workloads.py \
  --output data/experiments/m10-closeout-small \
  --profile small --scenario clean --seed 20261001

python scripts/generate_synthetic_workloads.py \
  --output data/experiments/m10-closeout-medium \
  --profile medium --scenario clean --seed 20261001
```

Expected **structural** results: small = 100 observations, medium = 1,000, each across four symbols by default. The manifest, raw-file checksums and aggregate digest are deterministic for identical generator version, parameters and input code. These counts are not performance results. For financial-invalid and parser-error reproducibility, see the separate `mixed`, `invalid_only` and `duplicate_date` scenarios in the fixture/quality documentation.

### B — Record bounded Raw-to-Silver benchmark attempts (#85)

```bash
python scripts/run_etl_benchmark.py \
  --dataset data/experiments/m10-closeout-small \
  --output data/experiments/m10-closeout-small.jsonl \
  --warmups 1 --repetitions 5

python scripts/run_etl_benchmark.py \
  --dataset data/experiments/m10-closeout-medium \
  --output data/experiments/m10-closeout-medium.jsonl \
  --warmups 1 --repetitions 5
```

Each benchmark should record **one warm-up plus five measured attempts**. Confirm measured success/failure counts from the CLI; do not presume success if it exits nonzero. Each attempt records fixture SHA-256, code revision (if resolvable), Python version, status and its own timing. `elapsed_ns` uses `perf_counter_ns()` around `process_raw_market_data`; generation, preflight, copying, persistence, and Gold are outside the timed boundary. Timing values are machine-dependent and are **not** expected to match across runs.

### C — Evaluate fixture-vs-observed quality (#87)

```bash
python scripts/evaluate_market_data_quality.py \
  --dataset data/experiments/m10-closeout-small \
  --results data/experiments/m10-closeout-small.jsonl \
  --output data/experiments/m10-closeout-small-quality.json

python scripts/evaluate_market_data_quality.py \
  --dataset data/experiments/m10-closeout-medium \
  --results data/experiments/m10-closeout-medium.jsonl \
  --output data/experiments/m10-closeout-medium-quality.json
```

For clean fixtures with successful measured attempts, verify `summary.all_matched` and matching measured counts in the JSON. If attempts fail or differ from generator expectations, preserve the evidence and report the discrepancy instead of changing expected results. Parser failures are not financial rejections; violation **occurrences** are not necessarily distinct rejected observations.

### D — Analyze performance using existing timings (#91)

```bash
python scripts/analyze_etl_performance.py \
  --input data/experiments/m10-closeout-small.jsonl \
  --input data/experiments/m10-closeout-medium.jsonl \
  --json-output data/experiments/m10-closeout-analysis.json \
  --markdown-output data/experiments/m10-closeout-analysis.md
```

Review eligible comparisons, median **of per-attempt** throughput, elapsed-time distributions and failure-category counts. Valid tier comparisons require matching scenario, seed, symbol count, source revision and Python version plus unique fixture identities. Hardware, disk/cache effects and dependency details are not fully captured in JSONL. Therefore scaling comparisons remain descriptive, not causal or production SLAs.

### E — Optional, explicitly authorized Gold test-DB exercise (#89)

**Do not run this automatically as part of the offline workflow.** Verify the PostgreSQL *test* DB has the required schema through the existing isolated integration-test setup; do not reset or migrate an arbitrary database. `POSTGRES_DB` must explicitly equal `financial_market_test` and a password must be configured locally. The evaluator additionally verifies the **connected** database and refuses autocommit, and writes evidence only after transaction rollback.

```bash
# Only after reviewing the isolated test DB and local credentials:
python scripts/evaluate_gold_repeatability.py \
  --authorize-test-db \
  --output data/experiments/m10-closeout-gold.json
```

Five contract scenarios are initial insertion, exact replay, newer update, stale replay and equal-timestamp conflict. A passing CLI reports **5** matched scenarios and rollback, but does not prove committed durability, concurrent behavior or long-running reliability. Use your working local `pt` command if it is how you safely load the test database configuration.

### F — Read-only cross-report provenance review

```bash
python scripts/review_m10_evidence.py \
  --pair data/experiments/m10-closeout-small data/experiments/m10-closeout-small.jsonl \
  --pair data/experiments/m10-closeout-medium data/experiments/m10-closeout-medium.jsonl \
  --quality data/experiments/m10-closeout-small-quality.json \
  --quality data/experiments/m10-closeout-medium-quality.json \
  --performance data/experiments/m10-closeout-analysis.json
```

To also inspect an already generated Gold report (without touching PostgreSQL), append:

```bash
  --gold data/experiments/m10-closeout-gold.json
```

**Note:** append the `--gold` flag to the **same** command above; do not run this option alone. The reviewer reads files, never modifies them, and emits only counts and booleans on success. It checks SHA-256 file/inventory integrity, fixture/benchmark identity, attempt order, selected quality summary consistency, performance input digests and Gold report scenario/rollback **claims**. It does **not** recalculate all metrics independently, regenerate fixtures, re-run pipelines, connect to PostgreSQL, authenticate provenance, or prove that a database transaction rolled back. Use producer-specific validation and tests as the primary behavioral evidence.

## Evidence record and reviewer checklist

Record this information in the PR review or local review notes; do not invent or commit measured values that were not observed:

- [ ] Git commit SHA and clean code revision identified; local uncommitted modifications disclosed.
- [ ] Python version and major dependency versions recorded where available; hardware/OS/load/cache conditions described separately.
- [ ] #83 seeds, profiles, scenarios, symbol count, raw-file hashes and manifest SHA-256 checked.
- [ ] #85 benchmark warm-up/measured counts and failure categories checked; `raw_to_silver` timing boundary stated.
- [ ] #87 expected vs observed measured attempts checked; financial rejections distinguished from parser failures.
- [ ] #89 (if executed) explicit test DB authorization, server-side identity, rollback and five scenario outcomes verified; no production DB accessed.
- [ ] #91 report input SHA-256 digests and eligibility of tier comparisons confirmed; no invented bottleneck claims.
- [ ] Read-only cross-report CLI returns `PASS`; any omitted optional evidence is explicitly marked **not reviewed**.
- [ ] `python -m ruff check .` and `python -m ruff format --check .` pass.
- [ ] `python scripts/run_tests.py` passes; note total passed and skipped counts and skip reasons.
- [ ] Seven GitHub Actions jobs pass for the PR; code reviewed and merged to `main`.

## Closeout limitations and deferred work

1. The deterministic artifacts are fixture contents and generator metadata, **not** elapsed nanoseconds, host-level throughput, or full pipeline execution timings.
2. Fixture integrity hashes identify bytes but do **not** provide an independently signed origin.
3. Benchmarks do not time individual parsing/validation/Parquet subtasks, provider calls, orchestration, Gold persistence, or production cloud services.
4. Synthetic observations do not establish real-market representativeness. Quality results validate consistency with synthetic expected outcomes, not financial accuracy on live market data.
5. Gold evidence validates a rollback-only five-case transaction. It cannot establish committed durability, concurrent conflicts, or production SLAs; it may require an intentionally configured local PostgreSQL test service.
6. Timing comparisons lack complete machine/environment metadata and therefore do not control for hardware, system load, cache or dependency variance.
7. Closeout reviewer is a supplementary read-only cross-check; existing experiment validation, tests and manual review remain authoritative for their individual claims.

**Milestone decision:** Close M10 only after the full local suite and seven CI checks pass, the six earlier deliverables are linked, optional Gold verification limitations are disclosed, and the final PR is reviewed and merged. This document supplies the procedure; it is not a claim that those external approvals have already occurred.
