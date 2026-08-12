"""15 个 MVP 面板中的 9 个日度 ETF 面板。

每个 render_* 函数：
- 接收 flow_df + 元数据
- 返回 HTML 片段：<div class="panel"> + Plotly.newPlot 调用
- 上游 df 为空、label 过滤后为空或 coverage=None 时显式标 stale，不渲染 figure
"""
from __future__ import annotations

from html import escape as _html_escape

import pandas as pd

from flow_dashboard.render.figures import (
    bar_flow_panel,
    line_cumulative_panel,
    stacked_bar_breakdown_panel,
    horizontal_topn_panel,
)
from flow_dashboard.render.theme import render_figure_to_html


def _wrap_panel(div_id: str, title: str, body: str, stale: bool = False) -> str:
    stale_cls = " stale" if stale else ""
    return f"""<div class="panel{stale_cls}" id="{div_id}">
<h2 class="panel-title">{_html_escape(title)}</h2>
{body}
</div>"""


def _stale_message(reason: str = "数据不可得") -> str:
    return f'<div class="stale">⚠️ {reason}（stale）</div>'


def _stale_or_none(
    sub: pd.DataFrame,
    coverage: float | None,
    div_id: str,
    title: str,
) -> str | None:
    """如果 sub 为空或 coverage 为 None，返回 stale panel；否则返回 None。"""
    if sub.empty or coverage is None:
        return _wrap_panel(div_id, title, _stale_message(), stale=True)
    return None


def render_huijin_broad_daily(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    sub = df[df["label"] == "huijin"] if "label" in df.columns else df
    stale = _stale_or_none(sub, coverage, "panel-huijin-broad-daily", "汇金宽基 ETF 日度流量")
    if stale:
        return stale
    fig = bar_flow_panel(sub, title="汇金宽基 ETF 日度流量",
                         data_date=data_date, coverage=coverage,
                         last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-huijin-broad-daily")
    return _wrap_panel("panel-huijin-broad-daily", "汇金宽基 ETF 日度流量", body)


def render_tech_tmt_daily(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    sub = df[df["label"] == "tech"] if "label" in df.columns else df
    stale = _stale_or_none(sub, coverage, "panel-tech-tmt-daily", "科技/TMT ETF 日度流量")
    if stale:
        return stale
    fig = bar_flow_panel(sub, title="科技/TMT ETF 日度流量（对照中证 TMT）",
                         data_date=data_date, coverage=coverage,
                         last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-tech-tmt-daily")
    return _wrap_panel("panel-tech-tmt-daily", "科技/TMT ETF 日度流量", body)


def render_total_market_daily(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    stale = _stale_or_none(df, coverage, "panel-total-market-daily", "全市场合计日度流量")
    if stale:
        return stale
    agg = df.groupby("trade_date", as_index=False)["etf_estimated_flow_cny"].sum()
    agg["label"] = "ALL"
    fig = bar_flow_panel(agg, title="全市场 ETF 合计日度流量",
                         data_date=data_date, coverage=coverage,
                         last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-total-market-daily")
    return _wrap_panel("panel-total-market-daily", "全市场合计日度流量", body)


def render_broad_daily(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    sub = df[df["label"] == "broad"] if "label" in df.columns else df
    stale = _stale_or_none(sub, coverage, "panel-broad-daily", "宽基 ETF 日度流量")
    if stale:
        return stale
    fig = bar_flow_panel(sub, title="宽基 ETF 日度流量",
                         data_date=data_date, coverage=coverage,
                         last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-broad-daily")
    return _wrap_panel("panel-broad-daily", "宽基 ETF 日度流量", body)


def render_industry_theme_daily(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    sub = df[df["label"] == "industry"] if "label" in df.columns else df
    stale = _stale_or_none(sub, coverage, "panel-industry-theme-daily", "行业/主题 ETF 日度流量")
    if stale:
        return stale
    fig = bar_flow_panel(sub, title="行业/主题 ETF 日度流量",
                         data_date=data_date, coverage=coverage,
                         last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-industry-theme-daily")
    return _wrap_panel("panel-industry-theme-daily", "行业/主题 ETF 日度流量", body)


def render_category_cumulative_daily(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    stale = _stale_or_none(df, coverage, "panel-category-cumulative-daily", "分类累计日度流量")
    if stale:
        return stale
    fig = stacked_bar_breakdown_panel(df, title="分类累计日度流量",
                                       data_date=data_date, coverage=coverage,
                                       last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-category-cumulative-daily")
    return _wrap_panel("panel-category-cumulative-daily", "分类累计日度流量", body)


def render_cycle_daily(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    sub = df[df["label"] == "cycle"] if "label" in df.columns else df
    stale = _stale_or_none(sub, coverage, "panel-cycle-daily", "周期主题 ETF 日度流量")
    if stale:
        return stale
    fig = bar_flow_panel(sub, title="周期主题 ETF 日度流量",
                         data_date=data_date, coverage=coverage,
                         last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-cycle-daily")
    return _wrap_panel("panel-cycle-daily", "周期主题 ETF 日度流量", body)


def render_cycle_cumulative_daily(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    sub = df[df["label"] == "cycle"] if "label" in df.columns else df
    stale = _stale_or_none(sub, coverage,
                           "panel-cycle-cumulative-daily", "周期主题 ETF 累计流量")
    if stale:
        return stale
    by_date = sub.groupby("trade_date", as_index=False)["etf_estimated_flow_cny"].sum()
    by_date = by_date.sort_values("trade_date")
    by_date["cumulative_flow_cny"] = by_date["etf_estimated_flow_cny"].cumsum()
    fig = line_cumulative_panel(by_date, title="周期主题 ETF 累计流量",
                                 data_date=data_date, coverage=coverage,
                                 last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-cycle-cumulative-daily")
    return _wrap_panel("panel-cycle-cumulative-daily", "周期主题 ETF 累计流量", body)


def render_top15_etf_daily(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    stale = _stale_or_none(df, coverage, "panel-top15-daily", "单只 ETF 流量 TOP15")
    if stale:
        return stale
    latest = df[df["trade_date"] == df["trade_date"].max()]
    fig = horizontal_topn_panel(latest, title="单只 ETF 流量 TOP15",
                                data_date=data_date, coverage=coverage,
                                last_success_at=last_success_at, topn=15)
    body = render_figure_to_html(fig, div_id="panel-top15-daily")
    return _wrap_panel("panel-top15-daily", "单只 ETF 流量 TOP15", body)
