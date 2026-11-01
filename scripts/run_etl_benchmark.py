"""Run a bounded offline benchmark against a verified M10 synthetic dataset."""

import argparse
from pathlib import Path

from financial_data_platform.experiments.benchmark import (
    run_benchmark,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New .jsonl file")
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument("--warmups", type=int, default=1)
    args = parser.parse_args()
    try:
        results = run_benchmark(
            dataset_dir=args.dataset,
            result_path=args.output,
            repetitions=args.repetitions,
            warmups=args.warmups,
        )
    except (ValueError, OSError) as exc:
        # Do not expose filesystem paths or arbitrary provider responses in CI logs.
        parser.error(
            f"Benchmark preflight failed ({type(exc).__name__}); inspect locally"
        )
    measured = [row for row in results if not row["warmup"]]
    success_count = sum(row["status"] == "success" for row in measured)
    print(
        f"PASS: recorded {len(measured)} measured attempts and "
        f"{len(results) - len(measured)} warm-ups; "
        f"{success_count} measured successes, {len(measured) - success_count} failures"
    )
    if success_count != len(measured):
        parser.exit(status=1, message="Some measured attempts failed; review JSONL\n")


if __name__ == "__main__":
    main()
