"""PostgreSQL connection configuration for the Gold warehouse."""

import os
import psycopg


def get_database_config() -> dict[str, str | int]:
    """Read PostgreSQL connection settings from environment variables."""

    password = os.getenv("POSTGRES_PASSWORD")

    if not password:
        raise ValueError(
            "POSTGRES_PASSWORD must be configured"
        )

    return {
        "host": os.getenv("POSTGRES_HOST", "127.0.0.1"),
        "port": int(os.getenv("POSTGRES_PORT", "5432")),
        "dbname": os.getenv("POSTGRES_DB", "financial_market"),
        "user": os.getenv("POSTGRES_USER", "financial_app"),
        "password": password,
    }


def connect_to_database() -> psycopg.Connection:
    """Open a PostgreSQL connection using environment configuration."""

    config = get_database_config()

    return psycopg.connect(**config)