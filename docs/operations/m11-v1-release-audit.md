# M11 — Portfolio Release v1.0: readiness audit (Issue #95 candidate)

**Status: evidence-based draft; NOT a release approval.** This is a static review of
178 files supplied in the M11 source export, not a live deployment, Docker
build, CI run, security scan, or GitHub Release verification. GitHub issue
number must be replaced if the assigned issue is not #95. Findings are based
on the exported content and should be rechecked against the tracked repository.

## Release definition and constraints

A portfolio v1.0 should let an independent reviewer understand the architecture,
install the development dependencies, run safe offline checks, see the dashboard,
and follow a transparent demonstration procedure. This is a **local development
portfolio release**, not a hosted or production-ready financial service.
Live ingestion and Gold loading remain disabled by default; database-writing
checks require an isolated test target. See
[the established M9 release boundary](release-readiness.md).

## Confirmed inventory (from export)

| Area | Evidence | Assessment |
| --- | --- | --- |
| Python package | `pyproject.toml`: Python >=3.11; `0.1.0` version; optional `dashboard` and `dev` extras | Development packaging present; v1.0 version not yet prepared |
| Entry-point docs | `README.md`, `docs/operations/README.md`, `docs/dashboard-local-setup.md` | Operational navigation exists; portfolio story is minimal |
| Default safety | `.env.example`: both `ENABLE_*` flags `false`; `.gitignore`; default-deny `.dockerignore` | Sensible defaults present; verify runtime config at release |
| CI | `.github/workflows/ci.yml` | Seven jobs: lint, unit-tests, integration-tests, compose-validation, release-dashboard-image, airflow-smoke, dashboard-smoke |
| Data and experiments | `docs/experiments/m10-reproducibility-closeout.md` and experiment scripts | Documented offline evidence workflow; measured times are host-dependent |
| Operational procedures | `docs/operations/operations-runbook.md`, `release-readiness.md`, `backup-and-recovery.md` | Detailed local procedures; no production deployment guarantee |
| Application | `src/financial_data_platform/dashboard/app.py` | Streamlit read-only dashboard; independent live walkthrough not performed |

## Prioritized findings

**P0 = safety/credential blocker; P1 = v1.0 release gate; P2 = portfolio polish.**
An audit finding is not evidence of a runtime failure.

| ID | Priority | Observation and concrete evidence | Resolution / sign-off |
| --- | --- | --- | --- |
| M11-01 | P1 | `pyproject.toml` declares `version = "0.1.0"`. No v1.0 version or tag was established by this export. | Align package/version strategy, verify tests/build and release tag in final issue; do not change version during audit. |
| M11-02 | P1 | `README.md` accurately calls this a local development platform and links primarily to operations. It lacks a portfolio-first feature/demo tour and concise architecture/release narrative. | Add project highlights, component diagram, demo paths and limitations in the portfolio-docs issue. |
| M11-03 | P1 | Existing `docs/operations/release-readiness.md` documents locally built images and manual promotion, not a published v1.0 artifact or release notes. | Prepare versioned release notes, provenance/checklist, and explicit non-production scope before tagging. |
| M11-04 | P1 | The export omitted `compose.yaml`, `compose.airflow.yaml`, `Dockerfile.airflow`, and `Dockerfile.dashboard` because the exporter allowed only selected root filenames. CI and documentation reference them, but their **contents could not be inspected here**. | Verify these four tracked files directly in the next deployment review; run `python scripts/validate_compose_health.py` with Docker and inspect Dockerfiles for secret-safe COPY/build rules. Do not infer they are missing from Git. |
| M11-05 | P1 | The workflow has seven jobs, but CI passage and live GitHub branch protection/release settings were not checked by this static export. | Capture actual run URLs and verify required checks before v1.0 approval. |
| M11-06 | P1 | `.env.example` defaults to `POSTGRES_DB=financial_market`; standalone integration tests require isolated `financial_market_test`. Existing `scripts/run_tests.py` reads `.env` explicitly; operators must select a safe test target. | Document OS-independent commands and assert test DB identity in release verification; never publish `.env` or developer-specific launchers. |
| M11-07 | P2 | Dashboard setup and smoke checks are documented; portfolio screenshots and a reviewer-friendly walkthrough are not established in this export. | Add sanitised screenshots or scripted, offline demo instructions; disclose empty-data and 5,000-row history limits. |
| M11-08 | P2 | M9 release guidance states base image tags and dependency ranges are not fully pinned; no SBOM, image signing, vulnerability scan or production deploy is claimed. | Disclose these limitations; consider pinning/SBOM only as a scoped later task. |

**Security gate:** No P0 credential exposure is established by the supplied
source, but this review does not include secret scanning. Explicitly inspect
the staged diff and release assets for secrets. Keep Airflow ingestion/loading
disabled and the DAG paused. Do not run destructive Compose commands or live API
calls for audit evidence.

## Proposed M11 issue order

1. **Release readiness audit (this issue):** merge this report, the
   [gate checklist](m11-v1-release-checklist.md), and its static tests.
2. **Deployment and startup reliability:** review actual Compose/Dockerfiles,
   test startup/smoke paths, and document safe local demo prerequisites.
3. **Portfolio README and architecture:** prepare quickstart, features, diagram,
   demonstration instructions and limitations.
4. **Release verification:** collect commit-pinned local and CI evidence;
   verify security, reproducibility, and version/packaging strategy.
5. **v1.0 publication and closeout:** approved tag, GitHub Release notes,
   provenance, and milestone sign-off, only after preceding gates.

These are proposed follow-up issues, not claims that GitHub issues already exist.

## Evidence collection before final v1.0 sign-off

Use the [release checklist](m11-v1-release-checklist.md) to record exact results,
SHA, reviewer and CI links. `PASS` is reserved for actions actually executed.
A document-only review of the source export cannot establish Docker, database,
API availability, browser rendering, security scanning or deployment readiness.
