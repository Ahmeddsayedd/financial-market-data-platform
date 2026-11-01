# Secrets, configuration and least-privilege access (#75)

## Scope and safe handling

`.env.example` contains key names and empty placeholders; `.env` is ignored by
Git and must remain private. Do not paste `.env`, print `docker compose config`,
post resolved environment variables, commit dumps or share Airflow's generated
`passwords.json.generated`. `.gitignore` is a safety net, **not** a secret
scanner. Use platform-provided secret storage for production; this repository
does not integrate a managed secrets service. On a suspected exposure, revoke or
rotate the affected credential at its provider and check Git history and logs;
removing a file from a new commit alone does not erase exposure.

## Environment inventory

| Variable | Purpose | Notes |
| --- | --- | --- |
| `TWELVE_DATA_API_KEY` | Twelve Data access | Keep empty unless explicitly performing authorized ingestion; do not print it |
| `ALPHA_VANTAGE_API_KEY`, `FMP_API_KEY` | Reserved provider configuration | Present in `.env.example`; not evidence those adapters are operational |
| `POSTGRES_HOST` | Gold DB host | Optional in Python; defaults to `127.0.0.1`, scheduler sets `postgres` |
| `POSTGRES_PORT` | Gold DB port | Defaults to `5432`; host mapping may differ |
| `POSTGRES_DB` | Gold database name | `.env.example` defaults to `financial_market`; Airflow scheduler is pinned to `financial_market_test` |
| `POSTGRES_USER`, `POSTGRES_PASSWORD` | Gold application access | Shared project connection configuration, currently **not** split by role |
| `AIRFLOW_POSTGRES_DB`, `AIRFLOW_POSTGRES_USER`, `AIRFLOW_POSTGRES_PASSWORD` | Airflow metadata DB | Separate from Gold; DB service is private to its Compose network |
| `AIRFLOW_JWT_SECRET` | Airflow internal JWT signing secret | Use a distinct high-entropy value; coordinate controlled restart on rotation |
| `AIRFLOW_PORT` | Local API/UI host port | Default `8080`, bound to `127.0.0.1` |
| `ENABLE_TWELVE_DATA_INGESTION` | Environment-level ingestion authorization | Must remain `false` by default; individual DAG-run permission also required |
| `ENABLE_GOLD_LOADING` | Environment-level Gold write authorization | Must remain `false` by default; individual DAG-run permission and test DB guard also apply |

Airflow's Simple Auth Manager generates an admin password in the named
`airflow_auth_data` volume. Retrieve it privately if needed; avoid copying the
file to the repository or echoing it into shared logs. The two database systems
also use distinct persistent volumes, `postgres_data` and
`airflow_postgres_data`. Neither has automated secret rotation here.

## Credential lifecycle (manual procedure)

1. Generate different strong random values for Gold DB, Airflow metadata DB,
   Airflow JWT signing and provider tokens using an approved credential manager.
2. Store them privately and inject through local environment configuration;
   avoid plaintext command-line arguments and shell history containing secrets.
3. For rotation, plan a maintenance window and backup. Rotate at the underlying
   PostgreSQL/provider/auth system **and** update all dependent clients; merely
   editing `.env` does not modify a password already stored in PostgreSQL.
4. Recreate affected containers only when ready, check health and login/query
   behavior, and revoke old tokens once verified. Airflow JWT rotation may
   invalidate sessions; plan for controlled reauthentication.
5. Review logs and permissions after rotation; do not print secret-bearing
   `docker inspect`, resolved Compose config, or environment dumps.

## PostgreSQL least-privilege design

The current Python connection helper reads one `POSTGRES_USER` and password
from environment variables for both ETL and dashboard. Dashboard query helpers
use `SET TRANSACTION READ ONLY` and SELECT statements, but **no database-level
SELECT-only role is automatically created**. To separate roles, an operator must
provision the database and start the dashboard with separate `POSTGRES_*`
environment credentials, while leaving the ETL's credentials separate.

Recommended independent identities:

| Identity | Intended privileges |
| --- | --- |
| Dashboard reader | `CONNECT`, schema `USAGE`, `SELECT` on `dim_asset`, `dim_date`, `fact_market_metrics`, `pipeline_run`; no `INSERT`/`UPDATE`/`DELETE`, no sequence grants |
| ETL writer | Only approved schema/table DML required for validated Gold writes and execution tracking; provision separately and verify existing migrations |
| Migration operator | Schema migrations/DDL, used manually for controlled updates; not used by dashboard |
| Database administrator | Role/backup administration; never used as normal dashboard credentials |
| Airflow metadata identity | Only its separate Airflow metadata database; never share its credentials with Gold |

### Example manual dashboard-reader provisioning

**Review with the database owner before executing.** The following example is
an illustration for an operator to adapt to the correct database and schema,
not a script run by CI. It deliberately does not supply a password. In
PostgreSQL `psql` connected by an administrator to the **intended Gold database**:

```sql
-- Operator-only example: verify current_database() and role names first.
-- Create the LOGIN role using an approved interactive/managed password method.
CREATE ROLE dashboard_reader LOGIN;
GRANT CONNECT ON DATABASE financial_market TO dashboard_reader;
GRANT USAGE ON SCHEMA public TO dashboard_reader;
GRANT SELECT ON TABLE public.dim_asset, public.dim_date,
    public.fact_market_metrics, public.pipeline_run TO dashboard_reader;
```

The example targets `financial_market`; use separately approved roles/grants
when accessing `financial_market_test`. Table grants do not imply access to
future tables. Do not grant `CREATE`, `TEMP`, `INSERT`, `UPDATE`, `DELETE`,
`TRUNCATE`, sequence privileges, ownership or superuser. Review inherited
role membership, `PUBLIC` privileges, and default privileges; merely granting
SELECT does not revoke privileges inherited elsewhere. As a defense in depth,
an operator may also configure the role's default transactions as read-only,
but this does not replace least-privilege grants.

### Verify before deploying a dashboard reader

In the **target database**, as the prospective reader (not admin), confirm a
normal SELECT works and permissions are absent for writes. Prefer checking
permissions without executing an actual write:

```sql
SELECT current_user, current_database();
SELECT has_table_privilege(current_user, 'public.pipeline_run', 'SELECT');
SELECT has_table_privilege(current_user, 'public.pipeline_run', 'INSERT');
SELECT has_table_privilege(current_user, 'public.pipeline_run', 'UPDATE');
SELECT has_table_privilege(current_user, 'public.pipeline_run', 'DELETE');
```

Repeat for all dashboard tables. A SELECT role is effective only if its
inherited/public privileges are also restricted. Use a separate service
process or environment when launching Streamlit; the app has no dedicated
`DASHBOARD_POSTGRES_*` override and reads the standard `POSTGRES_*` keys.
