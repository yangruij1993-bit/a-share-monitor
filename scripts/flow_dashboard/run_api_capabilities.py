"""生成 api_capabilities.yaml 到 data/flow_dashboard/phase_a_evidence/。

跑 live 样本时需要 ASHARE_FLOW_TUSHARE_TOKEN 与网络访问。
"""
from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from flow_dashboard.config import EVIDENCE_DIR, ensure_dirs, TIMEZONE  # noqa: E402
from flow_dashboard.phase_a.api_capabilities import build_capabilities  # noqa: E402


def _live_sample() -> dict:
    """每个 endpoint 跑一次小样本，记录实际行数、最新日期、首次观测时间。"""
    from flow_dashboard.data.tushare_providers import (
        pull_fund_basic, pull_etf_share_size, pull_fund_nav, pull_fund_daily,
        pull_margin, pull_fut_basic, pull_fut_daily, pull_index_daily,
    )
    from flow_dashboard.data.sina_client import fetch_futures_node, fetch_spot_indices

    live = {"tushare": {}, "sina": {}}
    now = pd.Timestamp.now(tz=TIMEZONE)
    sample_codes = ["510050.SH", "510300.SH", "510500.SH", "159915.SZ"]

    def _record(area, name, df_or_payload):
        if isinstance(df_or_payload, pd.DataFrame):
            live[area][name] = {
                "sample_rows": int(len(df_or_payload)),
                "first_observed_at": now.isoformat(),
                "columns_observed": list(df_or_payload.columns),
            }
        else:
            live[area][name] = {"error": str(df_or_payload), "first_observed_at": now.isoformat()}

    for name, fn, args in [
        ("fund_basic", pull_fund_basic, {"market": "E"}),
        ("etf_share_size", pull_etf_share_size,
         {"codes": sample_codes, "start_date": "20260807", "end_date": "20260812"}),
        ("fund_nav", pull_fund_nav,
         {"codes": ["510050.SH"], "start_date": "20260807", "end_date": "20260812"}),
        ("fund_daily", pull_fund_daily,
         {"codes": ["510050.SH"], "start_date": "20260807", "end_date": "20260812"}),
        ("margin", pull_margin, {"start_date": "20260811", "end_date": "20260811"}),
        ("fut_basic", pull_fut_basic, {"exchange": "CFFEX", "fut_code": "IC"}),
        ("fut_daily", pull_fut_daily,
         {"ts_code": "IC2608.CFX", "start_date": "20260807", "end_date": "20260812"}),
        ("index_daily", pull_index_daily,
         {"ts_code": "000905.SH", "start_date": "20260807", "end_date": "20260812"}),
    ]:
        try:
            df = fn(**args)
            _record("tushare", name, df)
        except Exception as exc:
            print(f"[warn] tushare {name} failed: {exc}")
            traceback.print_exc()
            _record("tushare", name, exc)

    try:
        df = fetch_futures_node("IC")
        _record("sina", "fetch_futures_node_IC", df)
    except Exception as exc:
        _record("sina", "fetch_futures_node_IC", exc)
    try:
        df = fetch_spot_indices(["sh000905", "sh000852"])
        _record("sina", "fetch_spot_indices", df)
    except Exception as exc:
        _record("sina", "fetch_spot_indices", exc)
    return live


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true",
                        help="跑真实小样本并合并到 yaml（需要 token + 网络）")
    parser.add_argument("--output", default=str(EVIDENCE_DIR / "api_capabilities.yaml"))
    args = parser.parse_args()

    ensure_dirs()
    caps = build_capabilities()
    if args.live:
        caps["live_sample"] = _live_sample()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(caps, allow_unicode=True, sort_keys=False, default_flow_style=False))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
