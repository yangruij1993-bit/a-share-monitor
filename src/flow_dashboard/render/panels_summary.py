# src/flow_dashboard/render/panels_summary.py
"""核心结论 KPI 卡片：水平值 + 短/中期变化，从投资者视角突出"变了什么"。

参考 ashare-flow-weekly 周报的"核心结论"区设计 ——
顶部一排卡片速览全局资金动向，让读者一眼抓住重点。

设计原则（投资者视角）：
- 主数值是水平值，但 delta 行必须回答"变化"：短（1/5 日）vs 中（20 日）对照；
- 绝对水平无信息量的指标（IC/IM 基差常年贴水），重点展示走阔/收敛；
- 附带连续天数等语境（连续第 N 日净流入 / 净流出）；
- tone 一律按"近期变化方向"着色：利多变化 → 红（positive），利空 → 绿（negative）。

输入数据：pipeline 已算出的 flow / margin / basis DataFrame；
不做任何指标计算本身（计算逻辑在 indicators/ 下）。
"""
from __future__ import annotations

from typing import Any

import pandas as pd

from flow_dashboard.render.theme import render_kpi_cards


_YI = 1e8


def _fmt_yi(v: float | None) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{v / _YI:+.1f}"


def _tone(v: float | None) -> str:
    if v is None or pd.isna(v) or v == 0:
        return "neutral"
    return "positive" if v > 0 else "negative"


# ============ ETF flow 派生量 ============


def _daily_flow_total(flow: pd.DataFrame, label: str | None = None) -> pd.Series:
    """按 trade_date 聚合的日度净流入合计（元），index 为 trade_date 升序。"""
    sub = flow
    if label is not None and "label" in flow.columns:
        sub = flow[flow["label"] == label]
    if sub.empty:
        return pd.Series(dtype=float)
    return sub.groupby("trade_date")["etf_estimated_flow_cny"].sum().sort_index()


def _streak_text(series: pd.Series) -> str:
    """连续同号天数描述：如 '连续第 4 日净流出'；不足 2 日返回空串。"""
    if len(series) < 2:
        return ""
    last = series.iloc[-1]
    if last == 0 or pd.isna(last):
        return ""
    n = 1
    for v in reversed(list(series.iloc[:-1])):
        if v == 0 or pd.isna(v) or (v > 0) != (last > 0):
            break
        n += 1
    direction = "净流入" if last > 0 else "净流出"
    return f"连续第 {n} 日{direction}"


def _sum_last_n(series: pd.Series, n: int) -> float | None:
    if len(series) == 0:
        return None
    return float(series.iloc[-n:].sum())


def build_etf_summary_cards(
    flow: pd.DataFrame,
    *,
    n_day_window: int = 5,
    m_day_window: int = 20,
) -> list[dict[str, Any]]:
    """4 张 ETF 卡片：全市场今日 / 全市场近5日 / 国家队今日 / 科技今日。

    每张 delta 行给出对照语境（连续天数、近 5/20 日累计），
    让读者判断单日数字是延续还是拐点。
    """
    total = _daily_flow_total(flow)
    today = float(total.iloc[-1]) if len(total) else None
    total_5d = _sum_last_n(total, n_day_window)
    total_20d = _sum_last_n(total, m_day_window)
    streak = _streak_text(total)

    huijin = _daily_flow_total(flow, "huijin")
    huijin_today = float(huijin.iloc[-1]) if len(huijin) else None
    huijin_5d = _sum_last_n(huijin, n_day_window)

    tech = _daily_flow_total(flow, "tech")
    tech_today = float(tech.iloc[-1]) if len(tech) else None
    tech_5d = _sum_last_n(tech, n_day_window)

    today_delta = f"今日 · {streak}" if streak else "今日"
    return [
        {
            "label": "全市场 ETF 今日净流入",
            "value": _fmt_yi(today),
            "delta": f"{today_delta}（亿元，+流入 / −流出）",
            "tone": _tone(today),
        },
        {
            "label": f"全市场 ETF 近 {n_day_window} 日累计",
            "value": _fmt_yi(total_5d),
            "delta": f"近 {m_day_window} 日累计 {_fmt_yi(total_20d)} 亿",
            "tone": _tone(total_5d),
        },
        {
            "label": "国家队（汇金）今日",
            "value": _fmt_yi(huijin_today),
            "delta": f"近 {n_day_window} 日 {_fmt_yi(huijin_5d)} 亿 · 50/300/500",
            "tone": _tone(huijin_today),
        },
        {
            "label": "科技 / TMT 今日",
            "value": _fmt_yi(tech_today),
            "delta": f"近 {n_day_window} 日 {_fmt_yi(tech_5d)} 亿 · 半导体/芯片",
            "tone": _tone(tech_today),
        },
    ]


# ============ Margin 派生量 ============


def _rzye_series(margin_agg: pd.DataFrame) -> pd.Series:
    """全市场（ALL）融资余额时间序列（元），trade_date 升序。"""
    if margin_agg.empty or "exchange_id" not in margin_agg.columns:
        return pd.Series(dtype=float)
    all_rows = margin_agg[margin_agg["exchange_id"] == "ALL"]
    if all_rows.empty:
        return pd.Series(dtype=float)
    return all_rows.set_index("trade_date")["rzye"].sort_index()


def _change_last_n(series: pd.Series, n: int) -> float | None:
    """最近 n 个观测的变化量（最新 − 第 n 个之前）；历史不足返回 None。"""
    if len(series) <= n:
        return None
    return float(series.iloc[-1] - series.iloc[-1 - n])


def build_margin_summary_cards(margin_agg: pd.DataFrame) -> list[dict[str, Any]]:
    """2 张融资卡片：余额水平 + 日变化；5 日变化 + 20 日对照。

    融资余额的绝对水平无多空含义，变化方向才是信号：
    日度（短线情绪）、5 日（一周杠杆节奏）、20 日（中期趋势）三层对照。
    """
    rzye = _rzye_series(margin_agg)
    if rzye.empty:
        return [
            {"label": "全市场融资余额", "value": "—", "delta": "数据不可得"},
            {"label": "融资余额 5 日变化", "value": "—", "delta": "数据不可得"},
        ]

    latest = float(rzye.iloc[-1])
    daily = _change_last_n(rzye, 1)
    weekly = _change_last_n(rzye, 5)
    monthly = _change_last_n(rzye, 20)

    return [
        {
            "label": "全市场融资余额",
            "value": f"{latest / _YI:.0f}",
            "delta": f"今日 {_fmt_yi(daily)} 亿",
            "tone": _tone(daily),
        },
        {
            "label": "融资余额 5 日变化",
            "value": _fmt_yi(weekly),
            "delta": f"20 日变化 {_fmt_yi(monthly)} 亿",
            "tone": _tone(weekly),
        },
    ]


# ============ 基差派生量 ============


def _basis_change(df: pd.DataFrame, n: int) -> float | None:
    """基差相对 n 个交易日前的变化（bp）：负值 = 贴水走阔。"""
    if len(df) <= n:
        return None
    latest = float(df["basis_points"].iloc[-1])
    prev = float(df["basis_points"].iloc[-1 - n])
    return latest - prev


def _basis_change_text(chg: float | None) -> str:
    if chg is None or pd.isna(chg):
        return "—"
    if chg > 0:
        return f"收敛 {abs(chg):.1f}bp"
    if chg < 0:
        return f"走阔 {abs(chg):.1f}bp"
    return "持平"


def build_basis_summary_cards(
    basis_ic: pd.DataFrame, basis_im: pd.DataFrame,
) -> list[dict[str, Any]]:
    """IC / IM 基差卡片：主数值为最新基差，delta 突出贴水走阔/收敛。

    IC/IM 常年贴水（对冲需求 + 分红），绝对水平信息量低；
    投资者关心的是边际变化：贴水收敛 = 对冲压力缓解（偏多信号，红），
    贴水走阔 = 对冲需求上升（偏空信号，绿）。
    """
    def _cards(df: pd.DataFrame, name: str) -> dict[str, Any]:
        if df.empty or "basis_points" not in df.columns:
            return {"label": f"{name} 最新基差", "value": "—", "delta": "数据不可得"}
        series = df.sort_values("trade_date")
        latest = float(series["basis_points"].iloc[-1])
        chg5 = _basis_change(series, 5)
        chg20 = _basis_change(series, 20)
        return {
            "label": f"{name} 最新基差",
            "value": f"{latest:.1f}",
            "delta": f"5日{_basis_change_text(chg5)} · 20日{_basis_change_text(chg20)}",
            "tone": _tone(chg5),  # 收敛/升水 → positive(红)
        }

    return [_cards(basis_ic, "IC（中证 500）"), _cards(basis_im, "IM（中证 1000）")]


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
