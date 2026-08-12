"""Phase B pipeline 入口：intraday / eod_preview / daily_finalize / monthly。

run_intraday: 盘中（每 15 分钟），只用新浪；写 intraday_latest.html。
run_eod_preview: T 日 19:00+，Tushare 已可得，生成 partial 报告。
run_daily_finalize: T+1 09:30+，定稿 T 日报告。
run_monthly: 每月第一个交易日，公募代理（Phase C 关闭时仅刷新分类表）。
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from flow_dashboard.config import (
    TIMEZONE, OUTPUT_DIR, RUNNERS_LOCK,
    INTRADAY_OUTPUT,
)
from flow_dashboard.data.sina_providers import (
    fetch_futures_snapshot,
    fetch_snapshot,
)
from flow_dashboard.render.assembly import (
    acquire_runner_lock, publish_intraday, RunnerLockError,
)
from flow_dashboard.render.panels_basis import render_basis_panel
from flow_dashboard.render.theme import build_html_skeleton

log = logging.getLogger(__name__)


def run_intraday(
    *,
    as_of: pd.Timestamp,
    output_dir: Path | str | None = None,
    lock_path: Path | str | None = None,
    force: bool = False,
) -> Path:
    """盘中入口：拉新浪 IC/IM 期货 + 现货指数，渲染基差预览页。

    per spec §3.3: 只写 intraday_latest.html，不写归档。
    per spec §7.4: 上游失败时不计算基差，全行标 stale。
    per spec §3.3: 无法获取锁时记录 skipped_due_to_lock，保留上一份 intraday_latest.html。
    """
    output_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    lock_path = Path(lock_path) if lock_path else RUNNERS_LOCK
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        with acquire_runner_lock(lock_path):
            return _run_intraday_inner(as_of, output_dir)
    except RunnerLockError:
        log.warning("intraday skipped_due_to_lock at %s", as_of)
        return output_dir / "intraday_latest.html"


def _run_intraday_inner(as_of: pd.Timestamp, output_dir: Path) -> Path:
    ic_batch = fetch_futures_snapshot("IC", observed_at=as_of)
    im_batch = fetch_futures_snapshot("IM", observed_at=as_of)
    spot_batch = fetch_snapshot(["sh000905", "sh000852"], observed_at=as_of)

    failed = bool(ic_batch.failures or im_batch.failures or spot_batch.failures)

    if failed:
        body = '<div class="stale">⚠️ 盘中行情数据不可得（stale）— 已保留上一份成功快照，不计算新基差</div>'
        full = build_html_skeleton(
            title="A 股流动性 — 盘中预览（stale）",
            body=body,
            data_date=as_of.strftime("%Y-%m-%d"),
            last_success_at=as_of.strftime("%Y-%m-%d %H:%M CST"),
            footer="市场观察，非交易建议。盘中预览仅来自新浪公开行情。",
        )
        return publish_intraday(output_dir=output_dir, full_html=full)

    from flow_dashboard.indicators.basis import compute_basis

    ic_df = _quotes_to_fut_df(ic_batch)
    im_df = _quotes_to_fut_df(im_batch)
    spot_df = _quotes_to_spot_df(spot_batch)

    basis_ic = compute_basis(ic_df, spot_df, spot_map={"IC": "000905.SH"},
                             max_quote_skew_seconds=None)
    basis_im = compute_basis(im_df, spot_df, spot_map={"IM": "000852.SH"},
                             max_quote_skew_seconds=None)

    basis_html = render_basis_panel(
        ic_df=basis_ic, im_df=basis_im,
        data_date=as_of.strftime("%Y-%m-%d"),
        coverage=1.0 if not basis_ic.empty else None,
        last_success_at=as_of.strftime("%H:%M"),
        layer="intraday",
    )

    full = build_html_skeleton(
        title="A 股流动性 — 盘中预览",
        body=basis_html,
        data_date=as_of.strftime("%Y-%m-%d"),
        last_success_at=as_of.strftime("%Y-%m-%d %H:%M CST"),
        footer="市场观察，非交易建议。盘中预览仅来自新浪公开行情；非交易信号。",
    )
    return publish_intraday(output_dir=output_dir, full_html=full)


def _quotes_to_fut_df(batch) -> pd.DataFrame:
    rows = []
    for q in batch.quotes:
        rows.append({
            "ts_code": q["provider_code"].replace("sina_fut_", ""),
            "trade_date": pd.Timestamp(batch.observed_at).normalize(),
            "settle": q.get("settlement"),
            "close": q.get("last_price"),
            "pre_settle": q.get("pre_close"),
            "delist_date": pd.Timestamp("2026-08-21", tz="Asia/Shanghai"),  # 占位，Phase B 不接 fut_basic
        })
    return pd.DataFrame(rows)


def _quotes_to_spot_df(batch) -> pd.DataFrame:
    rows = []
    for q in batch.quotes:
        ts_code = _spot_provider_to_ts(q["provider_code"])
        rows.append({
            "ts_code": ts_code,
            "trade_date": pd.Timestamp(batch.observed_at).normalize(),
            "close": q.get("last_price"),
        })
    return pd.DataFrame(rows)


def _spot_provider_to_ts(provider_code: str) -> str:
    mapping = {"sh000905": "000905.SH", "sh000852": "000852.SH"}
    return mapping.get(provider_code, provider_code)


# 后续 task 实现：
def run_eod_preview(*, data_date, as_of, force: bool = False) -> str:
    raise NotImplementedError


def run_daily_finalize(*, data_date, as_of, force: bool = False) -> str:
    raise NotImplementedError


def run_monthly(*, as_of, force: bool = False) -> str:
    raise NotImplementedError
