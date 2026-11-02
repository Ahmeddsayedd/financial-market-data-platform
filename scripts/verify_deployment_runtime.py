"""Read-only local Docker Compose startup/health snapshot for Issue #97.

Does not start/stop containers, invoke DAGs, or print credentials or logs.
"""

import argparse
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STACKS = {
    "compose.yaml": ("postgres",),
    "compose.airflow.yaml": (
        "airflow-postgres",
        "airflow-init",
        "airflow-api-server",
        "airflow-scheduler",
        "airflow-dag-processor",
    ),
}


def docker(args: list[str]) -> subprocess.CompletedProcess[str]:
    """Capture output privately, including potentially sensitive Docker errors."""
    try:
        return subprocess.run(
            ["docker", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Docker command unavailable or timed out") from exc


def classify_service(service: str, details: dict) -> tuple[bool, str]:
    """Require active, healthy containers; init is a successful one-shot job."""
    state = details.get("State", {})
    if not isinstance(state, dict):
        return False, "invalid container state"
    status = state.get("Status", "unknown")
    if service == "airflow-init":
        ok = status == "exited" and state.get("ExitCode") == 0
        return ok, "completed (exit 0)" if ok else "not successfully completed"
    health = state.get("Health", {})
    health_status = health.get("Status") if isinstance(health, dict) else None
    ok = status == "running" and health_status == "healthy"
    return ok, f"{status}; health={health_status or 'unknown'}"


def check_stack(
    filename: str, services: tuple[str, ...]
) -> list[tuple[str, bool, str]]:
    """Discover only the named project's service containers, without changes."""
    observations = []
    for service in services:
        result = docker(["compose", "-f", filename, "ps", "--all", "--quiet", service])
        if result.returncode:
            observations.append((service, False, "Compose query failed"))
            continue
        ids = result.stdout.strip().splitlines()
        if len(ids) != 1 or not ids[0].strip():
            observations.append((service, False, "expected one existing container"))
            continue
        inspect = docker(["inspect", "--format", "{{json .State}}", ids[0].strip()])
        if inspect.returncode:
            observations.append((service, False, "container inspect failed"))
            continue
        try:
            state = json.loads(inspect.stdout)
        except json.JSONDecodeError:
            observations.append((service, False, "invalid inspection result"))
            continue
        ok, description = classify_service(service, {"State": state})
        observations.append((service, ok, description))
    return observations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stack",
        choices=("gold", "airflow", "all"),
        default="all",
        help="existing local stack to inspect (default: all)",
    )
    args = parser.parse_args()
    selection = {
        "gold": ("compose.yaml",),
        "airflow": ("compose.airflow.yaml",),
        "all": tuple(STACKS),
    }[args.stack]
    try:
        results = [
            (filename, *observation)
            for filename in selection
            for observation in check_stack(filename, STACKS[filename])
        ]
    except RuntimeError as exc:
        print(f"FAIL: {exc}")
        return 2
    for filename, service, ok, description in results:
        print(f"{'PASS' if ok else 'FAIL'}: {filename} / {service}: {description}")
    if all(ok for _, _, ok, _ in results):
        print("PASS: All inspected containers reached their required states")
        return 0
    print("FAIL: One or more inspected containers is absent, unhealthy, or incomplete")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
