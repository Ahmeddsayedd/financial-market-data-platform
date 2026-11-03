# Operations index — local development (M9 / #75)

This index documents operator procedures, **not** an automated deployment or
production disaster-recovery guarantee. Commands are intended for the local
repository root. Never share `.env`, decrypted Compose config, database dumps,
admin password files or raw log content containing secrets.

| Goal | Reference |
| --- | --- |
| Configure secrets and understand roles | [Secrets and least privilege](secrets-and-least-privilege.md) |
| Safely start/stop services and triage incidents | [Operations runbook](operations-runbook.md) |
| Safely back up and restore in an isolated environment | [Backup and recovery](backup-and-recovery.md) |
| Airflow-specific local setup | [Airflow local setup](../airflow-local-setup.md) |
| Compose and service health | [Airflow and Compose health](airflow-compose-health.md) |
| M11 Docker startup verification (#97) | [Deployment reliability](m11-deployment-reliability.md) |
| Offline CI smoke checks | [Offline smoke verification](offline-smoke-verification.md) |
| Correlated JSON diagnostics | [Structured logging](structured-pipeline-logging.md) |
| Read-only pipeline health states | [Pipeline health assessment](pipeline-health-assessment.md) |
| M9 scope and outstanding issues | [Implementation plan](m9-implementation-plan.md) |
| Release artifact verification and manual promotion | [Release readiness](release-readiness.md) |
| M11 v1.0 evidence-based readiness audit | [M11 release audit](m11-v1-release-audit.md) |
| M11 v1.0 verification and publication gates | [M11 release checklist](m11-v1-release-checklist.md) |
| Issue #99 release candidate verification record | [M11 v1 release evidence](m11-v1-release-evidence.md) |
| Proposed v1.0.0 notes and known limitations | [v1.0.0 draft release notes](v1.0.0-release-notes.md) |
| M9 final gate verification and sign-off evidence | [Final M9 verification](m9-final-verification.md) |

## Boundaries

- Gold PostgreSQL (`compose.yaml`) and Airflow metadata PostgreSQL
  (`compose.airflow.yaml`) are separate services and persistent volumes.
- `financial_market_test` is the permitted development write target for Airflow
  execution tracking and gated Gold loading. It is not the Airflow metadata DB.
- The dashboard's Python queries run `SET TRANSACTION READ ONLY`; dedicated
  SELECT-only database credentials are an additional recommended defense, **not**
  provisioned by this repository.
- These documents neither execute restore/rotation commands nor enable live
  ingestion, loading, or DAG scheduling.

- [Issue #101 analytics verification and traceability](issue-101-analytics-verification.md)

- [Issue #103: controlled Twelve Data live verification](issue-103-twelve-data-live-verification.md)

- [Issue #104: reproducible real-data replay and read-only Gold evidence](issue-104-end-to-end-evidence.md)

- [Read-only Airflow and populated dashboard demonstration evidence](airflow-end-to-end-demonstration.md)

- [Controlled real-data Airflow execution](controlled-airflow-real-data-execution.md) — opt-in captured-Raw replay, isolated Gold and indicator writes, restoration
