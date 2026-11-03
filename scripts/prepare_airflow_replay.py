"""Prepare an existing Twelve Data Raw file for a controlled offline Airflow run."""

import argparse
import json
import sys
from pathlib import Path

from financial_data_platform.orchestration.replay_demo import (
    ReplayPreparationError,
    prepare_airflow_replay,
)

ROOT = Path(__file__).resolve().parents[1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-raw", type=Path, required=True)
    parser.add_argument("--symbol", default="AAPL")
    args = parser.parse_args(argv)
    try:
        result = prepare_airflow_replay(
            source=args.source_raw,
            experiment_root=ROOT / "data/experiments",
            airflow_raw_root=ROOT / "data/raw",
            symbol=args.symbol,
        )
    except (OSError, ReplayPreparationError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
