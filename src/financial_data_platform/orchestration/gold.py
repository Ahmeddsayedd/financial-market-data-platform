"""Reusable Silver-to-Gold orchestration adapter."""

from pathlib import Path
from typing import Sequence

from financial_data_platform.storage.silver_reader import (
    read_silver_parquet,
)
from financial_data_platform.warehouse.gold_loader import (
    load_market_records,
)


def load_silver_paths_to_gold(
    *,
    relative_paths: Sequence[str],
    silver_base_dir: Path,
) -> dict[str, object]:
    """Load selected Silver partitions into Gold as one transaction."""

    selected_paths = tuple(relative_paths)

    if not selected_paths:
        raise ValueError("At least one Silver file must be selected")

    silver_root = silver_base_dir.resolve()
    resolved_paths: list[Path] = []

    for relative_name in selected_paths:
        if not isinstance(relative_name, str) or not relative_name:
            raise ValueError("Silver paths must be nonempty strings")

        relative_path = Path(relative_name)

        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise ValueError("Silver path must remain inside Silver storage")

        resolved_path = (silver_root / relative_path).resolve()

        if not resolved_path.is_relative_to(silver_root):
            raise ValueError("Silver path escapes Silver storage")

        if resolved_path.suffix != ".parquet":
            raise ValueError("Selected Silver file must be Parquet")

        if not resolved_path.is_file():
            raise FileNotFoundError(
                f"Silver file does not exist: {relative_name}"
            )

        resolved_paths.append(resolved_path)

    if len(set(resolved_paths)) != len(resolved_paths):
        raise ValueError("Duplicate Silver files are not allowed")

    # Read and validate the entire selected input before opening
    # the PostgreSQL write transaction.
    records = []

    for path in resolved_paths:
        records.extend(read_silver_parquet(path))

    if not records:
        raise ValueError("Selected Silver files contain no records")

    # The existing loader manages commit, rollback, and cleanup.
    counts = load_market_records(records)

    return {
        "status": "success",
        "files_loaded": len(resolved_paths),
        "records_read": len(records),
        "inserted": counts["inserted"],
        "updated": counts["updated"],
        "unchanged": counts["unchanged"],
        "rejected": counts["rejected"],
        "silver_paths": [str(path) for path in resolved_paths],
    }