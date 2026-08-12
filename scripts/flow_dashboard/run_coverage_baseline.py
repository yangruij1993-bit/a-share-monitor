"""生成覆盖率基线 CSV：用 PIT 标签作为 universe，按 etf_share_size 实测计算。"""
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
from flow_dashboard.phase_a.coverage_baseline import compute_coverage_series  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", default="20260101")
    parser.add_argument("--end-date", default="20260812")
    parser.add_argument("--labels", default=str(EVIDENCE_DIR / "etf_pit_labels.csv"))
    parser.add_argument("--output", default=str(EVIDENCE_DIR / "coverage_baseline.csv"))
    args = parser.parse_args()

    ensure_dirs()
    labels = load_pit_labels(args.labels)
    universe = sorted(set(labels["ts_code"]))

    etf = pull_etf_share_size(codes=universe, start_date=args.start_date, end_date=args.end_date)
    if etf.empty:
        print("[warn] etf_share_size empty; nothing to baseline")
        return

    flow_rows = []
    for _, label_row in labels.iterrows():
        dim = label_row["dimension"]
        lab = label_row["label"]
        ts_code = label_row["ts_code"]
        sub = etf[etf["ts_code"] == ts_code]
        for _, s in sub.iterrows():
            flow_rows.append({
                "ts_code": ts_code, "trade_date": s["trade_date"],
                "dimension": dim, "label": lab,
                "share_in_shares": s["share_in_shares"],
                "total_size_cny": s["total_size"] * 10000,
            })
    flow = pd.DataFrame(flow_rows)
    if flow.empty:
        print("[warn] flow empty; check label/etf code alignment")
        return
    out = compute_coverage_series(flow, universe=universe)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"wrote {args.output} rows={len(out)}")
    print(out.tail(10).to_string(index=False))


if __name__ == "__main__":
    main()
