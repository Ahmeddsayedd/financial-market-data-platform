
# Local PostgreSQL Development Setup

## Purpose

This guide explains how to run the financial market data platform's local PostgreSQL database using Docker Compose.

PostgreSQL serves as the Gold analytical storage layer. The database schema and loading logic are implemented in separate development tasks.

This setup is intended for local development and testing, not production deployment.

## Prerequisites

- Docker Desktop or Docker Engine with Docker Compose support
- Docker engine running
- Git
- An available local TCP port (5432 by default)

On Windows, Docker Desktop uses the WSL 2 backend for Linux containers.

Verify the installation:

```bash
docker --version
docker compose version
docker info
```

## Environment Configuration

From the repository root, copy the example environment configuration if a local `.env` file does not already exist:

```bash
cp .env.example .env
```

If `.env` already exists, preserve its existing API credentials and add the PostgreSQL variables manually.

Configure:

```dotenv
POSTGRES_DB=financial_market
POSTGRES_USER=financial_app
POSTGRES_PASSWORD=
POSTGRES_PORT=5432
```

Set `POSTGRES_PASSWORD` to a nonempty, locally chosen password.

Never commit `.env` or share its contents. The repository tracks `.env.example` only.

These credentials are for local development, not production use.

## Start PostgreSQL

From the repository root:

```bash
docker compose config --quiet
docker compose up -d
docker compose ps
```

Wait until the PostgreSQL service reports `healthy`.

On first startup, Docker downloads the configured PostgreSQL image and initializes the database in a named Docker volume.

## Check Logs

```bash
docker compose logs postgres
```

To view recent logs:

```bash
docker compose logs --tail=50 postgres
```

## Verify the Database Connection

Execute a SQL query through the PostgreSQL container:

```bash
docker compose exec postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT current_database(), current_user, version();"'
```

The query should return the configured database, the configured user, and the PostgreSQL server version.

## Stop and Restart

Stop and remove the containers without deleting database data:

```bash
docker compose down
```

Start them again:

```bash
docker compose up -d
```

The PostgreSQL named volume preserves the database contents.

Stopping containers does not automatically delete persistent data.

## Persistent Storage

The Compose configuration uses a named volume:

`postgres_data`

Docker Compose manages the physical storage location.

Database files are not stored in the Git repository.

The database was tested by inserting a temporary record, removing and recreating the container, and successfully querying the original record afterward.

The temporary verification table was removed after testing.

## Destructive Reset

**WARNING: The following command deletes the local PostgreSQL database volume and its stored data.**

Run it only when intentionally resetting the local development environment:

```bash
docker compose down -v
```

After removing the volume, the next startup initializes a new, empty database using the configured environment variables.

Do not use this command when you want to preserve existing data.

## Troubleshooting

### Docker command not found

Verify that Docker Desktop is installed and that the Docker CLI is available in the terminal's PATH.

On Windows, restarting the terminal after installation may help.

### Docker engine unavailable

Start Docker Desktop and wait for its engine to become ready.

Use:

```bash
docker info
```

### PostgreSQL is not healthy

Inspect the service status and logs:

```bash
docker compose ps
docker compose logs --tail=50 postgres
```

### Port 5432 already in use

Change `POSTGRES_PORT` in the local `.env` file to an available host port, such as `5433`, and recreate the service:

```bash
docker compose up -d
```

The container continues to use PostgreSQL port 5432 internally.

### Environment variable changes do not update the existing database

The official PostgreSQL image applies initial database credentials and database creation settings when initializing an empty data directory.

Changing `POSTGRES_DB`, `POSTGRES_USER`, or `POSTGRES_PASSWORD` in `.env` does not automatically reinitialize an existing database volume.

Do not delete the volume merely to troubleshoot credentials without first considering data loss.

## Scope

This guide covers PostgreSQL infrastructure only.

The Gold warehouse schema, database migrations, Silver-to-Gold loading, financial transformations, and Airflow integration are developed separately.
