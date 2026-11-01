"""Seed or clean isolated dashboard demonstration records, never production."""

import argparse
from pathlib import Path

from dotenv import load_dotenv

from financial_data_platform.dashboard.demo_data import (
    DEMO_SOURCE,
    cleanup_demo_data,
    new_demo_symbol,
    seed_demo_data,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("seed", help="Create a new unique disposable demo dataset")
    clean = commands.add_parser("clean", help="Remove a specified demo dataset")
    clean.add_argument("--symbol", required=True)
    args = parser.parse_args()

    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=False)
    if args.command == "seed":
        symbol = new_demo_symbol()
        seed_demo_data(symbol)
        print(
            f"Created 35 observations and 3 pipeline runs: "
            f"source={DEMO_SOURCE}, symbol={symbol}"
        )
        print(f"Clean with: python scripts/dashboard_demo.py clean --symbol {symbol}")
    else:
        cleanup_demo_data(args.symbol)
        print(f"Cleaned demo-owned records for {DEMO_SOURCE}/{args.symbol}")


if __name__ == "__main__":
    main()
