"""Offline tests of opt-in, read-only runtime health inspection."""

import json
from unittest.mock import patch

import pytest

from scripts import verify_deployment_runtime as verifier


@pytest.mark.parametrize(
    ("name", "state", "expected"),
    [
        ("postgres", {"Status": "running", "Health": {"Status": "healthy"}}, True),
        ("postgres", {"Status": "running", "Health": {"Status": "starting"}}, False),
        ("postgres", {"Status": "exited", "Health": {"Status": "healthy"}}, False),
        ("postgres", {"Status": "running"}, False),
        ("airflow-init", {"Status": "exited", "ExitCode": 0}, True),
        ("airflow-init", {"Status": "exited", "ExitCode": 1}, False),
        ("airflow-init", {"Status": "running", "ExitCode": 0}, False),
    ],
)
def test_classify_service(name, state, expected):
    assert verifier.classify_service(name, {"State": state})[0] is expected


class Result:
    def __init__(self, code=0, stdout=""):
        self.returncode = code
        self.stdout = stdout


def test_stack_success_checks_each_container_without_mutations():
    calls = []

    def fake_docker(args):
        calls.append(args)
        if args[0] == "compose":
            return Result(stdout="container-id\n")
        return Result(
            stdout=json.dumps({"Status": "running", "Health": {"Status": "healthy"}})
        )

    with patch.object(verifier, "docker", side_effect=fake_docker):
        results = verifier.check_stack("compose.yaml", ("postgres",))
    assert results[0][1] is True
    assert [call[0] for call in calls] == ["compose", "inspect"]
    assert "--all" in calls[0]
    assert "--quiet" in calls[0]


def test_stack_missing_container_is_failure():
    with patch.object(verifier, "docker", return_value=Result()):
        results = verifier.check_stack("compose.yaml", ("postgres",))
    assert results[0][1] is False
    assert "expected one" in results[0][2]


def test_stack_does_not_expose_docker_stderr(capsys):
    result = Result(code=1, stdout="")
    result.stderr = "SECRET_DO_NOT_PRINT"
    with patch.object(verifier, "docker", return_value=result):
        results = verifier.check_stack("compose.yaml", ("postgres",))
        print(results[0][2])
    assert "SECRET_DO_NOT_PRINT" not in capsys.readouterr().out


def test_invalid_inspection_fails_closed():
    with patch.object(
        verifier,
        "docker",
        side_effect=[Result(stdout="abc\n"), Result(stdout="broken")],
    ):
        results = verifier.check_stack("compose.yaml", ("postgres",))
    assert results[0][1] is False
