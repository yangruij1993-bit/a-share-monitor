"""daily_finalize 入口 CLI。"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd

from flow_dashboard.config import OUTPUT_DIR, TIMEZONE
from flow_dashboard.pipeline import run_daily_finalize
from flow_dashboard.schedule import should_retry_finalize


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-date", default=None)
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--retry-if-partial", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    if args.as_of:
        as_of = pd.Timestamp(args.as_of)
        if as_of.tzinfo is None:
            as_of = as_of.tz_localize(TIMEZONE)
    else:
        as_of = pd.Timestamp.now(tz=TIMEZONE)

    data_date = args.data_date or (as_of - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
    if args.retry_if_partial and not should_retry_finalize(OUTPUT_DIR, data_date, as_of):
        print(f"daily_finalize skipped: {data_date} morning report complete")
        return
    path = run_daily_finalize(data_date=data_date, as_of=as_of)
    print(f"daily_finalize published: {path}")


if __name__ == "__main__":
    main()
