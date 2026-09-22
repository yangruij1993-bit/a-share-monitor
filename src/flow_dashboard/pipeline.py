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
    OUTPUT_DIR,
    RUNNERS_LOCK,
)
from flow_dashboard.data.sina_providers import (
    fetch_futures_snapshot,
    fetch_snapshot,
)
from flow_dashboard.render.assembly import (
    RunnerLockError,
    acquire_runner_lock,
    publish_intraday,
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
        ic_batch.failures
        or im_batch.failures
        or spot_batch.failures
        or not ic_batch.quotes
        or not im_batch.quotes
        or not spot_batch.quotes
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

    basis_ic = compute_basis(
        ic_df, spot_df, spot_map={"IC": "000905.SH"}, max_quote_skew_seconds=None
    )
    basis_im = compute_basis(
        im_df, spot_df, spot_map={"IM": "000852.SH"}, max_quote_skew_seconds=None
    )

    basis_html = render_basis_panel(
        ic_df=basis_ic,
        im_df=basis_im,
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
        rows.append(
            {
                "ts_code": q["provider_code"].replace("sina_fut_", ""),
                "trade_date": pd.Timestamp(batch.observed_at).normalize(),
                "settle": q.get("settlement"),
                "close": q.get("last_price"),
                "pre_settle": q.get("pre_close"),
                "delist_date": pd.Timestamp(
                    "2026-08-21", tz="Asia/Shanghai"
                ),  # 占位，Phase B 不接 fut_basic
            }
        )
    return pd.DataFrame(rows)


def _quotes_to_spot_df(batch) -> pd.DataFrame:
    rows = []
    for q in batch.quotes:
        ts_code = _spot_provider_to_ts(q["provider_code"])
        rows.append(
            {
                "ts_code": ts_code,
                "trade_date": pd.Timestamp(batch.observed_at).normalize(),
                "close": q.get("last_price"),
            }
        )
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
    data_date: str,
    as_of: pd.Timestamp,
    output_dir: Path,
    universe: list[str] | None,
    report_date: str | None = None,
) -> Path:
    # report_date：本次发布的报告日期（归档名/标题/skeleton 用）。
    # A股 runner 调用时缺省 = data_date（行为不变）；港股 runner 触发补发时
    # 传自己的触发日期，A股数据日期单独进 manifest（设计 §7 双日期）。
    report_date = report_date or data_date
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
        "panel-margin-industry-heatmap",  # NEW (Phase C)
        # NEW (HK short) — 港股 tab 四面板
        "panel-hk-conclusion",
        "panel-hk-market",
        "panel-hk-watch",
        "panel-hk-top20",
    ]

    from flow_dashboard.data.pit_labels import load_pit_labels
    from flow_dashboard.indicators.basis import compute_basis, tenor_contracts
    from flow_dashboard.indicators.etf_flow import compute_etf_flow
    from flow_dashboard.indicators.margin import (
        aggregate_margin_by_industry,
        aggregate_market_margin,
        compute_net_margin_change,
        compute_weekly_change,
    )
    from flow_dashboard.render.assembly import publish_archive
    from flow_dashboard.render.panels_basis import render_basis_panel
    from flow_dashboard.render.panels_daily import (
        render_broad_daily,
        render_category_cumulative_daily,
        render_cycle_cumulative_daily,
        render_cycle_daily,
        render_huijin_broad_daily,
        render_industry_theme_daily,
        render_tech_tmt_daily,
        render_top15_etf_daily,
        render_total_market_daily,
    )
    from flow_dashboard.render.panels_margin import render_margin_exchange_panel
    from flow_dashboard.render.panels_margin_industry import (
        render_margin_industry_heatmap,
    )
    from flow_dashboard.render.panels_summary import render_summary_section
    from flow_dashboard.render.panels_weekly import (
        render_broad_weekly,
        render_category_cumulative_weekly,
        render_industry_theme_weekly,
        render_monthly_total,
    )
    from flow_dashboard.render.theme import render_section_band

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
    # IC/IM 三档合约（当月/当季/下季），到期自动滚换；每档单独成线不拼接
    tenors = tenor_contracts(pd.Timestamp(data_date))
    ic_fut = _load_fut_daily_multi(
        [f"IC{ym}.CFX" for ym, _label in tenors], start, end, as_of
    )
    im_fut = _load_fut_daily_multi(
        [f"IM{ym}.CFX" for ym, _label in tenors], start, end, as_of
    )
    spot_500 = _load_index_daily_for_pipeline("000905.SH", start, end, as_of)
    spot_1000 = _load_index_daily_for_pipeline("000852.SH", start, end, as_of)

    is_partial = (
        etf_share.empty
        or "trade_date" not in etf_share.columns
        or pd.isna(etf_share["trade_date"].max())
        or etf_share["trade_date"].max() < end
    )

    fund_nav = _load_fund_nav_for_pipeline(
        codes=codes, start=start, end=end, as_of=as_of
    )
    if not etf_share.empty and not fund_nav.empty:
        merged = etf_share.merge(
            fund_nav[["ts_code", "nav_date", "unit_nav"]].rename(
                columns={"nav_date": "trade_date"}
            ),
            on=["ts_code", "trade_date"],
            how="left",
        )
    else:
        merged = etf_share.copy()
        if "unit_nav" not in merged.columns:
            merged["unit_nav"] = pd.NA

    # 先算 flow，再 merge labels。原因：merge labels 会让每个 (ts_code, trade_date)
    # 复制成多行（每个 label 一行），此时 compute_etf_flow 的 groupby("ts_code").shift(1)
    # 会在同日内跨 label 行错位 shift，导致大部分 diff=0（每个 ts_code 只有 1/N 的行能
    # 拿到正确的 prev_share）。先算 flow → 每 (ts_code, trade_date) 唯一 → diff 正确；
    # 然后再 merge labels 把行 explode 到各个 panel。
    flow = compute_etf_flow(merged) if not merged.empty else merged

    if not flow.empty and (
        "dimension" not in flow.columns or "label" not in flow.columns
    ):
        if not labels.empty:
            # drop_duplicates() 保留每个 (ts_code, dimension, label) 一行；
            # merge on ts_code 自然 explode — 同一 ETF 在多个面板下重复出现
            # （per pit_labels.py docstring: 同一 ETF 可多维度多标签）
            flow = flow.merge(
                labels[["ts_code", "dimension", "label"]].drop_duplicates(),
                on="ts_code",
                how="left",
            )
        else:
            flow["dimension"] = "ownership"
            flow["label"] = "uncategorized"

    coverage = 1.0 if not flow.empty else None
    kwargs = {
        "data_date": data_date,
        "coverage": coverage,
        "last_success_at": as_of.strftime("%Y-%m-%d %H:%M"),
    }

    # —— 章节结构：header → KPI 卡片 → §1 ETF → §2 两融 → §3 衍生品 → §4 周度/月度 ——
    # 顺序与 ashare-flow-weekly 周报原型对齐，但保留我们日报的颗粒度。
    body_parts: list[str] = []

    # 两融数据（先算，KPI 卡片要用）
    if not margin_df.empty:
        m = aggregate_market_margin(margin_df, market_scope=None)
        m = compute_weekly_change(m)
    else:
        m = pd.DataFrame()

    # 基差数据（先算，KPI 卡片要用）
    spot_df = pd.concat([spot_500, spot_1000], ignore_index=True)
    if not ic_fut.empty and not im_fut.empty:
        basis_ic = compute_basis(
            ic_fut, spot_df, spot_map={"IC": "000905.SH"}, max_quote_skew_seconds=None
        )
        basis_im = compute_basis(
            im_fut, spot_df, spot_map={"IM": "000852.SH"}, max_quote_skew_seconds=None
        )
    else:
        basis_ic = pd.DataFrame()
        basis_im = pd.DataFrame()

    # KPI 卡片取当月主力（tenors 首档），图表展示全部三档
    front_ym = tenors[0][0]
    basis_ic_front = (
        basis_ic[basis_ic["ts_code"] == f"IC{front_ym}.CFX"]
        if not basis_ic.empty
        else basis_ic
    )
    basis_im_front = (
        basis_im[basis_im["ts_code"] == f"IM{front_ym}.CFX"]
        if not basis_im.empty
        else basis_im
    )

    # 核心结论 KPI 卡片
    body_parts.append(
        render_summary_section(
            flow=flow,
            margin_agg=m,
            basis_ic=basis_ic_front,
            basis_im=basis_im_front,
        )
    )

    # §1 ETF 被动资金（9 个日度面板）
    body_parts.append(
        render_section_band(
            anchor_id="section-etf",
            num="01",
            title="ETF 被动资金 · 日度流量",
            subtitle="国家队 / 宽基 / 科技 / 行业 / 周期",
        )
    )
    body_parts.append(render_huijin_broad_daily(flow, **kwargs))
    body_parts.append(render_tech_tmt_daily(flow, **kwargs))
    body_parts.append(render_total_market_daily(flow, **kwargs))
    body_parts.append(render_broad_daily(flow, **kwargs))
    body_parts.append(render_industry_theme_daily(flow, **kwargs))
    body_parts.append(render_category_cumulative_daily(flow, **kwargs))
    body_parts.append(render_cycle_daily(flow, **kwargs))
    body_parts.append(render_cycle_cumulative_daily(flow, **kwargs))
    body_parts.append(render_top15_etf_daily(flow, **kwargs))

    # §2 杠杆资金（两融）：交易所 + 行业
    body_parts.append(
        render_section_band(
            anchor_id="section-margin",
            num="02",
            title="杠杆资金 · 两融",
            subtitle="融资余额 / 行业净融资变化",
        )
    )
    m_kwargs = {
        "data_date": data_date,
        "coverage": 1.0 if not m.empty else None,
        "last_success_at": as_of_format(as_of),
        "reconciliation_tolerance": None,
    }
    body_parts.append(render_margin_exchange_panel(m, **m_kwargs))

    # Phase C 第 16 面板：行业 5 日净变化表
    margin_detail_df = _load_margin_detail_for_pipeline(start, end, as_of)
    if not margin_detail_df.empty:
        members = _load_sw_l1_members()
        members_daily = _pivot_sw_l1_to_daily(members, start=start, end=end)
        industry_agg = aggregate_margin_by_industry(margin_detail_df, members_daily)
        industry_with_change = compute_net_margin_change(industry_agg, n_trading_days=5)
        industry_coverage = 1.0 if not industry_with_change.empty else None
    else:
        industry_with_change = pd.DataFrame()
        industry_coverage = None
    body_parts.append(
        render_margin_industry_heatmap(
            industry_with_change,
            data_date=data_date,
            coverage=industry_coverage,
            last_success_at=as_of_format(as_of),
        )
    )

    # §3 衍生品（期货基差）
    body_parts.append(
        render_section_band(
            anchor_id="section-basis",
            num="03",
            title="衍生品 · 期货基差",
            subtitle="IC（中证 500）/ IM（中证 1000）",
        )
    )
    body_parts.append(
        render_basis_panel(
            ic_df=basis_ic,
            im_df=basis_im,
            data_date=data_date,
            coverage=1.0 if not basis_ic.empty else None,
            last_success_at=as_of_format(as_of),
            layer="eod",
        )
    )

    # §4 周度/月度回顾
    body_parts.append(
        render_section_band(
            anchor_id="section-periodic",
            num="04",
            title="周度 / 月度回顾",
            subtitle="ETF 资金中期趋势",
        )
    )
    from flow_dashboard.indicators.flow_aggregation import (
        aggregate_monthly_flow,
        aggregate_weekly_flow,
    )

    if not flow.empty:
        weekly = aggregate_weekly_flow(flow)
        weekly = weekly.rename(columns={"week_start": "period_start"})
    else:
        weekly = pd.DataFrame()
    w_kwargs = {
        "data_date": data_date,
        "coverage": 0.95 if not weekly.empty else None,
        "last_success_at": as_of.strftime("%Y-%m-%d %H:%M"),
    }
    body_parts.append(render_broad_weekly(weekly, **w_kwargs))
    body_parts.append(render_industry_theme_weekly(weekly, **w_kwargs))
    body_parts.append(render_category_cumulative_weekly(weekly, **w_kwargs))
    if not flow.empty:
        monthly = aggregate_monthly_flow(flow)
    else:
        monthly = pd.DataFrame()
    body_parts.append(render_monthly_total(monthly, **w_kwargs))

    body = "\n".join(body_parts)

    title_suffix = " (partial)" if is_partial else ""
    try:
        hk_body, hk_data_date = _render_hk_tab_for_pipeline(as_of)
    except Exception:  # 港股渲染故障不得阻塞 A股 发布（设计 §3 隔离）
        log.warning("hk tab render failed; publishing with banner", exc_info=True)
        hk_body = ('<div class="panel stale">⚠️ 港股沽空数据待更新 — 渲染异常，'
                   '请检查 hk_short 缓存与日志。</div>')
        hk_data_date = None
    full_html = build_html_skeleton(
        title=f"市场流动性日报 — {report_date}{title_suffix}",
        body=body,
        data_date=report_date,
        last_success_at=as_of.strftime("%Y-%m-%d %H:%M CST"),
        footer="市场观察，非交易建议。"
        + (" 本期为 partial：ETF 份额数据尚未完整入库。" if is_partial else ""),
        tabs=[
            {
                "id": "ashare",
                "name": "A股资金流",
                "body": body,
                "nav_sections": [
                    ("section-etf", "01 ETF 被动"),
                    ("section-margin", "02 杠杆资金"),
                    ("section-basis", "03 衍生品"),
                    ("section-periodic", "04 周度/月度"),
                ],
            },
            {
                "id": "hk-short",
                "name": "港股沽空",
                "body": hk_body,
                "nav_sections": [
                    ("section-hk-conclusion", "HK 结论"),
                    ("section-hk-watch", "HK 明细"),
                ],
            },
        ],
    )

    _, archive_path, _, _ = publish_archive(
        output_dir=output_dir,
        data_date=report_date,
        html_body=body,
        manifest_payload={
            "panels": panel_ids,
            "source_versions": {
                "etf_share": "etf_share_size_v1",
                "margin": "margin_v1",
                "fut_daily": "fut_daily_v1",
                "index_daily": "index_daily_v1",
                "hk_short": "hk_short_v1",
            },
            "panel_status": {
                "is_partial": is_partial,
                "ashare_data_date": data_date,
                "hk_data_date": hk_data_date,
            },
        },
        full_html=full_html,
    )
    return archive_path


def as_of_format(as_of: pd.Timestamp) -> str:
    return as_of.strftime("%Y-%m-%d %H:%M")


def _render_hk_tab_for_pipeline(as_of: pd.Timestamp) -> tuple[str, str | None]:
    """渲染港股沽空 tab（只读缓存，无网络/无写入；供单测 patch）。"""
    from flow_dashboard.render.panels_hk_short import render_hk_short_body

    return render_hk_short_body(as_of=as_of)


def _load_etf_share_for_pipeline(codes, start, end, as_of):
    from flow_dashboard.data.loaders import load_etf_share

    return load_etf_share(codes=codes, start=start, end=end, as_of=as_of)


def _load_margin_for_pipeline(start, end, as_of):
    from flow_dashboard.data.loaders import load_margin

    return load_margin(start=start, end=end, as_of=as_of)


def _load_fut_daily_for_pipeline(ts_code, start, end, as_of):
    from flow_dashboard.data.loaders import load_fut_daily

    df = load_fut_daily(ts_code=ts_code, start=start, end=end, as_of=as_of)
    if not df.empty and "delist_date" not in df.columns:
        # Phase B 占位：未接 fut_basic；按合约月份的第三个周五推到期日。
        # 仅影响 days_to_delist / 年化贴水（未绘图），不影响 basis_points。
        from flow_dashboard.indicators.basis import third_friday_of_contract

        df["delist_date"] = third_friday_of_contract(ts_code)
    return df


def _load_fut_daily_multi(ts_codes, start, end, as_of):
    frames = [
        d
        for d in (_load_fut_daily_for_pipeline(c, start, end, as_of) for c in ts_codes)
        if not d.empty
    ]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _load_index_daily_for_pipeline(ts_code, start, end, as_of):
    from flow_dashboard.data.loaders import load_index_daily

    return load_index_daily(ts_code=ts_code, start=start, end=end, as_of=as_of)


def _load_fund_nav_for_pipeline(codes, start, end, as_of):
    from flow_dashboard.data.loaders import load_fund_nav

    return load_fund_nav(codes=codes, start=start, end=end, as_of=as_of)


def _load_margin_detail_for_pipeline(start, end, as_of):
    from flow_dashboard.data.loaders import load_margin_detail

    return load_margin_detail(start=start, end=end, as_of=as_of)


def _load_sw_l1_members():
    from flow_dashboard.data.sw_l1_members import load_sw_l1_members

    return load_sw_l1_members()


def _pivot_sw_l1_to_daily(members, *, start, end):
    from flow_dashboard.data.sw_l1_members import pivot_to_daily_membership

    return pivot_to_daily_membership(members, start=start, end=end)


def run_daily_finalize(
    *,
    data_date: str,
    as_of: pd.Timestamp,
    output_dir: Path | str | None = None,
    lock_path: Path | str | None = None,
    universe: list[str] | None = None,
    force: bool = False,
) -> Path:
    """T+1 09:30+ 定稿 T 日报告。

    与 eod_preview 共享渲染逻辑（_run_eod_preview_inner），但同日补跑会
    通过 publish_archive.next_version_number 自动递增版本号；旧版本不删除。
    """
    output_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    lock_path = Path(lock_path) if lock_path else RUNNERS_LOCK
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        with acquire_runner_lock(lock_path):
            return _run_eod_preview_inner(data_date, as_of, output_dir, universe)
    except RunnerLockError:
        log.warning("daily_finalize skipped_due_to_lock at %s", as_of)
        return output_dir / f"report_{data_date}_v01.html"


def run_monthly(
    *,
    as_of: pd.Timestamp,
    output_dir: Path | str | None = None,
    labels_path: Path | str | None = None,
    force: bool = False,
) -> Path:
    """每月入口：Phase B 仅刷新 PIT 分类表快照。

    spec §3.1: 公募代理指标（s6/s7）属于 Phase C，本函数不实现。
    spec §3.1: 数据未披露则保留上期并显示原始 source_date。

    本函数只做"快照拷贝"：不强制 PIT 完整 schema（confirmed_at 等可缺），
    避免在月度归档环节因局部缺列阻断发布；下游分析环节仍由 load_pit_labels
    做严格契约校验。源文件未变更时，重复调用产出字节一致（to_csv 确定性）。
    """
    output_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    if labels_path is None:
        labels_path = Path("data/flow_dashboard/phase_a_evidence/etf_pit_labels.csv")
    labels_path = Path(labels_path)

    df = pd.read_csv(labels_path)
    snapshot_path = output_dir / f"pit_labels_monthly_{as_of.strftime('%Y-%m-%d')}.csv"
    df.to_csv(snapshot_path, index=False, encoding="utf-8-sig")
    return snapshot_path
