"""Run project tests using credentials from the local .env file."""

import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = PROJECT_ROOT / ".env"


def main() -> int:
    if not ENV_FILE.is_file():
        print("Error: .env file not found.", file=sys.stderr)
        return 1

    environment = os.environ.copy()

    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()

        if not line or line.startswith("#"):
            continue

        key, separator, value = line.partition("=")

        if separator:
            environment[key.strip()] = value.strip()

    return subprocess.call(
        [sys.executable, "-m", "pytest", "-q", *sys.argv[1:]],
        cwd=PROJECT_ROOT,
        env=environment,
    )


if __name__ == "__main__":
    raise SystemExit(main())
