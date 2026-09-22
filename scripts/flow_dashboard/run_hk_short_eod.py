#!/usr/bin/env python3
"""launchd 入口：港股沽空 EOD（18:45）。港股休市日由 run_hk_short_eod 短路。"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from flow_dashboard.config import TIMEZONE


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", default=None, help="回放时点（默认 now，ISO 格式）")
    args = parser.parse_args()

    import pandas as pd

    if args.as_of:
        as_of = pd.Timestamp(args.as_of)
    else:
        as_of = pd.Timestamp.now(tz=str(TIMEZONE))

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    from flow_dashboard.hk_short_pipeline import run_hk_short_eod

    out = run_hk_short_eod(as_of=as_of)
    print(f"published: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
