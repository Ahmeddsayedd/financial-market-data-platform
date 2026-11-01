# Operator-approved backup and recovery (#75)

**Procedural guidance only.** This issue adds no executable backup/restore
script, no CI restore, and no permission to overwrite existing data. Obtain
operator approval and verify the source/target DB identity and volume ownership
before any migration, restore or service outage.

## Data inventory and recovery boundaries

| Asset | Location | Scope |
| --- | --- | --- |
| Gold PostgreSQL | `compose.yaml`, `postgres_data` | `financial_market` and the separate `financial_market_test` database, depending on initialization |
| Airflow metadata PostgreSQL | `compose.airflow.yaml`, `airflow_postgres_data` | Airflow run history, scheduling and metadata; separate backup |
| Airflow authentication data | `airflow_auth_data` | Generated local admin credentials; treat as secrets |
| Raw/Silver/quarantine | `data/raw`, `data/silver`, `data/quarantine` | Files mounted from the host; outside PostgreSQL dump coverage |
| Application code/migrations | Git repository | Keep a commit/version reference matching each backup |

A logical `pg_dump` captures one selected database's SQL objects/data, not
other databases, host-mounted files, Airflow auth volumes, or actual passwords
for external services. PostgreSQL role/global backup requires an independently
reviewed procedure (`pg_dumpall --globals-only` is an example of a globals
backup tool but may expose password hashes and is **not** executed here).

## Manual backup preparation (non-destructive)

1. Confirm which instance is Gold vs Airflow metadata. Verify the database
   name using a read-only query such as `SELECT current_database();` through a
   trusted private database session. Do **not** paste connection credentials.
2. Arrange an appropriate maintenance/consistent snapshot window. Ensure the
   backup destination is outside the repository and has restricted access and
   sufficient free space; encrypt at rest and in transit as required.
3. Select a least-privileged backup operator able to read the required schema.
   PostgreSQL's `pg_dump` should run against the *intended database*, with a
   compatible client version (PostgreSQL 17 is used here).
4. Review commands locally **before executing**; use password-safe mechanisms
   such as a protected passfile rather than putting credentials in command
   arguments or shell history.

### Example operator command pattern (do not execute without approval)

The following is an illustrative template; replace placeholders privately and
verify the target. The `-Fc` format supports `pg_restore` inspection.

```text
pg_dump -h <APPROVED_HOST> -p <APPROVED_PORT> -U <BACKUP_ROLE>   -d <VERIFIED_SOURCE_DATABASE> -Fc -f <SECURE_OUTSIDE_REPOSITORY_PATH>
```

Back up Gold and Airflow metadata **separately**, and record the UTC backup
time, tool version, DB identity and repository commit. Treat dumps as sensitive.
For raw data and volumes, use a separate tested file/volume backup procedure;
do not assume a SQL dump contains these.

## Verification and restore — require explicit approval

1. Verify that the backup exists, is nonempty, is stored securely and can be
   inspected with `pg_restore --list` (without dumping its contents to shared
   logs). Record checksum and provenance privately.
2. Provision a **new isolated restore target** with a distinct name and
   credentials, preferably in a separate PostgreSQL instance. Never silently
   overwrite `financial_market`, `financial_market_test`, or the Airflow
   metadata database. Do not restore into a live running target.
3. Review ownership, extensions, schema permissions and PostgreSQL major
   version compatibility before restoration. The backup may contain sensitive
   data and privileged objects; run only under a reviewed role.
4. Restore into that empty approved target with `pg_restore`, using reviewed
   flags and a validated connection target. Deliberately omit runnable restore
   shell commands here to prevent copy/paste against an existing database.
5. Verify `current_database()`, expected tables, safe row counts, application
   migrations, roles, and read-only query behavior. For Airflow metadata,
   verify Airflow's own supported migration/version compatibility before any
   startup. Never point the production stack at a test restore by accident.
6. Rehearse the procedure and document RPO/RTO expectations separately; this
   repository does not claim scheduled backups or tested production recovery.
7. Only after evidence review and operator sign-off, decide whether to promote
   a restored copy and how to switch application credentials and endpoints.

## What not to do

Never use `docker compose down --volumes`, Docker volume prune, forced database
drops, unreviewed `pg_restore --clean`, or automatic replacement of production
roles/permissions as a normal backup or troubleshooting step. Do not commit
dumps or restored fixture data to Git.
