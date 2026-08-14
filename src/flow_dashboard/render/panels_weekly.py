"""4 个周度 ETF 面板。

每个 render_* 函数：
- 接收 flow_df + 元数据
- 返回 HTML 片段：<div class="panel"> + Plotly.newPlot 调用
- 上游 df 为空、label 过滤后为空或 coverage=None 时显式标 stale，不渲染 figure
"""
from __future__ import annotations

from html import escape as _html_escape

import pandas as pd

from flow_dashboard.render.figures import multi_line_period_panel
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


def render_broad_weekly(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    sub = df[df["label"] == "broad"] if "label" in df.columns else df
    stale = _stale_or_none(sub, coverage, "panel-broad-weekly", "宽基 ETF 周度流量")
    if stale:
        return stale
    fig = multi_line_period_panel(sub, title="宽基 ETF 周度流量",
                                  data_date=data_date, coverage=coverage,
                                  last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-broad-weekly-fig")
    return _wrap_panel("panel-broad-weekly", "宽基 ETF 周度流量", body)


def render_industry_theme_weekly(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    sub = df[df["label"] == "industry"] if "label" in df.columns else df
    stale = _stale_or_none(sub, coverage,
                           "panel-industry-weekly", "行业/主题 ETF 周度流量")
    if stale:
        return stale
    fig = multi_line_period_panel(sub, title="行业/主题 ETF 周度流量",
                                  data_date=data_date, coverage=coverage,
                                  last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-industry-weekly-fig")
    return _wrap_panel("panel-industry-weekly", "行业/主题 ETF 周度流量", body)


def render_category_cumulative_weekly(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    stale = _stale_or_none(df, coverage,
                           "panel-category-weekly", "分类累计周度流量")
    if stale:
        return stale
    fig = multi_line_period_panel(df, title="分类累计周度流量",
                                  data_date=data_date, coverage=coverage,
                                  last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-category-weekly-fig")
    return _wrap_panel("panel-category-weekly", "分类累计周度流量", body)


def render_monthly_total(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    stale = _stale_or_none(df, coverage, "panel-monthly-total", "月度合计")
    if stale:
        return stale
    # 月度合计：所有 label 在 month_start 上汇总
    agg = df.groupby("month_start", as_index=False)["etf_estimated_flow_cny"].sum()
    agg["label"] = "ALL"
    agg = agg.rename(columns={"month_start": "period_start"})
    fig = multi_line_period_panel(agg, title="月度合计流量",
                                  data_date=data_date, coverage=coverage,
                                  last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-monthly-total-fig")
    return _wrap_panel("panel-monthly-total", "月度合计", body)
