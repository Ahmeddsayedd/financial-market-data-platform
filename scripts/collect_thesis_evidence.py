"""Measure repeated offline real-data replays and optionally read audited test Gold."""

import argparse
import json
import os
import sys
from pathlib import Path

from financial_data_platform.experiments.end_to_end_evidence import (
    run_replay_experiment,
)
from financial_data_platform.experiments.live_market_verification import (
    TEST_DATABASE,
    VerificationError,
)

ROOT = Path(__file__).resolve().parents[1]


def _load_local_env() -> None:
    path = ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--replay-raw", type=Path, required=True)
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument(
        "--experiment-root",
        type=Path,
        default=ROOT / "data/experiments/issue103-live",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=1)
    parser.add_argument("--audit-test-gold", action="store_true")
    parser.add_argument("--confirm-test-db", default="")
    args = parser.parse_args(argv)
    try:
        if args.audit_test_gold:
            if args.confirm_test_db != TEST_DATABASE:
                raise VerificationError("Explicit test database confirmation required.")
            _load_local_env()
            # Process-local override; read-only preflight also checks server identity.
            os.environ["POSTGRES_DB"] = TEST_DATABASE
        result = run_replay_experiment(
            root=args.experiment_root,
            raw_path=args.replay_raw,
            symbol=args.symbol,
            report_path=args.output,
            repetitions=args.repetitions,
            warmups=args.warmups,
            audit_gold=args.audit_test_gold,
            confirmation=args.confirm_test_db,
        )
    except (VerificationError, OSError, ValueError, RuntimeError, KeyError):
        print(
            "FAIL: Evidence collection failed; inspect safe local configuration.",
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "status": "PASS",
                "report": str(args.output),
                "repetitions": result["repetitions"],
                "valid_count": result["quality"]["valid_count"],
                "median_raw_to_silver_seconds": result["raw_to_silver_seconds"][
                    "median"
                ],
                "audited_gold_rows": (
                    result["gold_audit"]["row_count"] if result["gold_audit"] else None
                ),
                "api_requests": 0,
                "gold_writes": 0,
            },
            sort_keys=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
