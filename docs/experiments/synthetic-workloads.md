# M10 — Deterministic synthetic market-data workloads (#83)

This generator produces **synthetic**, Twelve Data-shaped daily OHLCV JSON. It neither fetches provider data nor connects to PostgreSQL. It does **not** conduct performance benchmarks or establish real market representativeness.

## Generate into a new directory

From the repository root in Git Bash, with the project installed (`python -m pip install -e ".[dev]"`):

```bash
python scripts/generate_synthetic_workloads.py --output data/experiments/small-clean --profile small --scenario clean
python scripts/generate_synthetic_workloads.py --output data/experiments/small-mixed --profile small --scenario mixed --invalid-count 10 --seed 20261001
python scripts/generate_synthetic_workloads.py --output data/experiments/small-invalid --profile small --scenario invalid_only
python scripts/generate_synthetic_workloads.py --output data/experiments/small-duplicate --profile small --scenario duplicate_date
```

**Output directory must not already exist.** For tracked-repository safety, outputs inside the checkout are limited to the ignored `data/experiments/` tree. External explicitly selected directories are supported. No `.env`, provider API key, or database is needed. Generated data is an artifact; do not commit it. The `.gitignore` entry covers `data/experiments/`.

| Profile | Unique observations across payloads | Default symbols |
| --- | ---: | ---: |
| `small` | 100 | 4 |
| `medium` | 1,000 | 4 |
| `large` | 10,000 | 4 |

Override symbol count using `--symbols N`; the generator balances observation dates across symbols, and every **individual symbol response** has unique dates. These are workload sizes, **not measured performance capacities**. All generated dates are deterministic, counting backward from 2026-10-01, including weekends: this is synthetic test data, not an exchange-calendar simulation.

## Scenarios and semantics

- `clean`: every parsed observation passes the financial validation contract.
- `mixed --invalid-count N`: exactly N unique records are altered deterministically to fail one validation rule each. Requires `0 < N < total`.
- `invalid_only`: every unique observation is invalid by a financial rule, remains structurally parseable, and can be quarantined.
- `duplicate_date`: the first response intentionally duplicates its first observation date, causing **one parser-failed batch**. This is not a financial rejection and must not be used in a record rejection-rate denominator. Its payload has one extra duplicate row beyond the stated unique-observation count.

Financial invalid rules cycle over negative volume, nonpositive close, nonfinite close, high-below-low, open-outside-range, and close-outside-range. Labels are checked against the actual parser and validator in tests. Parse errors and invalid financial observations are separate experimental outcomes.

## Provenance and file layout

The generator creates `raw/SYN0001.json`, etc., plus `manifest.json`. JSON uses UTF-8, sorted keys, compact formatting and newline termination. For identical inputs, file contents and the manifest are byte-for-byte equal, independent of host paths and wall-clock time.

The manifest records schema version, generator version, seed, profile, scenario, symbol count, expected unique/valid/rejected records (or `null` if parsing fails), expected violation-code occurrences, parser-failed batch count, per-file SHA-256 checksums, an aggregate SHA-256 of the sorted filename-to-checksum mapping, and a fixed timezone-aware extraction timestamp. The aggregate hash covers file names and their hashes, not the manifest itself; check individual file checksums before processing.

The data is provider-*shaped* for `parse_time_series`. Files are intentionally written under the experiment directory rather than masquerading as production RawResponseWriter paths. Later M10 benchmarking should pass the actual generated file paths to `process_raw_market_data` in isolated temporary Raw/Silver/quarantine locations and use the documented fixed UTC extraction timestamp.

## Reproducibility and limitations

Use fixed generator version, seed, profile, scenario, symbol count and invalid count; record Git SHA, interpreter/dependency versions and generated hashes for every experiment. Large workloads can consume disk and memory; use bounded local runs. The generator intentionally does not perform a benchmark, mutate the Gold database, or reproduce live API latency, market microstructure or trading calendars. See [experimental design](m10-experimental-design.md) for statistical definitions and follow-on issues.

Verification:

```bash
python -m pytest -q tests/unit/test_synthetic_workloads.py
python -m ruff check .
python -m ruff format --check .
python scripts/run_tests.py
```
