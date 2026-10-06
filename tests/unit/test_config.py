import pytest

from financial_data_platform.config import (
    ConfigurationError,
    get_twelve_data_api_key,
)


def test_get_twelve_data_api_key_returns_environment_value(monkeypatch):
    monkeypatch.setenv(
        "TWELVE_DATA_API_KEY",
        "test-api-key",
    )

    assert get_twelve_data_api_key() == "test-api-key"


def test_get_twelve_data_api_key_rejects_missing_environment_variable(
    monkeypatch,
):
    monkeypatch.delenv(
        "TWELVE_DATA_API_KEY",
        raising=False,
    )

    with pytest.raises(
        ConfigurationError,
        match="TWELVE_DATA_API_KEY",
    ):
        get_twelve_data_api_key()
