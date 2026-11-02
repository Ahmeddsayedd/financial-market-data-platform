"""Static links and scope contracts for M11 portfolio release-readiness audit."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OPS = ROOT / "docs" / "operations"


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def test_m11_audit_and_checklist_exist_and_are_linked():
    for name in ("m11-v1-release-audit.md", "m11-v1-release-checklist.md"):
        assert (OPS / name).is_file()
        assert f"]({name})" in read("docs/operations/README.md")
        assert f"](docs/operations/{name})" in read("README.md")


def test_audit_preserves_evidence_limits_and_followup():
    doc = read("docs/operations/m11-v1-release-audit.md")
    for item in (
        "0.1.0",
        "compose.yaml",
        "compose.airflow.yaml",
        "Dockerfile.airflow",
        "Dockerfile.dashboard",
        "seven jobs",
        "P1",
        "P2",
        "not a live deployment",
        "No P0 credential exposure is established",
        "M11-06",
    ):
        assert item.lower() in doc.lower()


def test_release_gate_starts_unchecked_and_requires_approval():
    doc = read("docs/operations/m11-v1-release-checklist.md")
    assert "- [x]" not in doc.lower()
    assert "- [ ]" in doc
    for item in (
        "financial_market_test",
        "python scripts/run_tests.py",
        "python scripts/validate_compose_health.py",
        "seven",
        "GitHub Release",
        "release commit",
        "secrets",
    ):
        assert item.lower() in doc.lower()


def test_new_readme_links_resolve():
    for name in ("m11-v1-release-audit.md", "m11-v1-release-checklist.md"):
        assert (OPS / name).exists()
