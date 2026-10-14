"""panels_summary 契约测试：卡片必须突出短/中期变化与语境。"""
from __future__ import annotations

import pandas as pd

from flow_dashboard.render.panels_summary import (
    build_basis_summary_cards,
    build_etf_summary_cards,
    build_margin_summary_cards,
    render_summary_section,
)


_YI = 1e8


def _flow_df(dates: list[str], totals: list[float], label: str = "broad") -> pd.DataFrame:
    rows = []
    for d, v in zip(dates, totals):
        rows.append({
            "trade_date": pd.Timestamp(d), "label": label,
            "etf_estimated_flow_cny": v,
        })
    return pd.DataFrame(rows)


def test_etf_cards_show_streak_and_multi_window():
    dates = [f"2026-07-{d:02d}" for d in range(13, 28)] + [
        "2026-08-01", "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07"
    ]
    # 连续 5 日净流出，5 日累计 -50 亿
    totals = [10e8] * 15 + [-5e8, -10e8, -10e8, -10e8, -15e8]
    flow = _flow_df(dates, totals)
    cards = build_etf_summary_cards(flow)
    assert cards[0]["delta"].startswith("今日 · 连续第 5 日净流出")
    assert cards[1]["value"] == "-50.0"
    assert "近 20 日累计" in cards[1]["delta"]
    assert cards[0]["tone"] == "negative"


def test_etf_cards_do_not_show_zero_when_today_nav_missing():
    flow = _flow_df(["2026-10-12", "2026-10-13"], [10e8, float("nan")])
    cards = build_etf_summary_cards(flow)
    assert cards[0]["value"] == "—"


def test_margin_cards_show_daily_and_20d_change():
    dates = [f"2026-07-{d:02d}" for d in range(6, 31)] + [
        "2026-08-04", "2026-08-05", "2026-08-06", "2026-08-07"
    ]
    base = [26000e8] * len(dates)
    base[-1] += 100e8   # 今日 +100 亿
    base[-6] -= 50e8    # 5 日前低点 → 5 日变化 +150 亿
    base[-21] -= 200e8  # 20 日前更低 → 20 日变化 +300 亿
    margin = pd.DataFrame({
        "trade_date": pd.DatetimeIndex([pd.Timestamp(d) for d in dates]),
        "exchange_id": ["ALL"] * len(dates),
        "rzye": base,
    })
    cards = build_margin_summary_cards(margin)
    assert cards[0]["delta"] == "今日 +100.0 亿"
    assert cards[1]["value"] == "+150.0"
    assert "20 日变化 +300.0 亿" in cards[1]["delta"]
    assert cards[0]["tone"] == "positive"


def test_basis_cards_emphasize_convergence_or_widening():
    # 贴水走阔场景：最新 -30bp，5 日前 -20bp → 走阔
    ic = pd.DataFrame({
        "trade_date": pd.DatetimeIndex([pd.Timestamp(d) for d in
            [f"2026-08-{d:02d}" for d in range(2, 14)]]),
        "basis_points": [-20.0] * 9 + [-25.0, -28.0, -30.0],
    })
    # 贴水收敛场景：最新 -10bp，5 日前 -25bp → 收敛
    im = pd.DataFrame({
        "trade_date": pd.DatetimeIndex([pd.Timestamp(d) for d in
            [f"2026-08-{d:02d}" for d in range(2, 14)]]),
        "basis_points": [-25.0] * 9 + [-20.0, -15.0, -10.0],
    })
    cards = build_basis_summary_cards(ic, im)
    assert cards[0]["value"] == "-30.0"
    assert "走阔" in cards[0]["delta"]
    assert cards[0]["tone"] == "negative"   # 贴水走阔 → 偏空（绿）
    assert "收敛" in cards[1]["delta"]
    assert cards[1]["tone"] == "positive"   # 贴水收敛 → 偏多（红）


def test_render_summary_section_renders_cards_row():
    flow = _flow_df(["2026-08-06", "2026-08-07"], [10e8, 20e8])
    margin = pd.DataFrame({
        "trade_date": pd.DatetimeIndex([pd.Timestamp("2026-08-06"), pd.Timestamp("2026-08-07")]),
        "exchange_id": ["ALL", "ALL"],
        "rzye": [26000e8, 26100e8],
    })
    basis = pd.DataFrame({
        "trade_date": pd.DatetimeIndex([pd.Timestamp("2026-08-06"), pd.Timestamp("2026-08-07")]),
        "basis_points": [-20.0, -18.0],
    })
    html = render_summary_section(
        flow=flow, margin_agg=margin, basis_ic=basis, basis_im=basis,
    )
    assert 'class="cards-row"' in html
    assert "全市场 ETF 今日净流入" in html
