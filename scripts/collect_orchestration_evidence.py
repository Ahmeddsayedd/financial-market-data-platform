"""Collect sanitized, read-only Airflow tracking and Gold demonstration evidence."""

import argparse
import json
import os
import sys
from pathlib import Path

from financial_data_platform.experiments.orchestration_evidence import (
    EvidenceError,
    TEST_DATABASE,
    collect_orchestration_evidence,
)

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT_DIR = ROOT / "data" / "experiments"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--airflow-run-id", required=True)
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--confirm-test-db", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        output = args.output.resolve()
        if (
            output.suffix != ".json"
            or not output.is_relative_to(EXPERIMENT_DIR.resolve())
            or output.exists()
            or output.is_symlink()
            or not output.parent.is_dir()
        ):
            raise EvidenceError("Use a new JSON output under data/experiments.")
        if os.getenv("POSTGRES_DB") != TEST_DATABASE:
            raise EvidenceError("POSTGRES_DB must be financial_market_test.")
        result = collect_orchestration_evidence(
            airflow_run_id=args.airflow_run_id,
            symbol=args.symbol,
            confirmation=args.confirm_test_db,
        )
        # A tracking result may be running/failed; retain it without claiming PASS.
        output.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except (EvidenceError, OSError, ValueError, TypeError):
        print(
            "FAIL: Read-only evidence collection could not be verified.",
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "status": "RECORDED",
                "tracking_status": result["airflow_tracking"]["status"],
                "gold_rows": result["gold_snapshot"]["row_count"],
                "api_requests": 0,
                "database_writes": 0,
                "report": str(args.output),
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
