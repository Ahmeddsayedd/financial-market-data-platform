"""Database-independent checks for the offline Streamlit smoke runner."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from scripts import smoke_dashboard


def _page(*, heading="Gold warehouse overview", error=True, exception=False):
    return SimpleNamespace(
        header=[SimpleNamespace(value=heading)],
        error=(
            [SimpleNamespace(value="The Gold warehouse is unavailable.")]
            if error
            else []
        ),
        exception=["internal failure"] if exception else [],
    )


def test_offline_configuration_never_targets_a_live_database():
    assert smoke_dashboard.OFFLINE_ENV["POSTGRES_HOST"] == "127.0.0.1"
    assert smoke_dashboard.OFFLINE_ENV["POSTGRES_PORT"] == "1"
    assert smoke_dashboard.OFFLINE_ENV["ENABLE_GOLD_LOADING"] == "false"
    assert smoke_dashboard.OFFLINE_ENV["ENABLE_TWELVE_DATA_INGESTION"] == "false"


def test_smoke_covers_all_four_dashboard_pages():
    assert [page for page, _ in smoke_dashboard.PAGES] == [
        "Overview",
        "Market charts",
        "Indicators",
        "Pipeline monitoring",
    ]


def test_check_page_accepts_expected_disconnected_state():
    smoke_dashboard.check_page(
        _page(), name="Overview", heading="Gold warehouse overview"
    )


@pytest.mark.parametrize(
    "page",
    [
        _page(heading="Incorrect heading"),
        _page(error=False),
        _page(exception=True),
    ],
)
def test_check_page_rejects_invalid_execution(page):
    with pytest.raises(AssertionError):
        smoke_dashboard.check_page(
            page, name="Overview", heading="Gold warehouse overview"
        )


def test_runner_uses_sandboxed_environment_and_navigates(monkeypatch):
    import os
    import sys

    selected = []
    app = MagicMock()
    app.header = [SimpleNamespace(value="Gold warehouse overview")]
    app.error = [SimpleNamespace(value="The Gold warehouse is unavailable.")]
    app.exception = []

    def change_page(value):
        selected.append(value)
        app.header = [SimpleNamespace(value=dict(smoke_dashboard.PAGES)[value])]
        return app

    app.sidebar.radio.__getitem__.return_value.set_value.side_effect = change_page
    app.run.return_value = app

    app_test_class = MagicMock()
    app_test_class.from_file.return_value = app
    fake_module = SimpleNamespace(AppTest=app_test_class)
    monkeypatch.setitem(sys.modules, "streamlit", MagicMock())
    monkeypatch.setitem(sys.modules, "streamlit.testing", MagicMock())
    monkeypatch.setitem(sys.modules, "streamlit.testing.v1", fake_module)
    original_port = os.environ.get("POSTGRES_PORT")

    smoke_dashboard.run_smoke()

    assert selected == ["Market charts", "Indicators", "Pipeline monitoring"]
    assert os.environ.get("POSTGRES_PORT") == original_port
    assert app.run.call_count == 4
