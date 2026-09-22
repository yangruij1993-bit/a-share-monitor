"""港股沽空 EOD runner：18:45 触发，抓增量 + 整页重渲染（含 A股 tab）。

设计 §7：
- 与 A股 runner 共用 RUNNERS_LOCK；本模块持有锁后直接调用
  _run_eod_preview_inner（其内部不再取锁——fcntl 非阻塞锁嵌套会死锁）
- 休市日短路（除非 SFC 最新周报已超宽限期，仍需补抓）
- report_date = as_of 当日或之前最近的香港交易日
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from flow_dashboard.config import (
    HK_INDEX_SECIDS,
    HK_WATCH_LIST,
    OUTPUT_DIR,
    RUNNERS_LOCK,
)
from flow_dashboard.data.hk_short.hk_calendar import (
    is_hk_trading_day,
    latest_trading_day_on_or_before,
)
from flow_dashboard.render.assembly import RunnerLockError, acquire_runner_lock

log = logging.getLogger(__name__)


def _sfc_missing(*, as_of, cache_dir=None) -> bool:
    """最新已完成交易周的 SFC 报告是否已超宽限期（休市日短路例外的判据）。"""
    from flow_dashboard.data.hk_short.loaders import load_sfc_weekly
    from flow_dashboard.indicators import hk_short_state as state

    cached = load_sfc_weekly(as_of=as_of, allow_fetch=False, cache_dir=cache_dir)
    latest = pd.to_datetime(cached["position_date"]).max() if not cached.empty else None
    return state.sfc_is_pending(latest_cached_pd=latest, as_of=as_of)


def _fetch_hk_increments(as_of) -> None:
    """抓全部港股增量（单源失败只告警，不阻塞发布，设计 §5）。"""
    from flow_dashboard.data.hk_short.loaders import (
        load_em_sellshort,
        load_etf_master,
        load_hk_kline,
        load_hkex_dayquot,
        load_sfc_weekly,
        load_total_shares,
    )

    load_em_sellshort(as_of=as_of)  # 全市场逐日（full 标记）
    load_em_sellshort(as_of=as_of, codes=[c for _, c in HK_WATCH_LIST])
    load_hkex_dayquot(as_of=as_of)
    load_sfc_weekly(as_of=as_of)
    secids = list(HK_INDEX_SECIDS.values()) + [
        f"116.{c.split('.')[0].zfill(5)}" for _, c in HK_WATCH_LIST
    ]
    load_hk_kline(as_of=as_of, secids=secids)
    load_total_shares(as_of=as_of, codes=[c for _, c in HK_WATCH_LIST])
    load_etf_master(as_of=as_of)


def run_hk_short_eod(
    *,
    as_of: pd.Timestamp,
    output_dir: Path | str | None = None,
    lock_path: Path | str | None = None,
) -> Path:
    output_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    lock_path = Path(lock_path) if lock_path else RUNNERS_LOCK
    output_dir.mkdir(parents=True, exist_ok=True)

    ts = pd.Timestamp(as_of)
    ts = ts.tz_convert("Asia/Shanghai").tz_localize(None) if ts.tzinfo else ts
    if not is_hk_trading_day(ts) and not _sfc_missing(as_of=as_of):
        log.info("hk_short_eod skipped: %s 非香港交易日且 SFC 无逾期", ts.date())
        return output_dir / "latest.html"

    try:
        with acquire_runner_lock(lock_path):
            _fetch_hk_increments(as_of)
            from flow_dashboard.pipeline import _run_eod_preview_inner

            report_date = latest_trading_day_on_or_before(ts).strftime("%Y-%m-%d")
            return _run_eod_preview_inner(
                report_date, as_of, output_dir, universe=None, report_date=report_date
            )
    except (RunnerLockError, BlockingIOError):
        # BlockingIOError：acquire_runner_lock timeout=0 时 flock 冲突的原始
        # 异常（同进程/跨进程持锁均可能出现）；二者语义相同 → 保留现有页面。
        log.warning("hk_short_eod skipped_due_to_lock at %s", as_of)
        return output_dir / "latest.html"
