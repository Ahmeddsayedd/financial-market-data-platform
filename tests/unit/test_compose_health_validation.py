"""Tests for offline and non-secret-bearing Compose health validation."""

import json
from unittest.mock import Mock, patch

import pytest

from scripts import validate_compose_health as checker


def _healthy(command):
    return {
        "test": ["CMD-SHELL", command],
        "interval": "30s",
        "timeout": "10s",
        "retries": 5,
        "start_period": "60s",
    }


def _configs():
    networks = {"shared": {"name": "financial-market-shared", "external": True}}
    postgres = {
        "healthcheck": _healthy("pg_isready"),
        "ports": [{"host_ip": "127.0.0.1"}],
    }
    gold = {"networks": networks, "services": {"postgres": postgres}}
    airflow = {
        "networks": networks,
        "services": {
            "airflow-postgres": {"healthcheck": _healthy("pg_isready")},
            "airflow-init": {
                "depends_on": {"airflow-postgres": {"condition": "service_healthy"}}
            },
            "airflow-api-server": {
                "healthcheck": _healthy("/api/v2/monitor/health"),
                "ports": [{"host_ip": "127.0.0.1"}],
                "depends_on": {
                    "airflow-init": {"condition": "service_completed_successfully"}
                },
            },
            "airflow-scheduler": {
                "healthcheck": _healthy("--job-type SchedulerJob"),
                "depends_on": {
                    "airflow-init": {"condition": "service_completed_successfully"}
                },
                "environment": {
                    "ENABLE_TWELVE_DATA_INGESTION": "false",
                    "ENABLE_GOLD_LOADING": "false",
                    "POSTGRES_DB": "financial_market_test",
                },
            },
            "airflow-dag-processor": {
                "healthcheck": _healthy("--job-type DagProcessorJob"),
                "depends_on": {
                    "airflow-init": {"condition": "service_completed_successfully"}
                },
            },
        },
    }
    return gold, airflow


def test_good_configuration_passes():
    checker.validate_configs(*_configs())


@pytest.mark.parametrize(
    ("service", "probe"),
    [
        ("airflow-api-server", "/api/v2/monitor/health"),
        ("airflow-scheduler", "--job-type SchedulerJob"),
        ("airflow-dag-processor", "--job-type DagProcessorJob"),
    ],
)
def test_missing_health_probes_fail(service, probe):
    gold, airflow = _configs()
    airflow["services"][service]["healthcheck"]["test"] = ["CMD", "true"]
    with pytest.raises(ValueError, match="unexpected healthcheck"):
        checker.validate_configs(gold, airflow)


def test_missing_timing_fails():
    gold, airflow = _configs()
    del airflow["services"]["airflow-scheduler"]["healthcheck"]["timeout"]
    with pytest.raises(ValueError, match="missing healthcheck timeout"):
        checker.validate_configs(gold, airflow)


def test_public_api_binding_fails():
    gold, airflow = _configs()
    airflow["services"]["airflow-api-server"]["ports"] = [{"host_ip": "0.0.0.0"}]
    with pytest.raises(ValueError, match="bind to localhost"):
        checker.validate_configs(gold, airflow)


def test_enabled_live_ingestion_fails():
    gold, airflow = _configs()
    environment = airflow["services"]["airflow-scheduler"]["environment"]
    environment["ENABLE_TWELVE_DATA_INGESTION"] = "true"
    with pytest.raises(ValueError, match="must disable"):
        checker.validate_configs(gold, airflow)


def test_wrong_database_fails():
    gold, airflow = _configs()
    environment = airflow["services"]["airflow-scheduler"]["environment"]
    environment["POSTGRES_DB"] = "financial_market"
    with pytest.raises(ValueError, match="financial_market_test"):
        checker.validate_configs(gold, airflow)


def test_compose_parse_captures_output_without_printing_credentials(capsys):
    secret = "TEST_SECRET_MUST_NOT_APPEAR"
    result = Mock(returncode=0, stdout=json.dumps({"secret": secret}), stderr="")
    with patch.object(checker.subprocess, "run", return_value=result) as called:
        assert checker.load_compose("compose.yaml") == {"secret": secret}
    assert called.call_args.kwargs["capture_output"] is True
    assert secret not in capsys.readouterr().out
    env = called.call_args.kwargs["env"]
    assert env["POSTGRES_PASSWORD"] == "compose_validation_dummy"


def test_compose_failure_does_not_reveal_stderr(capsys):
    secret = "TEST_SECRET_MUST_NOT_APPEAR"
    result = Mock(returncode=1, stdout="", stderr=secret)
    with patch.object(checker.subprocess, "run", return_value=result):
        with pytest.raises(RuntimeError, match="exit status 1") as exc:
            checker.load_compose("compose.airflow.yaml")
    assert secret not in str(exc.value)
    assert secret not in capsys.readouterr().out
