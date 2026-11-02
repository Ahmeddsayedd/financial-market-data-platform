"""Opt-in live Twelve Data / offline replay validation for Issue #103.

Live mode performs exactly one HTTP request with retries disabled. No secrets
are printed. Writes to Gold require explicit confirmation and connect solely
to the financial_market_test database.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from financial_data_platform.experiments.live_market_verification import (
    TEST_DATABASE,
    VerificationError,
    validate_outputsize,
    validate_symbol,
    verify_market_data,
)
from financial_data_platform.providers.twelve_data.client import (
    TwelveDataClient,
    TwelveDataClientError,
)

ROOT = Path(__file__).resolve().parents[1]


def _load_local_env() -> None:
    """Read simple project .env values without printing or changing existing env."""
    path = ROOT / ".env"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = value.strip().strip('"').strip("'")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument(
        "--live", action="store_true", help="Authorize one real API request"
    )
    choice.add_argument(
        "--replay-raw", type=Path, help="Replay an existing local Raw JSON"
    )
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--outputsize", type=int, default=100)
    parser.add_argument(
        "--output-dir", type=Path, default=ROOT / "data/experiments/issue103-live"
    )
    parser.add_argument("--write-gold", action="store_true")
    parser.add_argument(
        "--confirm-test-db",
        default="",
        help="Must be financial_market_test for Gold writes",
    )
    args = parser.parse_args(argv)
    try:
        validate_symbol(args.symbol)
        validate_outputsize(args.outputsize)
        permitted_root = (ROOT / "data/experiments").resolve()
        if not args.output_dir.resolve().is_relative_to(permitted_root):
            raise VerificationError("Output must be under data/experiments.")
        if args.write_gold and args.confirm_test_db != TEST_DATABASE:
            raise VerificationError(
                "Gold writes require --confirm-test-db financial_market_test"
            )
        if args.live:
            _load_local_env()
            key = os.getenv("TWELVE_DATA_API_KEY", "")
            if not key.strip():
                raise VerificationError("TWELVE_DATA_API_KEY is not configured.")
            client = TwelveDataClient(api_key=key, max_retries=0)
        else:
            client = None
            if args.write_gold:
                _load_local_env()

        if args.write_gold:
            # A separate, explicit command-line confirmation is required.
            # Force only the approved test database in this process; do not
            # rewrite .env or any existing PostgreSQL configuration.
            os.environ["POSTGRES_DB"] = TEST_DATABASE

        summary = verify_market_data(
            experiment_root=args.output_dir,
            symbol=args.symbol,
            live_client=client,
            replay_raw=args.replay_raw,
            outputsize=args.outputsize,
            write_gold=args.write_gold,
            confirm_test_db=args.confirm_test_db,
        )
    except (
        VerificationError,
        TwelveDataClientError,
        ValueError,
        OSError,
        RuntimeError,
    ):
        # Provider exceptions may include URLs containing API credentials.
        # Never print exception details or tracebacks in the live CLI.
        print(
            "FAIL: Verification did not complete; check local configuration and logs.",
            file=sys.stderr,
        )
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
