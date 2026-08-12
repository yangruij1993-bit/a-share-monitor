"""Figure 工厂：6 种共通图表，被 15 个面板调用。

每个工厂接收 DataFrame + 元数据，返回 plotly.go.Figure。
单位转换：内部统一为元；渲染时除 1e8 转亿元显示。
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from flow_dashboard.render.theme import COLORS, apply_theme


_CNY_TO_YI = 1e8  # 亿元


def _to_yi(values: pd.Series | list[float]) -> list[float | None]:
    return [v / _CNY_TO_YI if pd.notna(v) else None for v in values]


def bar_flow_panel(
    df: pd.DataFrame,
    *,
    title: str,
    data_date: str,
    coverage: float | None = None,
    last_success_at: str | None = None,
) -> go.Figure:
    """日度流量柱图（正绿负红）。"""
    df = df.sort_values("trade_date")
    fig = go.Figure()
    flows_yi = _to_yi(df["etf_estimated_flow_cny"].tolist())
    colors = [
        COLORS["positive_flow"] if (v is not None and v >= 0) else COLORS["negative_flow"]
        for v in flows_yi
    ]
    fig.add_trace(go.Bar(
        x=df["trade_date"].astype(str).tolist(),
        y=flows_yi,
        marker_color=colors,
        showlegend=False,
    ))
    return apply_theme(
        fig, title=title, y_title="亿元", data_date=data_date,
        coverage=coverage, last_success_at=last_success_at, unit="亿元",
    )


def line_cumulative_panel(
    df: pd.DataFrame,
    *,
    title: str,
    data_date: str,
    coverage: float | None = None,
    last_success_at: str | None = None,
    y_unit: str = "亿元",
) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["trade_date"].astype(str).tolist(),
        y=_to_yi(df["cumulative_flow_cny"].tolist()),
        mode="lines+markers",
        line={"color": COLORS["primary"]},
        showlegend=False,
    ))
    return apply_theme(
        fig, title=title, y_title=y_unit, data_date=data_date,
        coverage=coverage, last_success_at=last_success_at, unit=y_unit,
    )


def stacked_bar_breakdown_panel(
    df: pd.DataFrame,
    *,
    title: str,
    data_date: str,
    coverage: float | None = None,
    last_success_at: str | None = None,
) -> go.Figure:
    """分类细分堆叠柱图（label × trade_date）。"""
    fig = go.Figure()
    for label, sub in df.groupby("label", sort=False):
        sub = sub.sort_values("trade_date")
        fig.add_trace(go.Bar(
            name=str(label),
            x=sub["trade_date"].astype(str).tolist(),
            y=_to_yi(sub["etf_estimated_flow_cny"].tolist()),
        ))
    fig.update_layout(barmode="relative")
    return apply_theme(
        fig, title=title, y_title="亿元", data_date=data_date,
        coverage=coverage, last_success_at=last_success_at, unit="亿元",
    )


def horizontal_topn_panel(
    df: pd.DataFrame,
    *,
    title: str,
    data_date: str,
    coverage: float | None = None,
    last_success_at: str | None = None,
    topn: int = 15,
) -> go.Figure:
    """TOP15 横向柱（按绝对值降序）。"""
    df = df.copy()
    df["_abs"] = df["etf_estimated_flow_cny"].abs()
    df = df.sort_values("_abs", ascending=False).head(topn)
    fig = go.Figure()
    flows_yi = _to_yi(df["etf_estimated_flow_cny"].tolist())
    colors = [
        COLORS["positive_flow"] if (v is not None and v >= 0) else COLORS["negative_flow"]
        for v in flows_yi
    ]
    fig.add_trace(go.Bar(
        orientation="h",
        y=df["ts_code"].astype(str).tolist(),
        x=flows_yi,
        marker_color=colors,
        showlegend=False,
    ))
    return apply_theme(
        fig, title=title, y_title="ETF", data_date=data_date,
        coverage=coverage, last_success_at=last_success_at, unit="亿元",
    )


def multi_line_period_panel(
    df: pd.DataFrame,
    *,
    title: str,
    data_date: str,
    coverage: float | None = None,
    last_success_at: str | None = None,
) -> go.Figure:
    """周度/月度多线（每 label 一条折线）。"""
    fig = go.Figure()
    period_col = "period_start" if "period_start" in df.columns else "trade_date"
    for label, sub in df.groupby("label", sort=False):
        sub = sub.sort_values(period_col)
        fig.add_trace(go.Scatter(
            name=str(label),
            x=sub[period_col].astype(str).tolist(),
            y=_to_yi(sub["etf_estimated_flow_cny"].tolist()),
            mode="lines+markers",
        ))
    return apply_theme(
        fig, title=title, y_title="亿元", data_date=data_date,
        coverage=coverage, last_success_at=last_success_at, unit="亿元",
    )


def dual_subplot_basis_panel(
    ic_df: pd.DataFrame,
    im_df: pd.DataFrame,
    *,
    data_date: str,
    coverage: float | None = None,
    last_success_at: str | None = None,
) -> go.Figure:
    """IC/IM 双 subplot：basis_points 柱图（每个 variety 一行）。

    注：``annualized_discount_rate`` 列存在但不在此首版中绘制（spec §3.5.2 仅要求跟踪基差）。
    """
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=False,
        subplot_titles=("IC 中证 500 基差", "IM 中证 1000 基差"),
        vertical_spacing=0.15,
    )
    for i, (label, df) in enumerate([("IC", ic_df), ("IM", im_df)], start=1):
        df = df.sort_values("trade_date")
        fig.add_trace(
            go.Bar(
                x=df["trade_date"].astype(str).tolist(),
                y=df["basis_points"].tolist(),
                name=f"{label} basis_points",
                marker_color=COLORS["primary"] if i == 1 else COLORS["warning"],
            ),
            row=i, col=1,
        )
    fig.update_layout(
        title={
            "text": f"期货基差（IC/IM 逐合约）<br><span style='font-size:11px;color:#666'>数据日期: {data_date}</span>",
            "x": 0.5, "xanchor": "center",
        },
        height=600,
        plot_bgcolor=COLORS["background"],
        showlegend=False,
    )
    annotations = list(fig.layout.annotations or [])
    notes = []
    if coverage is not None:
        notes.append(f"覆盖率: {coverage:.1%}")
    if last_success_at:
        notes.append(f"最近获取: {last_success_at}")
    if notes:
        annotations.append({
            "text": " | ".join(notes),
            "showarrow": False, "x": 1.0, "xref": "paper",
            "y": 1.0, "yref": "paper", "yanchor": "bottom", "xanchor": "right",
            "font": {"size": 10, "color": "#666"},
        })
    fig.update_layout(annotations=annotations)
    return fig
