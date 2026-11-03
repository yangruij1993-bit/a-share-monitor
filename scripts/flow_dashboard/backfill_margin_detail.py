#!/usr/bin/env python3
"""两融数据一次性回补：个股明细全量重拉 + 更早历史 + 汇总长历史。

背景：pull_margin_detail 修复分页前，缓存文件只含约 2000 行沪市代码
（深市含创业板 300/301、北交所整体缺失）；本脚本重拉全部已缓存日期并
回填更早历史。空数据日落空哨兵，避免日常运行反复探测非交易日。

用法（首跑约 10-20 分钟，可 nohup，可中断重跑）：
  .venv/bin/python3 scripts/flow_dashboard/backfill_margin_detail.py \
      [--start 2025-01-01] [--end 2026-10-12] [--repull-existing] \
      [--margin-start 2024-01-01] [--sleep 0.2]
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd

from flow_dashboard.config import CACHE_DIR, TIMEZONE

log = logging.getLogger(__name__)


def _pull_day_with_retry(day: str, attempts: int = 3) -> pd.DataFrame:
    from flow_dashboard.data.tushare_providers import pull_margin_detail

    last_err: Exception | None = None
    for i in range(attempts):
        try:
            return pull_margin_detail(day)
        except Exception as err:  # tushare 限频/网络抖动：退避重试
            last_err = err
            wait = 15 * (i + 1)
            log.warning("pull %s 失败(%s)，%ds 后重试", day, err, wait)
            time.sleep(wait)
    raise RuntimeError(f"{day} 重试 {attempts} 次仍失败") from last_err


def backfill_detail(start: pd.Timestamp, end: pd.Timestamp, *, repull: bool, sleep_s: float) -> None:
    from flow_dashboard.data.loaders import _annotate_margin_detail, _empty_with_audit
    from flow_dashboard.data.schema import AUDIT_COLUMNS

    days = pd.date_range(start, end)
    n_pulled = n_empty = n_skipped = 0
    for i, d in enumerate(days, start=1):
        day = d.strftime("%Y%m%d")
        cache_path = CACHE_DIR / f"margin_detail_{day}.parquet"
        if cache_path.exists() and not repull:
            n_skipped += 1
            continue
        fresh = _pull_day_with_retry(day)
        if fresh.empty:
            # 该日 19:00 发布时点已过才落空哨兵；未到 19:00 的空是"尚未发布"，
            # 落哨兵会永久阻断当晚 eod_preview 补拉（与 loader 同规则）
            day_publish = pd.to_datetime(day, format="%Y%m%d") + pd.Timedelta(hours=19)
            now_local = pd.Timestamp.now(tz=TIMEZONE).tz_localize(None)
            if now_local >= day_publish:
                pd.DataFrame(columns=list(AUDIT_COLUMNS)).to_parquet(cache_path)
            n_empty += 1
        else:
            annotated = _annotate_margin_detail(fresh, pd.Timestamp.now(tz=TIMEZONE))
            annotated.to_parquet(cache_path, index=False)
            n_pulled += 1
        if i % 25 == 0:
            log.info("detail 进度 %d/%d（拉取 %d 空日 %d 跳过 %d）",
                     i, len(days), n_pulled, n_empty, n_skipped)
        time.sleep(sleep_s)
    log.info("detail 完成：拉取 %d 天，空哨兵 %d 天，跳过 %d 天",
             n_pulled, n_empty, n_skipped)


def backfill_summary(start: pd.Timestamp, end: pd.Timestamp, as_of: pd.Timestamp) -> None:
    from flow_dashboard.data.loaders import load_margin

    df = load_margin(start=start, end=end, as_of=as_of)
    log.info("margin 汇总缓存覆盖 %s → %s（%d 行）",
             df["trade_date"].min().date(), df["trade_date"].max().date(), len(df))


def verify_chinext(end: pd.Timestamp) -> None:
    from flow_dashboard.indicators.margin import aggregate_chinext_margin

    frames = []
    for p in sorted(CACHE_DIR.glob("margin_detail_*.parquet")):
        day = pd.Timestamp(p.stem.split("_")[-1])
        if day > end:
            continue
        cached = pd.read_parquet(p)
        if not cached.empty:
            frames.append(cached[["trade_date", "ts_code", "rzye"]])
    if not frames:
        log.warning("无明细缓存可验证")
        return
    chinext = aggregate_chinext_margin(pd.concat(frames, ignore_index=True))
    log.info("创业板融资余额：%s → %s，最新 %d 亿元",
             chinext["trade_date"].min().date(), chinext["trade_date"].max().date(),
             chinext["chinext_rzye"].iloc[-1] / 1e8)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2025-01-01", help="个股明细回填起始日")
    parser.add_argument("--end", default=None, help="回填结束日（默认今天）")
    parser.add_argument("--repull-existing", action="store_true",
                        help="重拉已缓存日期（修复分页修复前的沪市-only 历史）")
    parser.add_argument("--margin-start", default="2024-01-01", help="汇总回填起始日")
    parser.add_argument("--sleep", type=float, default=0.2)
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    now = pd.Timestamp.now(tz=TIMEZONE)
    start = pd.Timestamp(args.start)
    end = pd.Timestamp(args.end) if args.end else now.tz_localize(None).normalize()

    log.info("回填个股两融明细 %s → %s（repull_existing=%s）",
             start.date(), end.date(), args.repull_existing)
    backfill_detail(start, end, repull=args.repull_existing, sleep_s=args.sleep)
    backfill_summary(pd.Timestamp(args.margin_start), end, now)
    verify_chinext(end)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
