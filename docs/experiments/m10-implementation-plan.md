# M10 — Experiments & Evaluation implementation plan

**Milestone:** M10. **Design issue:** #81 `experiment: design reproducible evaluation framework and metrics`. Issue numbers for later items are assigned by GitHub, **not presumed**. Follow one issue → branch → patch ZIP → tests → PR → merge at a time.

## Proposed sequence

| Order | Proposed issue title | Depends on | Deliverable / acceptance boundary |
| --- | --- | --- | --- |
| 1 | `experiment: design reproducible evaluation framework and metrics` (#81) | M9 | This methodology, pure metric definitions, and contract tests; no benchmark claims |
| 2 | `experiment: generate deterministic synthetic market-data workloads` (**#83**) | #81 | Seeded, labeled, replayable provider-shaped input; size tiers and malformed-vs-financial-invalid cases, fixture hashes; no provider traffic |
| 3 | `experiment: implement isolated ETL benchmark runner` (**#85**) | 1–2 | Bounded, opt-in local Raw→Silver benchmark, monotonic stage timings, JSONL attempt schema, warm-ups, failed-attempt capture; temp dirs |
| 4 | `experiment: evaluate financial data quality and rejection behavior` (**#87**) | 2–3 | Measured record-level rates, code occurrence breakdown, parser failure segregation, expected-vs-observed validity with denominators |
| 5 | `experiment: evaluate Gold persistence and repeatability` (**#89**) | 2–3 | Operator-approved isolated `financial_market_test` scenarios, inserted/updated/unchanged/rejected counts, logical-state comparison and cleanup review |
| 6 | `experiment: analyze performance, variability and results` | 3–5 | Repeated-run distributions, throughput/time curves, limitations, sanitized result tables/figures; no fabricated benchmark data |
| 7 | `test(experiment): reproduce and review M10 evaluation evidence` | 1–6 | Independent reproduction instructions and cross-checks, all Python tests and seven CI gates; final limitations and milestone sign-off |

The sequence is provisional and may be narrowed after reviewing existing fixture generation, CI capacity, and available storage. No issue in this plan creates automatic production workloads.

## Common safeguards

- Keep ingestion/Gold loading authorization gates and paused Airflow defaults unchanged.
- Prefer offline Raw-to-Silver experiments in `tmp_path`-style isolated locations. Gold measurements require intentional test DB targeting, reviewed cleanup, and no writes to `financial_market`.
- Generate deterministic fixtures from seeds and record content hashes; do not fetch live provider responses or commit sensitive data.
- Do not conflate ingestion file counts with observation counts, Gold `records_loaded` with rows read, or violation occurrences with rejected records.
- Clearly distinguish fresh results, historical CI/functional-test evidence, illustrative examples, and unsupported claims.
- Each PR records Ruff, total tests, seven GitHub Actions statuses, skipped environment-dependent checks, and any experiment limitations.

## Outputs intended for M11 / M12

The final M10 results should provide research questions, justified dataset design, machine-readable anonymized measurements, runtime/quality charts, repeatability evidence, threat-to-validity notes, and repeatable commands. They support an academic/portfolio narrative but are **not** statements of live API or cloud production performance.

## Issue #83 implementation

The deterministic, offline generator and manifest contracts are documented in [synthetic workloads](synthetic-workloads.md). The 100/1,000/10,000 observation tiers are fixture definitions, not benchmark evidence. Actual observed CI and local test results must be recorded by the PR reviewer.

## Issue #85 implementation

The [isolated Raw-to-Silver benchmark runner](etl-benchmark-runner.md) consumes verified Issue #83 fixtures and emits bounded per-attempt JSONL evidence with explicit warm-up, monotonic timing, failure and isolation semantics. This is an experimental *instrument*, not a published benchmark result; later M10 issues analyze actual observations.

## Issue #87 implementation

The [financial data-quality evidence evaluator](quality-evaluation.md) compares
verified synthetic manifest expectations with actual benchmark JSONL outcomes,
including record-level counts, per-rule violation occurrences and explicitly
expected parser failures. It is an offline evidence consistency check, not a
new ETL runner or independent real-market accuracy study.

## Issue #89 implementation

The [rollback-only Gold repeatability evaluation](gold-repeatability.md) exercises insert, exact replay, newer update, stale replay, and equal-timestamp conflict against the approved isolated test database without committing experiment rows. It is not a committed durability benchmark.

## Issue #6 — Offline performance analysis

The [offline performance analyzer](performance-analysis.md) validates Issue #85
schema-v1 benchmark JSONL files, summarizes successful measured attempts,
counts failures separately, and compares compatible synthetic workload tiers.
It emits reproducible JSON and Markdown reports without rerunning ETL or
claiming unmeasured per-substage bottlenecks. The GitHub issue number is
assigned independently and should be recorded after issue creation.
