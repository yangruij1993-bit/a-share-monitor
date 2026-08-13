"""Figure 工厂：6 种共通图表，被 15 个面板调用。

每个工厂接收 DataFrame + 元数据，返回 plotly.go.Figure。
单位转换：内部统一为元；渲染时除 1e8 转亿元显示。
"""
from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from flow_dashboard.data.etf_names import etf_display_name
from flow_dashboard.render.theme import COLORS, apply_theme


_CNY_TO_YI = 1e8  # 亿元

# 多 ETF 堆叠柱图的调色板（Dark24，色盲友好且对比度高）
_ETF_PALETTE = px.colors.qualitative.Dark24


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
    """日度流量柱图。

    单只 ETF 或无 ts_code：正绿负红聚合（原行为）。
    多只 ETF：每只 ETF 一个调色板颜色，barmode="relative" 堆叠
    （正数向上堆、负数向下堆，上下方向区分净流入/流出，颜色区分品种）。
    """
    df = df.sort_values("trade_date")
    fig = go.Figure()

    has_multi_codes = "ts_code" in df.columns and df["ts_code"].nunique(dropna=True) > 1

    if has_multi_codes:
        codes = sorted(df["ts_code"].dropna().unique())
        for i, ts_code in enumerate(codes):
            sub = df[df["ts_code"] == ts_code].sort_values("trade_date")
            flows_yi = _to_yi(sub["etf_estimated_flow_cny"].tolist())
            color = _ETF_PALETTE[i % len(_ETF_PALETTE)]
            display_name = etf_display_name(str(ts_code))
            fig.add_trace(go.Bar(
                name=display_name,
                x=sub["trade_date"].astype(str).tolist(),
                y=flows_yi,
                marker_color=color,
                hovertemplate=(
                    f"{display_name} ({ts_code})<br>"
                    "%{x}<br>%{y:.2f} 亿元<extra></extra>"
                ),
            ))
        fig.update_layout(barmode="relative")
    else:
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
            hovertemplate="%{x}<br>%{y:.2f} 亿元<extra></extra>",
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
        vertical_spacing=0.25,
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
        height=720,
        margin={"l": 60, "r": 30, "t": 100, "b": 60},
        plot_bgcolor=COLORS["background"],
        showlegend=False,
    )
    # type="category" 防止 Plotly 把 "YYYY-MM-DD" 字符串识别为日期造成周末空白。
    fig.update_xaxes(type="category")
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


def industry_heatmap_panel(
    df: pd.DataFrame,
    *,
    title: str,
    data_date: str,
    coverage: float | None = None,
    last_success_at: str | None = None,
    n_trading_days: int = 30,
) -> go.Figure:
    """行业 × 交易日 热力图（净融资 N 日变化，正红负绿）。

    Args:
        df: aggregate_margin_by_industry + compute_net_margin_change 输出，
            必须含 trade_date, industry_name, net_margin_5d_change
        n_trading_days: 显示最近 N 个交易日（默认 30）
    """
    if df.empty:
        return apply_theme(
            go.Figure(), title=title, y_title="行业",
            data_date=data_date, coverage=coverage,
            last_success_at=last_success_at, unit="亿元",
        )

    df = df.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    # 取最近 N 个交易日
    recent_dates = sorted(df["trade_date"].unique())[-n_trading_days:]
    df = df[df["trade_date"].isin(recent_dates)]

    # 构造矩阵：行=行业（按名称排序），列=日期
    pivot = df.pivot_table(
        index="industry_name",
        columns="trade_date",
        values="net_margin_5d_change",
        aggfunc="first",
    )
    pivot = pivot.reindex(sorted(pivot.index))  # 行业名排序
    pivot = pivot[sorted(pivot.columns)]  # 日期排序

    x = [d.strftime("%Y-%m-%d") for d in pivot.columns]
    y = list(pivot.index)
    # 元 → 亿元（保留 NaN）
    z = [[v / _CNY_TO_YI if pd.notna(v) else None for v in row]
         for row in pivot.values]

    fig = go.Figure(data=go.Heatmap(
        z=z, x=x, y=y,
        colorscale=[
            [0.0, "rgb(0, 128, 0)"],    # 负值=绿
            [0.5, "rgb(255, 255, 255)"],  # 0=白
            [1.0, "rgb(255, 0, 0)"],     # 正值=红
        ],
        zmid=0,
        colorbar={"title": "亿元"},
        hovertemplate="%{y}<br>%{x}<br>%{z:.2f} 亿元<extra></extra>",
    ))

    return apply_theme(
        fig, title=title, y_title="申万一级行业",
        data_date=data_date, coverage=coverage,
        last_success_at=last_success_at, unit="亿元",
    )
