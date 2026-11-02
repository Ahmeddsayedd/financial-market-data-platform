"""CLI safety checks: no API or PostgreSQL dependencies required."""

import runpy
from pathlib import Path

import pytest


@pytest.fixture
def cli_main():
    root = Path(__file__).resolve().parents[2]
    return runpy.run_path(str(root / "scripts/verify_twelve_data_live.py"))["main"]


def test_live_without_api_key_fails_without_network(cli_main, monkeypatch, capsys):
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    # The repository's local .env is not accessible in CI; ignore it here.
    monkeypatch.setitem(cli_main.__globals__, "_load_local_env", lambda: None)
    assert cli_main(["--live", "--symbol", "AAPL"]) == 1
    output = capsys.readouterr()
    assert "FAIL:" in output.err
    assert "apikey" not in output.err


def test_gold_requires_confirmation_even_before_key(cli_main, capsys):
    assert cli_main(["--live", "--write-gold"]) == 1
    assert "FAIL:" in capsys.readouterr().err


def test_external_output_directory_is_rejected(cli_main, tmp_path, capsys):
    assert (
        cli_main(
            [
                "--live",
                "--output-dir",
                str(tmp_path),
            ]
        )
        == 1
    )
    assert "FAIL:" in capsys.readouterr().err
