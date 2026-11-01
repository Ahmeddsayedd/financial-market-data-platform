"""Offline Docker Compose contract validation without printing interpolated secrets."""

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_NETWORK = "financial-market-shared"
# These values exist only in the subprocess environment for config parsing.
DUMMY_ENV = {
    "POSTGRES_DB": "financial_market_test",
    "POSTGRES_USER": "compose_validation",
    "POSTGRES_PASSWORD": "compose_validation_dummy",
    "POSTGRES_PORT": "5433",
    "AIRFLOW_POSTGRES_DB": "airflow_validation",
    "AIRFLOW_POSTGRES_USER": "airflow_validation",
    "AIRFLOW_POSTGRES_PASSWORD": "airflow_validation_dummy",
    "AIRFLOW_JWT_SECRET": "compose_validation_jwt_dummy",
    "AIRFLOW_PORT": "8080",
    "ENABLE_TWELVE_DATA_INGESTION": "false",
    "ENABLE_GOLD_LOADING": "false",
    "TWELVE_DATA_API_KEY": "",
}


def load_compose(filename: str) -> dict:
    """Resolve Compose to JSON in memory; never print its environment section."""
    env = {**os.environ, **DUMMY_ENV}
    result = subprocess.run(
        ["docker", "compose", "-f", filename, "config", "--format", "json"],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"{filename} is not a valid Compose configuration "
            f"(exit status {result.returncode}); inspect locally."
        )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{filename}: Compose produced invalid JSON") from exc


def validate_healthcheck(service: dict, expected: str, service_name: str) -> None:
    """Require an actual probe plus bounded timing values."""
    health = service.get("healthcheck")
    if not isinstance(health, dict):
        raise ValueError(f"{service_name} lacks a healthcheck")
    probe = health.get("test", [])
    if not isinstance(probe, list) or expected not in " ".join(probe):
        raise ValueError(f"{service_name}: unexpected healthcheck command")
    for key in ("interval", "timeout", "retries", "start_period"):
        if key not in health:
            raise ValueError(f"{service_name}: missing healthcheck {key}")


def validate_configs(gold: dict, airflow: dict) -> None:
    """Assert safety and service health contracts after Compose resolution."""
    gold_services = gold.get("services", {})
    airflow_services = airflow.get("services", {})
    validate_healthcheck(gold_services.get("postgres", {}), "pg_isready", "postgres")
    validate_healthcheck(
        airflow_services.get("airflow-postgres", {}),
        "pg_isready",
        "airflow-postgres",
    )
    expected_probes = {
        "airflow-api-server": "/api/v2/monitor/health",
        "airflow-scheduler": "--job-type SchedulerJob",
        "airflow-dag-processor": "--job-type DagProcessorJob",
    }
    for name, probe in expected_probes.items():
        validate_healthcheck(airflow_services.get(name, {}), probe, name)

    for name, config in (("compose.yaml", gold), ("compose.airflow.yaml", airflow)):
        networks = config.get("networks", {})
        if not any(
            isinstance(network, dict)
            and network.get("external") is True
            and network.get("name") == EXPECTED_NETWORK
            for network in networks.values()
        ):
            raise ValueError(f"{name}: shared external network missing")

    api_ports = airflow_services["airflow-api-server"].get("ports", [])
    if not api_ports or any(port.get("host_ip") != "127.0.0.1" for port in api_ports):
        raise ValueError("Airflow API server must bind to localhost")
    gold_ports = gold_services["postgres"].get("ports", [])
    if not gold_ports or any(port.get("host_ip") != "127.0.0.1" for port in gold_ports):
        raise ValueError("Gold PostgreSQL must bind to localhost")

    scheduler_env = airflow_services["airflow-scheduler"].get("environment", {})
    for key in ("ENABLE_TWELVE_DATA_INGESTION", "ENABLE_GOLD_LOADING"):
        if str(scheduler_env.get(key, "")).lower() != "false":
            raise ValueError(f"Scheduler must disable {key} during validation")
    if scheduler_env.get("POSTGRES_DB") != "financial_market_test":
        raise ValueError("Scheduler must target financial_market_test")
    if "airflow-init" not in airflow_services:
        raise ValueError("Missing Airflow initialization service")
    init_deps = airflow_services["airflow-init"].get("depends_on", {})
    if init_deps.get("airflow-postgres", {}).get("condition") != "service_healthy":
        raise ValueError("Airflow init must wait for healthy metadata PostgreSQL")
    for name in expected_probes:
        deps = airflow_services[name].get("depends_on", {})
        if (
            deps.get("airflow-init", {}).get("condition")
            != "service_completed_successfully"
        ):
            raise ValueError(f"{name} must wait for completed Airflow init")


def main() -> None:
    """Check both Compose files without starting Docker services."""
    gold = load_compose("compose.yaml")
    airflow = load_compose("compose.airflow.yaml")
    validate_configs(gold, airflow)
    print("PASS: Both Compose files resolve with non-secret test placeholders")
    print("PASS: PostgreSQL and Airflow application health probes are defined")
    print("PASS: Localhost bindings, dependencies, and safety defaults are intact")
    print("PASS: No containers were started or database operations performed")


if __name__ == "__main__":
    main()
