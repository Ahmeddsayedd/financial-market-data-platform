# M11 v1.0 release evidence — Issue #99

**Status: release candidate draft; not approved for publication.** This record
separates observed local results from release-commit checks that still require
confirmation. It must not replace the reusable
[operator checklist](m11-v1-release-checklist.md).

## Identified source and scope

- Repository: `Ahmeddsayedd/financial-market-data-platform`.
- Verified **baseline**, `main` after PR #98: `400bfd3df656ad05d52289d231ca5eea77905e8c`.
- Review date: 2026-11-02 (local verification; record UTC review date at sign-off).
- Issue #97 deployment reliability merged through PR #98; seven CI jobs were
  reported passing on that PR. CI run/job URLs: **TO RECORD**.
- Issue #99 updates metadata and docs; **final release commit SHA, PR number,
  seven CI job URLs, and approval are pending**. Do not treat the baseline's
  prior CI result as a passing result on this updated commit.
- Target version: package metadata `1.0.0`; proposed tag `v1.0.0` **not yet
  created**. Portfolio/local-only; no release or image has been published.

## Operator-reported verification (baseline)

| Check | Observed result | Limits |
| --- | --- | --- |
| Ruff lint | Passed before #99 | Rerun on final commit |
| Ruff format | Passed after two files were formatted in #97 | Rerun on final commit |
| Non-integration pytest | 627 passed, 1 skipped, 70 deselected | Baseline only |
| `python scripts/run_tests.py` | 697 passed, 1 skipped | Loads private `.env`; test isolation not fully audited per connection |
| `python scripts/validate_compose_health.py` | All four checks passed | Config validation, not startup |
| `python scripts/verify_deployment_runtime.py --stack all` | Six inspected services in expected states, incl. completed Airflow init | Snapshot of existing local containers |
| `python scripts/smoke_dashboard.py` | All four Streamlit pages passed | Safe offline handling, not real SQL availability |
| Airflow Docker build and isolated DAG import | Image built; DAG import, seven tasks, chain and defaults passed | No task execution or live ingestion |
| Dashboard `docker build --pull` and offline HTTP smoke | Image built and startup health passed | HTTP health only; no browser or production proof |
| Dashboard image ID | `sha256:4f927a67e633bcc47c74ebf2794a0b5ffbf3cbd60296a15e1d6dc3167528a771` | Local image identifier, **not** registry digest |

## Test database and safety review

The developer `.env` contains `POSTGRES_DB=financial_market`, while inspected
integration tests explicitly override or pass `financial_market_test`; CI is
configured to use `financial_market_test`. The grep-based fixture review does
**not** prove that every database connection in the local full test run went
to the isolated test database. Before any further database-writing test, verify
connection routing and isolation. Never attach secret values or live logs.

## Final release gate — not yet satisfied

- [ ] Confirm clean staged diff, safe defaults, no secrets or unpublished data.
- [ ] Confirm database isolation for the full local integration suite.
- [ ] Rerun lint/format/tests and smoke checks as appropriate on the final SHA.
- [ ] Capture all **seven** CI job links and results on the exact release commit.
- [ ] Verify README/document links and sanitized reviewer assets.
- [ ] Record final commit SHA, UTC review date, PR, reviewer, and approval.
- [ ] Review local dashboard/Airflow image IDs, upstream image versions and
      known unpinned-dependency limitations; approve scope explicitly.
- [ ] Only after sign-off: publish and verify annotated tag / GitHub Release
      in a **separate authorized publication step**.

Deferred improvements: stronger end-to-end DB connection isolation assertions,
reproducible pinned dependencies and base digests, SBOM/signing and vulnerability
scans, hosted deployment, and expanded portfolio demo artifacts. Assign owners
and tracking issues before release approval where appropriate. An image rollback
does not undo migrations or database writes.
