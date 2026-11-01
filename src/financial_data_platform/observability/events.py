"""Safe, correlated structured event logging for operational diagnostics.

Events have fixed names and metadata keys. Do not log raw payloads, exception
messages, environment dumps, or database connection parameters.
"""

import json
import logging
import re
from datetime import datetime, timezone
from uuid import UUID

_ALLOWED_FIELDS = frozenset(
    {
        "dag_id",
        "airflow_run_id",
        "pipeline_run_id",
        "stage",
        "status",
        "provider",
        "files_written",
        "files_loaded",
        "records_read",
        "records_extracted",
        "records_validated",
        "records_transformed",
        "records_loaded",
        "records_rejected",
        "valid_count",
        "invalid_count",
        "total_records",
        "inserted",
        "updated",
        "unchanged",
        "rejected",
        "error_type",
    }
)
_SECRET_WORDS = re.compile(
    r"password|passwd|secret|token|api[_-]?key|authorization|bearer|"
    r"postgres(?:ql)?://|://[^/\s:@]+:[^/\s@]+@",
    re.IGNORECASE,
)
_IDENT = re.compile(r"^[A-Za-z0-9_./:+@-]{1,160}$")
_EVENT = re.compile(r"^[a-z][a-z0-9_]{1,63}$")
_SUBSYSTEM = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


def _safe_value(key: str, value: object) -> str | int | None:
    """Accept only bounded safe metadata; never stringify untrusted objects."""
    if value is None:
        return None
    if key not in _ALLOWED_FIELDS:
        raise ValueError(f"Unsupported diagnostic field: {key}")
    if type(value) is int:
        if value < 0:
            raise ValueError("Diagnostic counters must be nonnegative")
        return value
    if isinstance(value, UUID):
        return str(value)
    if not isinstance(value, str):
        return "[REDACTED]"
    if _SECRET_WORDS.search(value) or not _IDENT.fullmatch(value):
        return "[REDACTED]"
    return value


def log_event(
    subsystem: str, event: str, *, level: str = "INFO", **fields: object
) -> None:
    """Emit one JSON event through the existing Python/Airflow log handlers.

    The payload intentionally excludes raw error details; callers may provide
    a sanitized exception class name via ``error_type`` instead.
    """
    if not _SUBSYSTEM.fullmatch(subsystem):
        raise ValueError("Invalid diagnostic subsystem")
    if not _EVENT.fullmatch(event):
        raise ValueError("Invalid diagnostic event name")
    if level not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
        raise ValueError("Unsupported diagnostic severity")
    payload: dict[str, str | int | None] = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "severity": level,
        "subsystem": subsystem,
        "event": event,
    }
    for key, value in fields.items():
        if key in payload:
            raise ValueError("Reserved diagnostic field")
        payload[key] = _safe_value(key, value)
    logging.getLogger(f"financial_data_platform.{subsystem}").log(
        getattr(logging, level), json.dumps(payload, sort_keys=True)
    )
