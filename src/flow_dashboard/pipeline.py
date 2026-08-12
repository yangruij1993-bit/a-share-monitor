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

    failed = bool(
        ic_batch.failures or im_batch.failures or spot_batch.failures
        or not ic_batch.quotes or not im_batch.quotes or not spot_batch.quotes
    )

    if failed:
        body = (
            '<div class="stale">⚠️ 盘中行情数据不可得（stale）— '
            "已保留上一份成功快照，不计算新基差。"
            "请检查：新浪网络/IC/IM/现货 endpoint、runners.lock 占用、launchd 日志。</div>"
        )
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


def run_eod_preview(
    *,
    data_date: str,
    as_of: pd.Timestamp,
    output_dir: Path | str | None = None,
    lock_path: Path | str | None = None,
    universe: list[str] | None = None,
    force: bool = False,
) -> Path:
    """T 日 19:00+ 的 partial 预发布。

    per spec §3.1 + §3.5 共通验收:
    - ETF 份额未入库时 HTML 头部标 partial
    - 不将 T-1 标 T
    - 输出 report_<data_date>_vNN.html + 更新 latest symlink
    """
    output_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    lock_path = Path(lock_path) if lock_path else RUNNERS_LOCK
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        with acquire_runner_lock(lock_path):
            return _run_eod_preview_inner(data_date, as_of, output_dir, universe)
    except RunnerLockError:
        log.warning("eod_preview skipped_due_to_lock at %s", as_of)
        return output_dir / f"report_{data_date}_v01.html"


def _run_eod_preview_inner(
    data_date: str, as_of: pd.Timestamp, output_dir: Path,
    universe: list[str] | None,
) -> Path:
    # 与 render/panels_*.py 中 div_id 保持一致；下游 manifest → panel 映射按此列表对齐。
    panel_ids = [
        "panel-huijin-broad-daily",
        "panel-tech-tmt-daily",
        "panel-total-market-daily",
        "panel-broad-daily",
        "panel-industry-theme-daily",
        "panel-category-cumulative-daily",
        "panel-cycle-daily",
        "panel-cycle-cumulative-daily",
        "panel-top15-daily",
        "panel-broad-weekly",
        "panel-industry-weekly",
        "panel-category-weekly",
        "panel-monthly-total",
        "panel-margin-exchange",
        "panel-basis",
    ]

    from flow_dashboard.data.pit_labels import load_pit_labels
    from flow_dashboard.indicators.etf_flow import compute_etf_flow
    from flow_dashboard.indicators.margin import (
        aggregate_market_margin, compute_weekly_change,
    )
    from flow_dashboard.indicators.basis import compute_basis
    from flow_dashboard.render.panels_daily import (
        render_huijin_broad_daily, render_tech_tmt_daily,
        render_total_market_daily, render_broad_daily,
        render_industry_theme_daily, render_category_cumulative_daily,
        render_cycle_daily, render_cycle_cumulative_daily,
        render_top15_etf_daily,
    )
    from flow_dashboard.render.panels_weekly import (
        render_broad_weekly, render_industry_theme_weekly,
        render_category_cumulative_weekly, render_monthly_total,
    )
    from flow_dashboard.render.panels_margin import render_margin_exchange_panel
    from flow_dashboard.render.panels_basis import render_basis_panel
    from flow_dashboard.render.assembly import publish_archive

    labels_path = Path("data/flow_dashboard/phase_a_evidence/etf_pit_labels.csv")
    if labels_path.exists():
        labels = load_pit_labels(str(labels_path))
        codes = universe or sorted(set(labels["ts_code"]))
    else:
        labels = pd.DataFrame()
        codes = universe or ["510050.SH", "510300.SH", "510500.SH", "159915.SZ"]

    start = pd.Timestamp(data_date) - pd.Timedelta(days=90)
    end = pd.Timestamp(data_date)

    etf_share = _load_etf_share_for_pipeline(codes, start, end, as_of)
    margin_df = _load_margin_for_pipeline(start, end, as_of)
    ic_fut = _load_fut_daily_for_pipeline("IC2608.CFX", start, end, as_of)
    im_fut = _load_fut_daily_for_pipeline("IM2608.CFX", start, end, as_of)
    spot_500 = _load_index_daily_for_pipeline("000905.SH", start, end, as_of)
    spot_1000 = _load_index_daily_for_pipeline("000852.SH", start, end, as_of)

    is_partial = (
        etf_share.empty
        or "trade_date" not in etf_share.columns
        or pd.isna(etf_share["trade_date"].max())
        or etf_share["trade_date"].max() < end
    )

    fund_nav = _load_fund_nav_for_pipeline(codes=codes, start=start, end=end, as_of=as_of)
    if not etf_share.empty and not fund_nav.empty:
        merged = etf_share.merge(
            fund_nav[["ts_code", "nav_date", "unit_nav"]].rename(
                columns={"nav_date": "trade_date"}
            ),
            on=["ts_code", "trade_date"], how="left",
        )
    else:
        merged = etf_share.copy()
        if "unit_nav" not in merged.columns:
            merged["unit_nav"] = pd.NA

    if not merged.empty:
        if "dimension" not in merged.columns or "label" not in merged.columns:
            if not labels.empty:
                merged = merged.merge(
                    labels[["ts_code", "dimension", "label"]].drop_duplicates("ts_code"),
                    on="ts_code", how="left",
                )
            else:
                merged["dimension"] = "ownership"
                merged["label"] = "uncategorized"

    flow = compute_etf_flow(merged) if not merged.empty else merged

    coverage = 1.0 if not flow.empty else None
    kwargs = dict(
        data_date=data_date,
        coverage=coverage,
        last_success_at=as_of.strftime("%Y-%m-%d %H:%M"),
    )

    panels: list[str] = []
    panels.append(render_huijin_broad_daily(flow, **kwargs))
    panels.append(render_tech_tmt_daily(flow, **kwargs))
    panels.append(render_total_market_daily(flow, **kwargs))
    panels.append(render_broad_daily(flow, **kwargs))
    panels.append(render_industry_theme_daily(flow, **kwargs))
    panels.append(render_category_cumulative_daily(flow, **kwargs))
    panels.append(render_cycle_daily(flow, **kwargs))
    panels.append(render_cycle_cumulative_daily(flow, **kwargs))
    panels.append(render_top15_etf_daily(flow, **kwargs))

    from flow_dashboard.indicators.flow_aggregation import (
        aggregate_weekly_flow, aggregate_monthly_flow,
    )
    if not flow.empty:
        weekly = aggregate_weekly_flow(flow)
        weekly = weekly.rename(columns={"week_start": "period_start"})
    else:
        weekly = pd.DataFrame()
    w_kwargs = dict(
        data_date=data_date,
        coverage=0.95 if not weekly.empty else None,
        last_success_at=as_of.strftime("%Y-%m-%d %H:%M"),
    )
    panels.append(render_broad_weekly(weekly, **w_kwargs))
    panels.append(render_industry_theme_weekly(weekly, **w_kwargs))
    panels.append(render_category_cumulative_weekly(weekly, **w_kwargs))
    if not flow.empty:
        monthly = aggregate_monthly_flow(flow)
    else:
        monthly = pd.DataFrame()
    panels.append(render_monthly_total(monthly, **w_kwargs))

    if not margin_df.empty:
        m = aggregate_market_margin(margin_df, market_scope=None)
        m = compute_weekly_change(m)
    else:
        m = pd.DataFrame()
    m_kwargs = dict(
        data_date=data_date,
        coverage=1.0 if not m.empty else None,
        last_success_at=as_of_format(as_of),
        reconciliation_tolerance=None,
    )
    panels.append(render_margin_exchange_panel(m, **m_kwargs))

    spot_df = pd.concat([spot_500, spot_1000], ignore_index=True)
    if not ic_fut.empty and not im_fut.empty:
        basis_ic = compute_basis(ic_fut, spot_df, spot_map={"IC": "000905.SH"},
                                 max_quote_skew_seconds=None)
        basis_im = compute_basis(im_fut, spot_df, spot_map={"IM": "000852.SH"},
                                 max_quote_skew_seconds=None)
    else:
        basis_ic = pd.DataFrame()
        basis_im = pd.DataFrame()
    panels.append(render_basis_panel(
        ic_df=basis_ic, im_df=basis_im,
        data_date=data_date,
        coverage=1.0 if not basis_ic.empty else None,
        last_success_at=as_of_format(as_of),
        layer="eod",
    ))

    body = "\n".join(panels)

    title_suffix = " (partial)" if is_partial else ""
    full_html = build_html_skeleton(
        title=f"A 股流动性日报 — {data_date}{title_suffix}",
        body=body,
        data_date=data_date,
        last_success_at=as_of.strftime("%Y-%m-%d %H:%M CST"),
        footer="市场观察，非交易建议。" + (
            " 本期为 partial：ETF 份额数据尚未完整入库。" if is_partial else ""
        ),
    )

    _, archive_path, _, _ = publish_archive(
        output_dir=output_dir, data_date=data_date,
        html_body=body,
        manifest_payload={
            "panels": panel_ids,
            "source_versions": {
                "etf_share": "etf_share_size_v1",
                "margin": "margin_v1",
                "fut_daily": "fut_daily_v1",
                "index_daily": "index_daily_v1",
            },
            "panel_status": {"is_partial": is_partial},
        },
        full_html=full_html,
    )
    return archive_path


def as_of_format(as_of: pd.Timestamp) -> str:
    return as_of.strftime("%Y-%m-%d %H:%M")


def _load_etf_share_for_pipeline(codes, start, end, as_of):
    from flow_dashboard.data.loaders import load_etf_share
    return load_etf_share(codes=codes, start=start, end=end, as_of=as_of)


def _load_margin_for_pipeline(start, end, as_of):
    from flow_dashboard.data.loaders import load_margin
    return load_margin(start=start, end=end, as_of=as_of)


def _load_fut_daily_for_pipeline(ts_code, start, end, as_of):
    from flow_dashboard.data.loaders import load_fut_daily
    return load_fut_daily(ts_code=ts_code, start=start, end=end, as_of=as_of)


def _load_index_daily_for_pipeline(ts_code, start, end, as_of):
    from flow_dashboard.data.loaders import load_index_daily
    return load_index_daily(ts_code=ts_code, start=start, end=end, as_of=as_of)


def _load_fund_nav_for_pipeline(codes, start, end, as_of):
    from flow_dashboard.data.loaders import load_fund_nav
    return load_fund_nav(codes=codes, start=start, end=end, as_of=as_of)


# 后续 task 实现：
def run_daily_finalize(*, data_date, as_of, force: bool = False) -> str:
    raise NotImplementedError


def run_monthly(*, as_of, force: bool = False) -> str:
    raise NotImplementedError
