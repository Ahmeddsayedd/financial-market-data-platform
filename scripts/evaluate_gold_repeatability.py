"""Explicit, rollback-only Gold evaluation against financial_market_test."""

import argparse
from pathlib import Path

from financial_data_platform.experiments.gold_repeatability import (
    run_gold_repeatability,
)
from financial_data_platform.experiments.workloads import DEFAULT_SEED


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="New .json file")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--authorize-test-db", action="store_true", required=True)
    args = parser.parse_args()
    try:
        report = run_gold_repeatability(
            output=args.output,
            authorize_test_db=args.authorize_test_db,
            seed=args.seed,
        )
    except (ValueError, RuntimeError, OSError) as exc:
        parser.error(f"Gold evaluation failed ({type(exc).__name__}); inspect locally")
    print(
        f"PASS: {len(report['scenarios'])} Gold scenarios matched; "
        "all experiment writes rolled back"
    )


if __name__ == "__main__":
    main()
