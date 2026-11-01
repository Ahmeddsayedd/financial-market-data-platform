"""Offline Streamlit page-execution smoke check for CI and local development.

Runs the actual application script with Streamlit AppTest. All database
connections are deliberately redirected to an unreachable localhost port.
"""

import os
from pathlib import Path
from unittest.mock import patch

PAGES = (
    ("Overview", "Gold warehouse overview"),
    ("Market charts", "Market charts"),
    ("Indicators", "Financial indicators"),
    ("Pipeline monitoring", "Pipeline monitoring"),
)

# Override local .env values within this process; never contact the real database.
OFFLINE_ENV = {
    "POSTGRES_HOST": "127.0.0.1",
    "POSTGRES_PORT": "1",
    "POSTGRES_DB": "financial_market_test",
    "POSTGRES_USER": "offline_smoke",
    "POSTGRES_PASSWORD": "offline_smoke_dummy",
    "PGCONNECT_TIMEOUT": "2",
    "TWELVE_DATA_API_KEY": "",
    "ENABLE_TWELVE_DATA_INGESTION": "false",
    "ENABLE_GOLD_LOADING": "false",
}


def check_page(app_test, *, name: str, heading: str) -> None:
    """Ensure Streamlit executed the selected page without an uncaught exception."""
    if app_test.exception:
        raise AssertionError(f"Streamlit raised an exception on {name}")
    if not app_test.header or app_test.header[0].value != heading:
        raise AssertionError(f"Unexpected heading on {name}")
    if not app_test.error:
        raise AssertionError(f"Expected a safe database-unavailable state on {name}")
    expected = "The Gold warehouse is unavailable."
    if expected not in app_test.error[0].value:
        raise AssertionError(f"Unexpected database-error message on {name}")


def run_smoke() -> None:
    """Execute all four pages with explicitly disconnected offline settings."""
    from streamlit.testing.v1 import AppTest

    root = Path(__file__).resolve().parents[1]
    app_path = root / "src/financial_data_platform/dashboard/app.py"
    with patch.dict(os.environ, OFFLINE_ENV):
        tested = AppTest.from_file(str(app_path)).run(timeout=30)
        for index, (name, heading) in enumerate(PAGES):
            if index:
                tested.sidebar.radio[0].set_value(name).run(timeout=30)
            check_page(tested, name=name, heading=heading)
            print(f"PASS: {name} executes with safe offline database handling")
    print("PASS: All four Streamlit pages executed without external services")


if __name__ == "__main__":
    run_smoke()
