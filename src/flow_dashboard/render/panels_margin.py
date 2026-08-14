"""两融面板：分交易所融资余额 + 周变化。"""
from __future__ import annotations

from html import escape as _html_escape

import pandas as pd
import plotly.graph_objects as go

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


# reconciliation_tolerance 未冻结时不在面板上显示对账状态（spec §3.5 共通验收）
