"""Analyze existing offline benchmark JSONL evidence without running ETL."""

import argparse
from pathlib import Path

from financial_data_platform.experiments.performance_analysis import (
    write_performance_analysis,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input", type=Path, required=True, action="append", dest="inputs"
    )
    parser.add_argument("--json-output", required=True, type=Path)
    parser.add_argument("--markdown-output", required=True, type=Path)
    args = parser.parse_args()
    try:
        report = write_performance_analysis(
            inputs=args.inputs,
            json_output=args.json_output,
            markdown_output=args.markdown_output,
        )
    except (ValueError, OSError) as exc:
        parser.error(
            f"Performance analysis failed ({type(exc).__name__}); inspect locally"
        )
    print(
        f"PASS: analyzed {len(report['groups'])} workload groups and "
        f"{len(report['comparisons'])} eligible scaling comparisons"
    )


if __name__ == "__main__":
    main()
