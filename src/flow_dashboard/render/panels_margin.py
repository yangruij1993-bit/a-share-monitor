"""两融面板：分交易所融资余额 + 周变化；融资余额长期趋势（全市场/创业板）。"""
from __future__ import annotations

from html import escape as _html_escape

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from flow_dashboard.render.theme import COLORS, apply_theme, render_figure_to_html


def _wrap_panel(body: str, stale: bool = False) -> str:
    cls = " stale" if stale else ""
    title = _html_escape("分交易所融资余额与周变化")
    return f"""<div class="panel{cls}" id="panel-margin-exchange">
<h2 class="panel-title">{title}</h2>
{body}
</div>"""


def render_margin_exchange_panel(
    df: pd.DataFrame,
    *,
    data_date: str,
    coverage: float | None,
    last_success_at: str | None,
    reconciliation_tolerance: float | None,
) -> str:
    if df.empty or coverage is None:
        return _wrap_panel('<div class="stale">⚠️ 数据不可得（stale）</div>', stale=True)

    latest = df[df["trade_date"] == df["trade_date"].max()]
    latest = latest.sort_values("exchange_id")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="融资余额 (亿元)",
        x=latest["exchange_id"].tolist(),
        y=(latest["rzye"] / 1e8).tolist(),
        marker_color=COLORS["primary"],
        yaxis="y",
    ))
    fig.add_trace(go.Scatter(
        name="周变化 (亿元)",
        x=latest["exchange_id"].tolist(),
        y=(latest["weekly_change_rzye"] / 1e8).tolist(),
        mode="lines+markers",
        line={"color": COLORS["negative_flow"]},
        yaxis="y2",
    ))
    fig.update_layout(
        yaxis={"title": "亿元", "gridcolor": COLORS["grid"]},
        yaxis2={"title": "周变化 (亿元)", "overlaying": "y", "side": "right"},
        xaxis={"gridcolor": COLORS["grid"]},
        plot_bgcolor=COLORS["background"],
    )
    fig = apply_theme(fig, title="分交易所融资余额与周变化",
                      y_title="亿元", data_date=data_date,
                      coverage=coverage, last_success_at=last_success_at,
                      unit="亿元")
    body = render_figure_to_html(fig, div_id="panel-margin-exchange-fig")
    return _wrap_panel(body)


def render_margin_trend_panel(
    market_df: pd.DataFrame,
    chinext_df: pd.DataFrame,
    *,
    data_date: str,
    coverage: float | None,
    last_success_at: str | None,
) -> str:
    """融资余额长期趋势：全市场（三所合计）/ 创业板 双子图折线。

    Args:
        market_df: aggregate_market_margin 输出（exchange_id 含 ALL 行）
        chinext_df: aggregate_chinext_margin 输出 [trade_date, chinext_rzye]
    """
    title = _html_escape("融资余额长期趋势（全市场 / 创业板）")
    if market_df is None:
        market_df = pd.DataFrame()
    if chinext_df is None:
        chinext_df = pd.DataFrame()
    market = (
        market_df[market_df["exchange_id"] == "ALL"]
        if not market_df.empty and "exchange_id" in market_df.columns
        else market_df
    )
    if (market.empty and chinext_df.empty) or coverage is None:
        return f"""<div class="panel stale" id="panel-margin-trend">
<h2 class="panel-title">{title}</h2>
<div class="stale">⚠️ 数据不可得（stale）</div>
</div>"""

    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=True,
        subplot_titles=("全市场融资余额（沪深北合计）", "创业板融资余额（300/301）"),
        vertical_spacing=0.10,
    )
    if not market.empty:
        m = market.sort_values("trade_date")
        fig.add_trace(go.Scatter(
            x=m["trade_date"].astype(str).tolist(),
            y=(m["rzye"] / 1e8).tolist(),
            mode="lines",
            line={"color": COLORS["primary"], "width": 2},
            name="全市场",
            hovertemplate="%{x}<br>%{y:.0f} 亿元<extra></extra>",
        ), row=1, col=1)
    if not chinext_df.empty:
        c = chinext_df.sort_values("trade_date")
        fig.add_trace(go.Scatter(
            x=c["trade_date"].astype(str).tolist(),
            y=(c["chinext_rzye"] / 1e8).tolist(),
            mode="lines",
            line={"color": COLORS["warning"], "width": 2},
            name="创业板",
            hovertemplate="%{x}<br>%{y:.0f} 亿元<extra></extra>",
        ), row=2, col=1)
    fig.update_layout(
        height=680,
        margin={"l": 60, "r": 30, "t": 60, "b": 30},
        plot_bgcolor=COLORS["background"],
        showlegend=False,
    )
    # nticks 限稀疏刻度：486 个日历类目全画会把日期标签挤成逐日密排
    fig.update_xaxes(
        type="category", categoryorder="category ascending",
        gridcolor=COLORS["grid"], nticks=10, tickangle=-45,
    )
    # tickformat 统一两子图刻度风格（默认上图 15k/20k、下图 3000/4000 不一致）
    fig.update_yaxes(gridcolor=COLORS["grid"], title_text="亿元", tickformat=",.0f")
    notes = [f"数据日期: {data_date}"]
    if coverage is not None:
        notes.append(f"覆盖率: {coverage:.1%}")
    if last_success_at:
        notes.append(f"最近获取: {last_success_at}")
    # add_annotation 追加而不覆盖——make_subplots 的子图标题也存于
    # layout.annotations，update_layout(annotations=[...]) 会把它们替换掉
    fig.add_annotation(
        text=" | ".join(notes), showarrow=False,
        x=1.0, xref="paper", y=1.0, yref="paper",
        yanchor="bottom", xanchor="right",
        font={"size": 10, "color": "#666"},
    )
    body = render_figure_to_html(fig, div_id="panel-margin-trend-fig")
    return f"""<div class="panel" id="panel-margin-trend">
<h2 class="panel-title">{title}</h2>
{body}
</div>"""


# reconciliation_tolerance 未冻结时不在面板上显示对账状态（spec §3.5 共通验收）
