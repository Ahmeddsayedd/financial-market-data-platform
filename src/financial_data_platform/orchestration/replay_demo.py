"""Stage one already-captured Twelve Data response for an offline Airflow run.

No API calls, database connections, or DAG triggers are performed here.
"""

import hashlib
import json
import re
from pathlib import Path

_SYMBOL = re.compile(r"[A-Z][A-Z0-9.-]{0,14}\Z")
_STAMP = re.compile(r"\d{8}T\d{12}Z\.json\Z")


class ReplayPreparationError(ValueError):
    """Unsafe or inconsistent replay input."""


def prepare_airflow_replay(
    *, source: Path, experiment_root: Path, airflow_raw_root: Path, symbol: str
) -> dict[str, object]:
    """Copy verified Raw JSON to the Airflow-mounted Raw root without overwriting it.

    Both roots are caller-supplied so this is independently unit-testable.
    """
    if not isinstance(symbol, str) or not _SYMBOL.fullmatch(symbol):
        raise ReplayPreparationError("Use one uppercase symbol (max 15 characters).")

    experiments = experiment_root.resolve()
    selected = source.resolve()
    if not selected.is_relative_to(experiments) or not selected.is_file():
        raise ReplayPreparationError(
            "Input must be an existing file in data/experiments."
        )
    parts = selected.relative_to(experiments).parts
    if len(parts) < 7 or parts[-7] != "raw" or parts[-6] != "twelve_data":
        raise ReplayPreparationError("Expected an archived Twelve Data Raw response.")
    if parts[-5] != symbol or not _STAMP.fullmatch(parts[-1]):
        raise ReplayPreparationError(
            "Raw path symbol or extraction filename is invalid."
        )
    # Relative paths are twelve_data / symbol / year / month / day / filename.
    relative = Path(*parts[-6:])
    if len(relative.parts) != 6 or not (
        re.fullmatch(r"\d{4}", relative.parts[2])
        and re.fullmatch(r"\d{2}", relative.parts[3])
        and re.fullmatch(r"\d{2}", relative.parts[4])
    ):
        raise ReplayPreparationError("Invalid Raw date partition.")

    try:
        payload = json.loads(selected.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ReplayPreparationError("Invalid Raw JSON.") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("meta"), dict):
        raise ReplayPreparationError("Raw response metadata is missing.")
    if payload["meta"].get("symbol") != symbol:
        raise ReplayPreparationError("Response symbol does not match path.")
    if not isinstance(payload.get("values"), list) or not payload["values"]:
        raise ReplayPreparationError("Raw response must contain observations.")

    original = selected.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    destination_root = airflow_raw_root.resolve()
    destination = (destination_root / relative).resolve()
    if not destination.is_relative_to(destination_root):
        raise ReplayPreparationError("Destination escapes Airflow Raw directory.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if not destination.is_file() or destination.read_bytes() != original:
            raise ReplayPreparationError(
                "Raw destination exists with different contents."
            )
        copied = False
    else:
        try:
            with destination.open("xb") as handle:
                handle.write(original)
        except FileExistsError as exc:
            raise ReplayPreparationError(
                "Raw destination was created concurrently."
            ) from exc
        copied = True

    return {
        "status": "READY",
        "symbol": symbol,
        "raw_relative_path": relative.as_posix(),
        "raw_sha256": digest,
        "observations_in_response": len(payload["values"]),
        "copy_performed": copied,
        "api_requests": 0,
        "dag_run_conf": {
            "allow_live_ingestion": False,
            "allow_gold_loading": True,
            "raw_relative_path": relative.as_posix(),
        },
    }
