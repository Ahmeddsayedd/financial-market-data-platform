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
| Offline CI smoke checks | [Offline smoke verification](offline-smoke-verification.md) |
| Correlated JSON diagnostics | [Structured logging](structured-pipeline-logging.md) |
| Read-only pipeline health states | [Pipeline health assessment](pipeline-health-assessment.md) |
| M9 scope and outstanding issues | [Implementation plan](m9-implementation-plan.md) |
| Release artifact verification and manual promotion | [Release readiness](release-readiness.md) |

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
