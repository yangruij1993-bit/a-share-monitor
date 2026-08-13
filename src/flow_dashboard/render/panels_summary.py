# src/flow_dashboard/render/panels_summary.py
"""核心结论 KPI 卡片：从已计算的指标里抽出当日/近 5 日关键数字。

参考 ashare-flow-weekly 周报的"核心结论"区设计 ——
顶部一排卡片速览全局资金动向，让读者一眼抓住重点。

输入数据：pipeline 已算出的 flow / margin / basis DataFrame；
不做任何指标计算本身（计算逻辑在 indicators/ 下），
这里只做"挑出最新一天的某个数字 + 格式化为亿元/百分比"。
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from flow_dashboard.render.theme import render_kpi_cards


_YI = 1e8


def _latest_flow_by_label(flow: pd.DataFrame, label: str) -> float | None:
    """取最新交易日指定 label 的 etf_estimated_flow_cny 合计（元）。"""
    if flow.empty or "label" not in flow.columns:
        return None
    sub = flow[flow["label"] == label]
    if sub.empty:
        return None
    latest = sub["trade_date"].max()
    return float(sub.loc[sub["trade_date"] == latest, "etf_estimated_flow_cny"].sum())


def _latest_total_flow(flow: pd.DataFrame) -> float | None:
    if flow.empty:
        return None
    latest = flow["trade_date"].max()
    return float(flow.loc[flow["trade_date"] == latest, "etf_estimated_flow_cny"].sum())


def _sum_flow_last_n_days(flow: pd.DataFrame, label: str | None, n: int = 5) -> float | None:
    """近 n 个交易日指定 label 的累计净流入（元）。label=None 表示全部。"""
    if flow.empty:
        return None
    sub = flow if label is None else (
        flow[flow["label"] == label] if "label" in flow.columns else flow
    )
    if sub.empty:
        return None
    dates = sorted(sub["trade_date"].unique())[-n:]
    recent = sub[sub["trade_date"].isin(dates)]
    return float(recent["etf_estimated_flow_cny"].sum())


def _fmt_yi(v: float | None) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{v / _YI:+.1f}"


def _fmt_yi_abs(v: float | None) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{abs(v) / _YI:.1f}"


def _tone(v: float | None) -> str:
    if v is None or pd.isna(v) or v == 0:
        return "neutral"
    return "positive" if v > 0 else "negative"


def build_etf_summary_cards(
    flow: pd.DataFrame,
    *,
    n_day_window: int = 5,
) -> list[dict[str, Any]]:
    """从 ETF flow DataFrame 构建 4 张 KPI 卡片：
    全市场今日 / 全市场近 5 日 / 国家队今日 / 科技今日。"""
    total_today = _latest_total_flow(flow)
    total_5d = _sum_flow_last_n_days(flow, label=None, n=n_day_window)
    huijin_today = _latest_flow_by_label(flow, "huijin")
    tech_today = _latest_flow_by_label(flow, "tech")

    return [
        {
            "label": "全市场 ETF 今日净流入",
            "value": _fmt_yi(total_today),
            "delta": "单位：亿元（+流入 / −流出）",
            "tone": _tone(total_today),
        },
        {
            "label": f"全市场 ETF 近 {n_day_window} 日累计",
            "value": _fmt_yi(total_5d),
            "delta": "亿元",
            "tone": _tone(total_5d),
        },
        {
            "label": "国家队（汇金）今日",
            "value": _fmt_yi(huijin_today),
            "delta": "50/300/500 三只代表 ETF",
            "tone": _tone(huijin_today),
        },
        {
            "label": "科技 / TMT 今日",
            "value": _fmt_yi(tech_today),
            "delta": "半导体 / 芯片 / 科技",
            "tone": _tone(tech_today),
        },
    ]


def build_margin_summary_cards(margin_agg: pd.DataFrame) -> list[dict[str, Any]]:
    """从 aggregate_market_margin + compute_weekly_change 的输出构建 2 张卡片：
    全市场融资余额 / 周变化。"""
    if margin_agg.empty or "exchange_id" not in margin_agg.columns:
        return [
            {"label": "全市场融资余额", "value": "—", "delta": "数据不可得"},
            {"label": "融资余额周变化", "value": "—", "delta": "数据不可得"},
        ]

    all_rows = margin_agg[margin_agg["exchange_id"] == "ALL"]
    if all_rows.empty:
        return [
            {"label": "全市场融资余额", "value": "—", "delta": "数据不可得"},
            {"label": "融资余额周变化", "value": "—", "delta": "数据不可得"},
        ]

    latest = all_rows[all_rows["trade_date"] == all_rows["trade_date"].max()].iloc[0]
    rzye = float(latest["rzye"]) if pd.notna(latest["rzye"]) else None
    weekly = (
        float(latest["weekly_change_rzye"])
        if "weekly_change_rzye" in latest.index and pd.notna(latest["weekly_change_rzye"])
        else None
    )

    return [
        {
            "label": "全市场融资余额",
            "value": f"{rzye / _YI:.0f}" if rzye is not None else "—",
            "delta": "亿元",
            "tone": "neutral",
        },
        {
            "label": "融资余额周变化",
            "value": _fmt_yi(weekly),
            "delta": "亿元（5 个交易日差）",
            "tone": _tone(weekly),
        },
    ]


def build_basis_summary_cards(
    basis_ic: pd.DataFrame, basis_im: pd.DataFrame,
) -> list[dict[str, Any]]:
    """IC / IM 最新基差（基点）。"""
    def _latest_basis(df: pd.DataFrame) -> float | None:
        if df.empty or "basis_points" not in df.columns:
            return None
        latest = df["trade_date"].max()
        rows = df[df["trade_date"] == latest]
        if rows.empty:
            return None
        return float(rows["basis_points"].iloc[0])

    ic = _latest_basis(basis_ic)
    im = _latest_basis(basis_im)

    return [
        {
            "label": "IC（中证 500）最新基差",
            "value": f"{ic:.1f}" if ic is not None else "—",
            "delta": "基点（贴水为负）",
            "tone": _tone(-ic if ic is not None else None),  # 升水=正→红，贴水→绿
        },
        {
            "label": "IM（中证 1000）最新基差",
            "value": f"{im:.1f}" if im is not None else "—",
            "delta": "基点（贴水为负）",
            "tone": _tone(-im if im is not None else None),
        },
    ]


def render_summary_section(
    *,
    flow: pd.DataFrame,
    margin_agg: pd.DataFrame,
    basis_ic: pd.DataFrame,
    basis_im: pd.DataFrame,
) -> str:
    """渲染"核心结论"卡片区（紧跟在 header 之后）。

    8 张卡片：4 ETF + 2 margin + 2 basis。
    """
    cards: list[dict[str, Any]] = []
    cards.extend(build_etf_summary_cards(flow))
    cards.extend(build_margin_summary_cards(margin_agg))
    cards.extend(build_basis_summary_cards(basis_ic, basis_im))
    return render_kpi_cards(cards)
