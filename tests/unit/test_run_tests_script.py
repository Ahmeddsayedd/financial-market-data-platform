"""Tests for the reproducible pytest runner."""

import pytest
import runpy
import sys
from pathlib import Path
from unittest.mock import patch


def test_runner_forwards_pytest_arguments(tmp_path):
    """Extra command-line arguments must reach pytest unchanged."""
    script = Path(__file__).resolve().parents[2] / "scripts" / "run_tests.py"

    env_file = tmp_path / ".env"
    env_file.write_text("POSTGRES_PASSWORD=testpassword\n", encoding="utf-8")

    with (
        patch("pathlib.Path.is_file", return_value=True),
        patch(
            "pathlib.Path.read_text",
            return_value=env_file.read_text(encoding="utf-8"),
        ),
        patch("subprocess.call", return_value=0) as mock_call,
        patch.object(
            sys,
            "argv",
            ["run_tests.py", "-k", "test_example"],
        ),
    ):
        with pytest.raises(SystemExit) as exc_info:
            runpy.run_path(str(script), run_name="__main__")

        assert exc_info.value.code == 0

    mock_call.assert_called_once()
    args, kwargs = mock_call.call_args

    assert args[0] == [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-k",
        "test_example",
    ]
    assert kwargs["env"]["POSTGRES_PASSWORD"] == "testpassword"


def test_runner_fails_when_env_file_is_missing():
    """Do not launch pytest when the local .env file is missing."""
    script = Path(__file__).resolve().parents[2] / "scripts" / "run_tests.py"

    with (
        patch("pathlib.Path.is_file", return_value=False),
        patch("subprocess.call") as mock_call,
        patch.object(sys, "argv", ["run_tests.py"]),
        pytest.raises(SystemExit) as exc_info,
    ):
        runpy.run_path(str(script), run_name="__main__")

    assert exc_info.value.code == 1
    mock_call.assert_not_called()