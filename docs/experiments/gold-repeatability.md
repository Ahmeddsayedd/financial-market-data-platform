# M10 — Gold persistence and rollback-only repeatability (#89)

This issue evaluates the **existing** `load_market_batch` behavior in one PostgreSQL transaction that is **always rolled back**. The test database receives no committed experimental facts, assets, or modified rows. No delete, truncate, drop, or migration is needed. This is not a durability-after-commit benchmark.

## Safety boundary

- **Opt in explicitly:** the CLI requires `--authorize-test-db`. The Python function requires `authorize_test_db=True` (the literal boolean, not a truthy value).
- Set `POSTGRES_DB=financial_market_test` deliberately; both configured and server-reported database identities are verified before any write. Existing connection configuration still requires `POSTGRES_PASSWORD` in the local environment; **never commit or upload `.env`**.
- A fresh randomized `M10...` asset symbol under source `m10_experiment` is checked for absence. Only that new symbol is read or changed. The transaction uses bounded PostgreSQL statement and lock timeouts.
- The runner calls `load_market_batch(cursor, ...)`, not `load_market_records`, because the latter commits its own transaction. The runner refuses autocommit connections, never calls commit, and rolls back even if an assertion or SQL statement fails. Existing `dim_date` upserts are rolled back too.
- Evidence is written **only after successful rollback** to a brand-new `.json` file; it excludes credentials, SQL exception messages, provider payloads, and the generated symbol. In the checkout, output must be under ignored `data/experiments/`.
- It does not modify the production database, invoke provider APIs, apply migrations, or perform persistent cleanup.

## Run (Git Bash, repository root)

First verify that the isolated PostgreSQL test database is running and the Gold schema has already been migrated **through your existing test setup**. Do not apply migrations or reset any database merely to run this experiment.

```bash
# Confirm test target locally. Do not print your .env or password.
python -c "import os; print('POSTGRES_DB:', os.getenv('POSTGRES_DB', '<unset>'))"

# Run only after verifying the value is financial_market_test.
python scripts/evaluate_gold_repeatability.py \
  --authorize-test-db \
  --output data/experiments/gold-repeatability-89.json
```

Output filenames must be new, with an existing parent directory. For repeat runs, choose another name; overwrites are refused. The CLI exits nonzero on any failed guard or experiment. If `POSTGRES_DB` is not explicitly `financial_market_test`, the experiment refuses to connect.

## Scenario contract

| Scenario | Records read | Inserted | Updated | Unchanged | Rejected | Logical state |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Initial | 2 | 2 | 0 | 0 | 0 | Two facts |
| Exact replay | 2 | 0 | 0 | 2 | 0 | Hash unchanged |
| Newer timestamp and changed value | 1 | 0 | 1 | 0 | 0 | Hash changes |
| Stale replay | 1 | 0 | 0 | 1 | 0 | Hash unchanged |
| Same timestamp, conflicting value | 1 | 0 | 0 | 0 | 1 | Hash unchanged |

All counts are **expected contract outcomes**, verified at runtime and not asserted as observed until the command completes successfully. The synthetic observations originate from the seeded Issue #83 generator. The fixture SHA-256, seed, scenario-level `perf_counter_ns()` elapsed time, counted outcomes, and before/after logical state SHA-256 are recorded. Duration times only `load_market_batch` and excludes connection setup, reads, rollback, and JSON reporting.

The Gold outcome balance is `records_read = inserted + updated + unchanged + rejected`. Applied records means `inserted + updated`. Financial validation rejection from Raw-to-Silver is a separate phenomenon. The same-timestamp conflicting fact is **classified** as a Gold rejection by the existing conflict rule, rather than raising an exception.

## Verification

```bash
python -m pytest -q tests/unit/test_gold_repeatability.py
python scripts/run_tests.py
python -m ruff check .
python -m ruff format --check .
```

The integration test runs against only `financial_market_test`; `scripts/run_tests.py` uses the project's isolated test environment. Do not run the integration test against a manually re-targeted live database. Confirm that seven CI jobs pass before merging.

## Interpretation and limits

A passing evaluation establishes consistent outcomes **inside one rolled-back transaction** and validates the loader's replay/conflict behavior. It does not establish long-run reliability, committed persistence durability, concurrent throughput, Airflow performance, or production SLAs. The five short stage durations are diagnostic, not a full statistically powered performance campaign. Existing unit and integration tests provide complementary evidence for committed transaction behavior.
