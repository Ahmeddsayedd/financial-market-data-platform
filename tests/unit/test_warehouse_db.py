import pytest
import psycopg

from financial_data_platform.warehouse.db import (
    get_database_config, 
    connect_to_database,
)
from unittest.mock import patch


def test_database_config_rejects_missing_password(monkeypatch):
    """Database connections require an explicitly configured password."""

    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)

    with pytest.raises(ValueError, match="POSTGRES_PASSWORD"):
        get_database_config()


def test_database_config_uses_environment_settings(monkeypatch):
    """Read PostgreSQL connection settings from environment variables."""

    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("POSTGRES_PORT", "5433")
    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")
    monkeypatch.setenv("POSTGRES_USER", "test_app")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test_password")

    result = get_database_config()

    assert result == {
        "host": "localhost",
        "port": 5433,
        "dbname": "financial_market_test",
        "user": "test_app",
        "password": "test_password",
    }


def test_connect_to_database_uses_configured_settings(monkeypatch):
    """Pass configured connection settings to psycopg."""

    monkeypatch.setenv("POSTGRES_HOST", "127.0.0.1")
    monkeypatch.setenv("POSTGRES_PORT", "5432")
    monkeypatch.setenv("POSTGRES_DB", "financial_market_test")
    monkeypatch.setenv("POSTGRES_USER", "financial_app")
    monkeypatch.setenv("POSTGRES_PASSWORD", "dummy_test_password")

    with patch("financial_data_platform.warehouse.db.psycopg.connect") as mock_connect:
        connection = connect_to_database()

    mock_connect.assert_called_once_with(
        host="127.0.0.1",
        port=5432,
        dbname="financial_market_test",
        user="financial_app",
        password="dummy_test_password",
    )

    assert connection is mock_connect.return_value


def test_connect_to_database_propagates_connection_failure(monkeypatch):
    """Do not hide PostgreSQL connection errors."""

    monkeypatch.setenv("POSTGRES_PASSWORD", "dummy_test_password")

    with patch(
        "financial_data_platform.warehouse.db.psycopg.connect",
        side_effect=psycopg.OperationalError("Connection refused"),
    ):
        with pytest.raises(psycopg.OperationalError, match="Connection refused"):
            connect_to_database()