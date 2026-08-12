"""monthly 入口 CLI。"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd  # noqa: E402

from flow_dashboard.config import TIMEZONE  # noqa: E402
from flow_dashboard.pipeline import run_monthly  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--labels-path", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    if args.as_of:
        as_of = pd.Timestamp(args.as_of)
        if as_of.tzinfo is None:
            as_of = as_of.tz_localize(TIMEZONE)
    else:
        as_of = pd.Timestamp.now(tz=TIMEZONE)

    path = run_monthly(as_of=as_of, labels_path=args.labels_path)
    print(f"monthly published: {path}")


if __name__ == "__main__":
    main()
