"""日度 ETF 面板（12 个）。

口径层级：宽基 / 行业为两大资产类别；科技（tech）、周期（cycle）、传统行业
（industry）是行业内部子类，各有累计折线专项面板，另有行业全口径面板（13 只）。

每个 render_* 函数：
- 接收 flow_df + 元数据
- 返回 HTML 片段：<div class="panel"> + Plotly.newPlot 调用
- 上游 df 为空、label 过滤后为空或 coverage=None 时显式标 stale，不渲染 figure
"""
from __future__ import annotations

from html import escape as _html_escape

import pandas as pd

from flow_dashboard.indicators.flow_aggregation import (
    dedup_flow_by_etf_day,
    normalize_asset_scope,
)
from flow_dashboard.render.figures import (
    bar_flow_panel,
    line_cumulative_panel,
    multi_line_cumulative_panel,
    stacked_bar_breakdown_panel,
    horizontal_topn_panel,
)
from flow_dashboard.render.theme import render_figure_to_html


def _wrap_panel(
    div_id: str,
    title: str,
    body: str,
    stale: bool = False,
    subtitle: str | None = None,
) -> str:
    stale_cls = " stale" if stale else ""
    subtitle_html = (
        f'<p class="panel-subtitle">{_html_escape(subtitle)}</p>' if subtitle else ""
    )
    return f"""<div class="panel{stale_cls}" id="{div_id}">
<h2 class="panel-title">{_html_escape(title)}</h2>
{subtitle_html}
{body}
</div>"""


def _stale_message(reason: str = "数据不可得") -> str:
    return f'<div class="stale">⚠️ {reason}（stale）</div>'


def _stale_or_none(
    sub: pd.DataFrame,
    coverage: float | None,
    div_id: str,
    title: str,
    subtitle: str | None = None,
) -> str | None:
    """如果 sub 为空或 coverage 为 None，返回 stale panel；否则返回 None。"""
    if sub.empty or coverage is None:
        return _wrap_panel(
            div_id, title, _stale_message(), stale=True, subtitle=subtitle
        )
    return None


def render_huijin_broad_daily(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    title = "国家队 · 汇金持仓宽基 ETF 日度流量"
    subtitle = "中央汇金持仓的 3 只宽基（50/300/500 ETF）—— 国家队动向专项跟踪"
    sub = df[df["label"] == "huijin"] if "label" in df.columns else df
    stale = _stale_or_none(sub, coverage, "panel-huijin-broad-daily", title, subtitle)
    if stale:
        return stale
    fig = bar_flow_panel(sub, title=title,
                         data_date=data_date, coverage=coverage,
                         last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-huijin-broad-daily-fig")
    return _wrap_panel("panel-huijin-broad-daily", title, body, subtitle=subtitle)


def render_tech_tmt_daily(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    title = "科技/TMT ETF 日度流量"
    subtitle = "行业子类专项：半导体 / 芯片 / 科技 3 只（含于行业全口径面板）"
    sub = df[df["label"] == "tech"] if "label" in df.columns else df
    stale = _stale_or_none(sub, coverage, "panel-tech-tmt-daily", title, subtitle)
    if stale:
        return stale
    fig = bar_flow_panel(sub, title=title,
                         data_date=data_date, coverage=coverage,
                         last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-tech-tmt-daily-fig")
    return _wrap_panel("panel-tech-tmt-daily", title, body, subtitle=subtitle)


def render_total_market_daily(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    title = "全市场 ETF 合计日度流量"
    subtitle = (
        "样本池每只 ETF 计一次（不随标签重复）加总为单根柱 —— "
        "反映 A 股 ETF 市场整体资金流向"
    )
    stale = _stale_or_none(df, coverage, "panel-total-market-daily", title, subtitle)
    if stale:
        return stale
    # flow 经 pit_labels explode 后同一 (ts_code, trade_date) 有多行（huijin/broad/
    # benchmark 各一行），直接求和会把多标签 ETF 计 3 次，必须先去重
    uniq = dedup_flow_by_etf_day(df)
    agg = uniq.groupby("trade_date", as_index=False)["etf_estimated_flow_cny"].sum()
    agg["label"] = "ALL"
    fig = bar_flow_panel(agg, title=title,
                         data_date=data_date, coverage=coverage,
                         last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-total-market-daily-fig")
    return _wrap_panel("panel-total-market-daily", title, body, subtitle=subtitle)


def render_broad_daily(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    title = "宽基 ETF 日度流量（按品种分色）"
    subtitle = "资产类别=broad：50 / 300 / 500 / 创业板 4 只主流宽基指数 ETF"
    sub = df[df["label"] == "broad"] if "label" in df.columns else df
    stale = _stale_or_none(sub, coverage, "panel-broad-daily", title, subtitle)
    if stale:
        return stale
    fig = bar_flow_panel(sub, title=title,
                         data_date=data_date, coverage=coverage,
                         last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-broad-daily-fig")
    return _wrap_panel("panel-broad-daily", title, body, subtitle=subtitle)


def render_industry_theme_daily(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    title = "行业 ETF 日度流量（按品种分色）"
    subtitle = (
        "资产类别=industry+tech+cycle：军工 / 银行 / 券商 / 食品饮料 / 医药 / 新能源车 / "
        "有色 / 房地产 / 半导体 / 芯片 / 科技 / 钢铁 / 煤炭，共 13 只行业代表 ETF"
    )
    sub = (
        df[df["label"].isin(["industry", "tech", "cycle"])]
        if "label" in df.columns
        else df
    )
    stale = _stale_or_none(sub, coverage, "panel-industry-theme-daily", title, subtitle)
    if stale:
        return stale
    fig = bar_flow_panel(sub, title=title,
                         data_date=data_date, coverage=coverage,
                         last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-industry-theme-daily-fig")
    return _wrap_panel("panel-industry-theme-daily", title, body, subtitle=subtitle)


def render_category_cumulative_daily(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    title = "按资产类别堆叠 · 日度流量"
    subtitle = (
        "每只 ETF 按唯一资产类别计入宽基 / 行业两段堆叠，两段之和 = 全市场合计"
        "（行业含科技、周期等子类，细分见专项面板；创业板归宽基，不重复计数；"
        "huijin 属 ownership 维度已排除，国家队动向见专项面板）。"
    )
    # 只保留 asset_scope 维度并归一化：huijin（ownership）与 benchmark 维度排除；
    # 创业板同时挂 growth/broad 两个 asset_scope 标签，归一后只计一次
    sub = df
    if "dimension" in df.columns:
        sub = df[df["dimension"] == "asset_scope"]
    sub = normalize_asset_scope(sub)
    stale = _stale_or_none(sub, coverage, "panel-category-cumulative-daily", title, subtitle)
    if stale:
        return stale
    fig = stacked_bar_breakdown_panel(sub, title=title,
                                       data_date=data_date, coverage=coverage,
                                       last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-category-cumulative-daily-fig")
    return _wrap_panel("panel-category-cumulative-daily", title, body, subtitle=subtitle)


def render_tech_cumulative_daily(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    title = "科技 ETF 累计净流入"
    subtitle = "行业子类专项：科技 ETF（半导体+芯片+科技）逐日累计净流入折线 —— 反映科技板块资金中期趋势"
    sub = df[df["label"] == "tech"] if "label" in df.columns else df
    stale = _stale_or_none(sub, coverage, "panel-tech-cumulative-daily", title, subtitle)
    if stale:
        return stale
    by_date = sub.groupby("trade_date", as_index=False)["etf_estimated_flow_cny"].sum()
    by_date = by_date.sort_values("trade_date")
    by_date["cumulative_flow_cny"] = by_date["etf_estimated_flow_cny"].cumsum()
    fig = line_cumulative_panel(by_date, title=title,
                                data_date=data_date, coverage=coverage,
                                last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-tech-cumulative-daily-fig")
    return _wrap_panel("panel-tech-cumulative-daily", title, body, subtitle=subtitle)


def render_cycle_daily(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    title = "周期 ETF 日度流量（按品种分色）"
    subtitle = "行业子类专项：钢铁 / 煤炭 2 只周期 ETF（含于行业全口径面板）"
    sub = df[df["label"] == "cycle"] if "label" in df.columns else df
    stale = _stale_or_none(sub, coverage, "panel-cycle-daily", title, subtitle)
    if stale:
        return stale
    fig = bar_flow_panel(sub, title=title,
                         data_date=data_date, coverage=coverage,
                         last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-cycle-daily-fig")
    return _wrap_panel("panel-cycle-daily", title, body, subtitle=subtitle)


def render_cycle_cumulative_daily(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    title = "周期 ETF 累计净流入"
    subtitle = "行业子类专项：周期 ETF（钢铁+煤炭）逐日累计净流入折线 —— 反映周期板块资金中期趋势"
    sub = df[df["label"] == "cycle"] if "label" in df.columns else df
    stale = _stale_or_none(sub, coverage, "panel-cycle-cumulative-daily", title, subtitle)
    if stale:
        return stale
    by_date = sub.groupby("trade_date", as_index=False)["etf_estimated_flow_cny"].sum()
    by_date = by_date.sort_values("trade_date")
    by_date["cumulative_flow_cny"] = by_date["etf_estimated_flow_cny"].cumsum()
    fig = line_cumulative_panel(by_date, title=title,
                                 data_date=data_date, coverage=coverage,
                                 last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-cycle-cumulative-daily-fig")
    return _wrap_panel("panel-cycle-cumulative-daily", title, body, subtitle=subtitle)


def render_industry_core_cumulative_daily(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    title = "传统行业 ETF 累计净流入对比"
    subtitle = (
        "行业子类专项：8 只传统行业 ETF（军工 / 银行 / 券商 / 食品饮料 / 医药 / "
        "新能源车 / 有色 / 房地产）逐日累计净流入对比；科技、周期见各自专项折线"
    )
    sub = df[df["label"] == "industry"] if "label" in df.columns else df
    stale = _stale_or_none(sub, coverage, "panel-industry-core-cumulative-daily", title, subtitle)
    if stale:
        return stale
    fig = multi_line_cumulative_panel(sub, title=title,
                                      data_date=data_date, coverage=coverage,
                                      last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-industry-core-cumulative-daily-fig")
    return _wrap_panel("panel-industry-core-cumulative-daily", title, body, subtitle=subtitle)


def render_top15_etf_daily(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    title = "单只 ETF 流量 TOP15（最新交易日）"
    subtitle = "最新交易日所有标的中 |净流入| 最大的 15 只 —— 单日焦点标的速览"
    stale = _stale_or_none(df, coverage, "panel-top15-daily", title, subtitle)
    if stale:
        return stale
    # 多标签 ETF 在 explode 后同日有多行，先去重避免同一 ETF 重复上榜/条长×N
    latest = df[df["trade_date"] == df["trade_date"].max()]
    latest = latest.drop_duplicates(subset=["ts_code", "trade_date"])
    fig = horizontal_topn_panel(latest, title=title,
                                data_date=data_date, coverage=coverage,
                                last_success_at=last_success_at, topn=15)
    body = render_figure_to_html(fig, div_id="panel-top15-daily-fig")
    return _wrap_panel("panel-top15-daily", title, body, subtitle=subtitle)
