"""daily_finalize 入口 CLI。"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd  # noqa: E402

from flow_dashboard.config import TIMEZONE  # noqa: E402
from flow_dashboard.pipeline import run_daily_finalize  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-date", required=True)
    parser.add_argument("--as-of", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    if args.as_of:
        as_of = pd.Timestamp(args.as_of)
        if as_of.tzinfo is None:
            as_of = as_of.tz_localize(TIMEZONE)
    else:
        as_of = pd.Timestamp.now(tz=TIMEZONE)

    path = run_daily_finalize(data_date=args.data_date, as_of=as_of)
    print(f"daily_finalize published: {path}")


if __name__ == "__main__":
    main()
