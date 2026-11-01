"""Compare offline M10 benchmark JSONL evidence with a verified workload manifest."""

import argparse
from pathlib import Path

from financial_data_platform.experiments.quality_evaluation import evaluate_quality


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument(
        "--results", type=Path, required=True, help="Existing benchmark JSONL"
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="New quality report JSON"
    )
    args = parser.parse_args()
    try:
        report = evaluate_quality(
            dataset_dir=args.dataset,
            benchmark_results=args.results,
            output_path=args.output,
        )
    except (ValueError, OSError) as exc:
        # Never reflect exception text, arbitrary file paths or payload bytes.
        parser.error(f"Quality evaluation preflight failed ({type(exc).__name__})")
    summary = report["summary"]
    print(
        "RESULT: quality evidence recorded; "
        f"{summary['measured_matching_attempts']}/{summary['measured_attempts']} "
        "measured attempts matched expected outcomes; "
        f"{summary['measured_parser_failures']} parser failures"
    )
    if not summary["all_matched"]:
        parser.exit(
            status=1, message="Quality discrepancies found; review JSON report\n"
        )


if __name__ == "__main__":
    main()
