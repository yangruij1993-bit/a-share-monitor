"""CLI 入口：从 etf_pit_labels.csv 取 ts_code 列表，轮询一次 etf_share_size。

示例:
    python scripts/flow_dashboard/poll_etf_share_size.py --trade-date 20260811 \
        --labels data/flow_dashboard/phase_a_evidence/etf_pit_labels.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd  # noqa: E402

from flow_dashboard.config import EVIDENCE_DIR  # noqa: E402
from flow_dashboard.data.pit_labels import load_pit_labels  # noqa: E402
from flow_dashboard.phase_a.poll_etf_share import poll_once  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trade-date", required=True)
    parser.add_argument(
        "--labels",
        default=str(EVIDENCE_DIR / "etf_pit_labels.csv"),
        help="PIT 标签表路径；将取其中所有 ts_code 作为轮询目标",
    )
    parser.add_argument(
        "--output-dir",
        default=str(EVIDENCE_DIR / "share_polling"),
    )
    args = parser.parse_args()

    labels = load_pit_labels(args.labels)
    codes = sorted(set(labels["ts_code"]))
    summary = poll_once(codes=codes, trade_date=args.trade_date, output_dir=args.output_dir)
    print(pd.DataFrame([summary]).to_string(index=False))


if __name__ == "__main__":
    main()
