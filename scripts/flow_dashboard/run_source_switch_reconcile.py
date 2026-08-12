"""生成源切换对账报告 CSV。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd  # noqa: E402

from flow_dashboard.config import EVIDENCE_DIR, ensure_dirs  # noqa: E402
from flow_dashboard.data.pit_labels import load_pit_labels  # noqa: E402
from flow_dashboard.data.tushare_providers import pull_etf_share_size  # noqa: E402
from flow_dashboard.phase_a.source_switch_reconcile import (  # noqa: E402
    fetch_fund_share,
    reconcile_share_sources,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", default="20260101")
    parser.add_argument("--end-date", default="20260812")
    parser.add_argument("--labels", default=str(EVIDENCE_DIR / "etf_pit_labels.csv"))
    parser.add_argument("--output", default=str(EVIDENCE_DIR / "source_switch_reconcile.csv"))
    parser.add_argument("--tolerance-pct", type=float, default=0.01)
    args = parser.parse_args()

    ensure_dirs()
    labels = load_pit_labels(args.labels)
    codes = sorted(set(labels["ts_code"]))

    etf = pull_etf_share_size(codes=codes, start_date=args.start_date, end_date=args.end_date)
    fund = fetch_fund_share(codes=codes, start_date=args.start_date, end_date=args.end_date)
    report = reconcile_share_sources(etf, fund, tolerance_pct=args.tolerance_pct)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"wrote {args.output} rows={len(report)}")
    print(report["flag"].value_counts().to_string())


if __name__ == "__main__":
    main()
