# M11 v1.0 release gate — operator checklist

**Template only: all checkboxes begin unchecked.** Copy results into the final
release PR/record rather than ticking boxes in this reusable guide. Never paste
`.env`, provider responses, full Compose config or credential-bearing logs.

## 1. Review identity and boundaries

- [ ] Record exact commit SHA (`git rev-parse HEAD`), branch, review date (UTC),
      PR and seven CI job links.
- [ ] Confirm portfolio-only/local-development release wording; do not promise
      hosted deployment or production availability.
- [ ] Inspect `git status --short` and staged diff for secrets, test output,
      credential files, database dumps and developer-specific helpers.
- [ ] Confirm ingestion/Gold loading flags remain disabled by default and DAG
      remains paused (see `docs/airflow-local-setup.md`).

## 2. Safe local verification

From repository root, with Python 3.11 and approved **isolated** PostgreSQL
integration environment (`financial_market_test`):

```bash
python -m ruff check .
python -m ruff format --check .
python -m pytest -q -m "not integration"
python scripts/run_tests.py
```

The full test runner loads the private repository `.env`; never run this
against a primary/production warehouse. The developer's optional `pt` alias is
not part of the released application and must not be required to follow docs.

- [ ] Record Ruff commands, pass/fail and version.
- [ ] Record pytest passed/skipped totals and platform versions.
- [ ] Confirm database identity and migration safety before integration tests.

## 3. Docker, Airflow and dashboard

- [ ] Inspect `compose.yaml`, `compose.airflow.yaml`, `Dockerfile.airflow`,
      `Dockerfile.dashboard` in the actual working tree; these files were not
      included in the initial audit export.
- [ ] With Docker available, run `python scripts/validate_compose_health.py`;
      this validates configurations and must not print resolved secrets.
- [ ] Run `python scripts/smoke_dashboard.py` with dashboard dependencies.
- [ ] Validate the offline Airflow DAG according to
      `docs/operations/offline-smoke-verification.md`.
- [ ] Build and smoke the local dashboard image according to
      `docs/operations/release-readiness.md`; distinguish image-build network
      access from offline smoke runtime.
- [ ] Record whether each check was actually run locally or only in CI.

## 4. Portfolio documentation and reproducibility

- [ ] README explains architecture, features, prerequisites, safe quickstart,
      demo route, and limitations.
- [ ] Reviewer can locate dashboard/operations/M10 experiment docs without
      needing private credentials or unpublished datasets.
- [ ] Verify links and sanitized demonstration assets.
- [ ] Document that local timing results are machine-dependent and that the
      M10 evidence reviewer does not itself prove database rollback.

## 5. Publication gate (future issue)

- [ ] Agree on semantic version and package metadata (currently `0.1.0` in
      audit export); do not publish a `v1.0.0` tag before version alignment.
- [ ] Confirm all **seven** GitHub Actions jobs pass on the exact release commit.
- [ ] Prepare versioned release notes, known limitations and commit provenance.
- [ ] Explicitly approve the release scope and review any image build digests;
      no registry upload or production deploy is implied.
- [ ] Publish and verify the tag/GitHub Release only after sign-off.

## Deferral log

Record each deferred improvement with owner, rationale and tracking issue.
Known current limitations: tag-based container base images, ranged Python
dependencies, no verified SBOM/signing/production deployment, read-only
Streamlit dashboard and local-only demonstration requirements. These limits
should not be represented as features already delivered.
