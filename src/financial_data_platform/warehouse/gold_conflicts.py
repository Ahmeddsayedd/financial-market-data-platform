"""Decide how incoming market observations affect existing Gold facts."""

from typing import Any


def decide_fact_action(
    existing: dict[str, Any] | None,
    incoming: dict[str, Any],
) -> str:
    """Choose the action for an incoming market observation."""

    if existing is None:
        return "insert"

    if existing == incoming:
        return "unchanged"

    if incoming["extracted_at"] > existing["extracted_at"]:
        return "update"

    if incoming["extracted_at"] < existing["extracted_at"]:
        return "unchanged"

    return "reject"