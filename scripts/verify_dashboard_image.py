"""Bounded offline health smoke for the packaged Streamlit dashboard image.

Run INSIDE the image with --network none. Does not query a database or provider.
"""

import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

HEALTH_URL = "http://127.0.0.1:8501/_stcore/health"
START_TIMEOUT_SECONDS = 40


def main() -> None:
    """Start Streamlit, verify its local HTTP endpoint, and clean up."""
    env = {
        **os.environ,
        "POSTGRES_HOST": "127.0.0.1",
        "POSTGRES_PORT": "1",
        "POSTGRES_DB": "financial_market_test",
        "POSTGRES_USER": "offline_smoke",
        "POSTGRES_PASSWORD": "offline_smoke_dummy",
        "PGCONNECT_TIMEOUT": "2",
        "ENABLE_TWELVE_DATA_INGESTION": "false",
        "ENABLE_GOLD_LOADING": "false",
        "TWELVE_DATA_API_KEY": "",
        "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
    }
    command = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        "src/financial_data_platform/dashboard/app.py",
        "--server.headless=true",
        "--server.address=127.0.0.1",
        "--server.port=8501",
        "--browser.gatherUsageStats=false",
    ]
    # Drop logs instead of printing potential exception/configuration details.
    with subprocess.Popen(
        command,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ) as process:
        try:
            deadline = time.monotonic() + START_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError("Dashboard process exited before healthy")
                try:
                    with urllib.request.urlopen(HEALTH_URL, timeout=2) as response:
                        if response.status == 200:
                            print(
                                "PASS: Dashboard image starts and reports healthy offline"
                            )
                            return
                except (OSError, urllib.error.URLError):
                    pass
                time.sleep(0.5)
            raise RuntimeError("Dashboard image did not become healthy in time")
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)


if __name__ == "__main__":
    main()
