import os


class ConfigurationError(RuntimeError):
    """Raised when required application configuration is missing."""


def get_twelve_data_api_key() -> str:
    """Return the configured Twelve Data API key."""

    api_key = os.getenv("TWELVE_DATA_API_KEY")

    if api_key is None or not api_key.strip():
        raise ConfigurationError(
            "TWELVE_DATA_API_KEY environment variable is required."
        )

    return api_key
