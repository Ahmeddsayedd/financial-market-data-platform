# Final thesis evaluation — measured evidence and claim boundaries

**Status:** evidence-review draft, not final release approval. The four local JSON reports listed below were supplied for review. Results are from a controlled local Windows/Python 3.11 demonstration; they are not production benchmarks. Source ZIP did not include a final release-commit identity or final post-merge CI run URL.

## Evidence inventory

| Experiment | Local evidence path | What it establishes |
| --- | --- | --- |
| Issue #105 replay | `data/experiments/issue104-aapl-replay-01.json` | Five measured offline Raw-to-Silver repetitions (one excluded warm-up) |
| Issue #105 Gold audit | `data/experiments/issue104-aapl-gold-audit-01.json` | Five measured offline repetitions and one read-only Gold snapshot query |
| Issue #107 guarded DAG | `data/experiments/issue107-airflow-evidence.json` | Successful execution tracking for a no-data manual orchestration run |
| Issue #109 controlled DAG | `data/experiments/issue109-full-airflow-run.json` | Tracking of actual offline Raw-to-Silver processing, plus a separate Gold snapshot |

The Git revisions embedded within reports identify their **original experiment source revisions**, not the final release commit. The saved Raw JSON, its full byte content, task-instance logs, and screenshots are not embedded in these reports.

## Real-market dataset and validation

One captured Twelve Data AAPL daily response contains **100 observations**, spanning **2026-06-11 to 2026-11-02**. The two offline replay reports agree on Raw SHA-256 `c4fa032937e26b093c509dd7f5fc73d9a19fc76d1376426b86ff1bf2e58ed928`; both report **100 valid, 0 rejected** and **0 API requests**. The broader live fetch and first Gold-load evidence was separately observed during Issue #103, not independently reproduced by the four uploaded JSON files.

## Measured timings

| Measured operation | Trials | Median | Other observations |
| --- | --- | ---: | --- |
| Raw-to-Silver, offline replay | 5 after 1 warm-up | **8.749 ms** | Range 7.963–14.262 ms; mean 9.650 ms |
| Raw-to-Silver, separate replay with Gold audit enabled | 5 after 1 warm-up | **7.384 ms** | Range 7.061–8.043 ms; mean 7.511 ms |
| Read-only Gold audit SQL query | 1 observed snapshot | **8.956 ms** | Single query; no variability estimate |
| Guarded Airflow execution tracking | 1 run | **7.294 s** | Execution-tracking interval, no extracted data |
| Controlled Airflow execution tracking | 1 run | **9.154 s** | Tracking interval; 100 extracted, validated and transformed |

**Do not calculate a speedup** between the first two replay trials: these are independent local runs with uncontrolled cache/process conditions. The audited replay's 7.384 ms is **Raw-to-Silver time only**, not the total audit time. Separately observed Airflow UI duration (9.005 s) uses a different timing boundary from the 9.154 s execution-tracking interval. Never combine them into a single measurement.

## Gold warehouse and indicator coverage

The read-only audit found **100 AAPL market rows across 100 distinct observation dates** in `financial_market_test`, covering the same date range. Indicator non-null counts:

| Indicator | Rows with a value | Expected warm-up interpretation |
| --- | ---: | --- |
| Running drawdown | 100 | Valid at the first observation |
| Log return | 99 | Requires a prior close |
| SMA 20 | 81 | Requires 20 closes |
| SMA 50 | 51 | Requires 50 closes |
| 20-day rolling volatility | 80 | Based on sufficient return history |
| RSI 14 | 86 | Initial history required |
| Rolling volume z-score | 81 | 20-point volume window |

The counts are consistent with these window conventions; they **do not independently verify every numeric indicator value**. The four reports agree on indicator coverage.

## Controlled Airflow replay and idempotency

- Guarded Issue #107 run: terminal tracking success, **0 extracted/transformed/loaded** records.
- Issue #109 run `manual__2026-11-03T00:25:11.008138+00:00`: tracking success, **100 extracted, 100 validated, 100 transformed, 0 rejected, 0 newly loaded**.
- The actual Issue #109 Gold task log (reviewed separately, not included in the evidence ZIP) reported **1 Silver file, 100 records read, 100 market rows unchanged, 0 inserted/updated, 100 indicator rows unchanged**. This supports idempotent replay on an already populated database, not first-load throughput or committed-data durability under concurrent writes.
- Both JSON collectors recorded **0 API requests and 0 database writes by the collector itself**. These fields do not describe database writes performed by the earlier Airflow DAG.

## Engineering verification reported during the project

The last local Issue #109 full-suite result was **760 passed, 1 skipped** and the operator reported **7/7 GitHub Actions checks** after its PR merge. These are operator-reported outcomes, **not independently re-executed by this evidence reviewer**. Capture the exact final merge commit, required CI run URL and review date in the formal release record before publication.

## Limits and remaining acceptance work

1. The real-world demonstration is one symbol, one daily response, and 100 dates; it is insufficient for multi-symbol scalability or market-data accuracy guarantees.
2. Real-provider fetch latency and large-scale throughput are separate from offline Raw-to-Silver performance; do not conflate M10 synthetic results with this live-data replay.
3. Airflow tracking status and the current Gold snapshot are separate observations. Retain the independently captured task log and UI evidence for the actual Gold task operation.
4. The local dashboard screenshots, complete live-fetch report and M10 benchmark datasets were not included in the uploaded final evidence ZIP. Review and add appropriately sanitized, citation-ready supporting assets before presentation sign-off.
5. Final source SHA, CI links, package-version checks, security/safety review, release sign-off, Git tag and GitHub Release remain separate publication gates.

## Reproducibility: offline cross-report check

After placing the four original JSON reports in `data/experiments`, run:

```bash
python scripts/review_thesis_evidence.py \
  --replay data/experiments/issue104-aapl-replay-01.json \
  --audit data/experiments/issue104-aapl-gold-audit-01.json \
  --guarded data/experiments/issue107-airflow-evidence.json \
  --controlled data/experiments/issue109-full-airflow-run.json
```

The CLI is a **read-only consistency check**. It does not import the application, call Twelve Data, query PostgreSQL, rerun Airflow, or create experimental outputs. Keep the private local evidence JSONs outside Git unless explicitly reviewed for sharing.
