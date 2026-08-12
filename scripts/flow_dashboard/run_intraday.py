"""盘中入口 CLI。

用法：
    python scripts/flow_dashboard/run_intraday.py [--as-of "2026-08-12 14:30"]
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd  # noqa: E402

from flow_dashboard.config import TIMEZONE  # noqa: E402
from flow_dashboard.pipeline import run_intraday  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", default=None,
                        help="ISO timestamp with tz; default = now")
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    if args.as_of:
        ts = pd.Timestamp(args.as_of)
        as_of = ts.tz_convert(TIMEZONE) if ts.tzinfo else pd.Timestamp(args.as_of, tz=TIMEZONE)
    else:
        as_of = pd.Timestamp.now(tz=TIMEZONE)

    output_dir = Path(args.output_dir) if args.output_dir else None
    path = run_intraday(as_of=as_of, output_dir=output_dir)
    print(f"intraday published: {path}")


if __name__ == "__main__":
    main()
