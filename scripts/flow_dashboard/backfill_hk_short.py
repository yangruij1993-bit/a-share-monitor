#!/usr/bin/env python3
"""港股沽空一次性回补：EM 卖空历史 / HKEX 窗口 / SFC 周报 / K线 / 总股本 / LOS。

用法（首日，数小时级，建议 nohup）：
  nohup .venv/bin/python3 scripts/flow_dashboard/backfill_hk_short.py \
      [--as-of '2026-09-18 19:00'] [cache_dir] &
loader 缓存感知，可中断重跑（已入库增量自动跳过）。
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd

from flow_dashboard.config import (
    HK_INDEX_SECIDS,
    HK_SHORT_CACHE_DIR,
    HK_WATCH_LIST,
    _hk_secid,
)

log = logging.getLogger(__name__)


def _loaders():
    from flow_dashboard.data.hk_short.loaders import (
        load_em_sellshort,
        load_etf_master,
        load_hk_kline,
        load_hkex_dayquot,
        load_sfc_weekly,
        load_total_shares,
    )

    return {
        "em_day": load_em_sellshort,
        "em_watch": load_em_sellshort,
        "hkex": load_hkex_dayquot,
        "sfc": load_sfc_weekly,
        "kline": load_hk_kline,
        "shares": load_total_shares,
        "los": load_etf_master,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--em-days", type=int, default=400)
    parser.add_argument("--hkex-days", type=int, default=70)
    parser.add_argument("--sfc-weeks", type=int, default=12)
    parser.add_argument("--kline-days", type=int, default=400)
    parser.add_argument("cache_dir", nargs="?", default=None)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    as_of = (
        pd.Timestamp(args.as_of, tz="Asia/Shanghai")
        if args.as_of
        else pd.Timestamp.now(tz="Asia/Shanghai")
    )
    cache_dir = Path(args.cache_dir) if args.cache_dir else HK_SHORT_CACHE_DIR

    watch_codes = [c for _, c in HK_WATCH_LIST]
    secids = list(HK_INDEX_SECIDS.values()) + [_hk_secid(c) for c in watch_codes]

    L = _loaders()
    em_start = as_of.tz_localize(None).normalize() - pd.Timedelta(days=args.em_days)
    log.info("backfill EM sellshort %s 起（首跑约 1-2 小时）", em_start.date())
    L["em_day"](as_of=as_of, start=em_start, cache_dir=cache_dir)
    L["em_watch"](as_of=as_of, codes=watch_codes, start=em_start, cache_dir=cache_dir)
    hkex_start = as_of.tz_localize(None).normalize() - pd.Timedelta(days=args.hkex_days)
    log.info("backfill HKEX dayquot %s 起（每日 26MB）", hkex_start.date())
    L["hkex"](as_of=as_of, start=hkex_start, cache_dir=cache_dir)
    log.info("backfill SFC %d 周", args.sfc_weeks)
    L["sfc"](as_of=as_of, weeks=args.sfc_weeks, cache_dir=cache_dir)
    kline_start = as_of.tz_localize(None).normalize() - pd.Timedelta(
        days=args.kline_days
    )
    log.info("backfill kline %s 起", kline_start.date())
    L["kline"](as_of=as_of, secids=secids, start=kline_start, cache_dir=cache_dir)
    L["shares"](as_of=as_of, codes=watch_codes, cache_dir=cache_dir)
    L["los"](as_of=as_of, cache_dir=cache_dir)
    log.info("backfill done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
