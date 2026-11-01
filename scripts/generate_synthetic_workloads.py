"""Generate deterministic offline synthetic Raw payloads in an explicit directory."""

import argparse
from pathlib import Path

from financial_data_platform.experiments.workloads import (
    DEFAULT_SEED,
    PROFILES,
    SCENARIOS,
    write_workload,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, required=True, help="New, nonexisting directory"
    )
    parser.add_argument("--profile", choices=PROFILES, default="small")
    parser.add_argument("--scenario", choices=SCENARIOS, default="clean")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--symbols", type=int, default=4)
    parser.add_argument("--invalid-count", type=int, default=0)
    args = parser.parse_args()
    try:
        result = write_workload(
            output_dir=args.output,
            profile=args.profile,
            scenario=args.scenario,
            seed=args.seed,
            symbol_count=args.symbols,
            invalid_count=args.invalid_count,
        )
    except (ValueError, FileExistsError, OSError) as exc:
        parser.error(str(exc))
    print(
        f"PASS: Generated {result['expected_unique_observations']} synthetic "
        f"observations across {result['symbol_count']} symbols; "
        f"scenario={result['scenario']}; dataset_sha256={result['dataset_sha256']}"
    )


if __name__ == "__main__":
    main()
