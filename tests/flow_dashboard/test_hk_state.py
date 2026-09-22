"""hk_short_state：§6.4 状态矩阵、阈值边界、SFC 降级、宽限期。"""

import pandas as pd

from flow_dashboard.indicators import hk_short_state as st
from flow_dashboard.indicators.hk_short_state import Evidence


def _ev(**kw):
    base = {
        "oi": "unavailable",
        "short_high": False,
        "ssr_high": False,
        "price": "neutral",
        "participation_high": False,
        "sfc_pending": False,
        "etf_interference": False,
    }
    base.update(kw)
    return Evidence(**base)


def test_state_adding_all_conditions():
    ev = _ev(
        oi="up", short_high=True, ssr_high=True, price="down", participation_high=True
    )
    assert st._classify(ev)["state"] == "空头净加仓迹象明显"


def test_state_divergence_oi_up_price_up():
    ev = _ev(oi="up", price="up")
    assert st._classify(ev)["state"] == "多空分歧扩大"


def test_state_covering_oi_down_price_up_participation():
    ev = _ev(oi="down", price="up", participation_high=True)
    out = st._classify(ev)
    assert out["state"] == "空头净回补迹象明显"
    assert out["notes"] == []  # 沽空额不高 → 无附加注
    out2 = st._classify(
        _ev(oi="down", price="up", participation_high=True, short_high=True)
    )
    assert st.COVER_NOTE in out2["notes"]  # 回补但沽空额高 → 注明博弈


def test_state_active_but_flat_oi():
    ev = _ev(oi="flat", short_high=True, ssr_high=True)
    assert st._classify(ev)["state"] == "沽空活跃但净仓变化有限"


def test_state_fall_with_oi_down_note():
    # 价跌 + 淡仓↓ 但无参与度 → 未命中回补 → 无法确认 + 长仓卖盘注
    out = st._classify(_ev(oi="down", price="down"))
    assert out["state"] == "暂时无法确认"
    assert st.FALL_NOTE in out["notes"]


def test_oi_unavailable_blocks_directional_states():
    # 淡仓↑ + 价涨本应"多空分歧扩大"，但 SFC unavailable → 无法确认
    out = st._classify(_ev(oi="unavailable", price="up"))
    assert out["state"] == "暂时无法确认"
    # 沽空额高 + SSR 高 + oi unavailable → 不输出"活跃但净仓有限"？§6.4 该状态
    # 要求 淡仓Δ≈0（flat），unavailable 不等于 ≈0 → 无法确认
    out2 = st._classify(_ev(oi="unavailable", short_high=True, ssr_high=True))
    assert out2["state"] == "暂时无法确认"


def test_etf_note_added_without_changing_state():
    out = st._classify(
        _ev(oi="flat", short_high=True, ssr_high=True, etf_interference=True)
    )
    assert out["state"] == "沽空活跃但净仓变化有限"
    assert st.ETF_HEDGE_NOTE in out["notes"]


def test_market_conclusion_thresholds_and_suffix():
    out = st.market_conclusion(
        sfc={"available": True, "delta_bps": 4.0, "breadth": 0.56},
        weekly_short_intensity=1.25,  # == 阈值 → short_high（>=）
        ssr_percentile=80.0,  # == 阈值 → ssr_high（>=）
        price="down",
        participation_high=True,
    )
    assert out["state"] == "空头净加仓迹象明显"  # delta 4.0 > 3 且 breadth 0.56 >= 0.55
    # delta 恰为 +3bp 且 breadth 恰为 0.55 → 仍算 up（>=）
    out2 = st.market_conclusion(
        sfc={"available": True, "delta_bps": 3.0, "breadth": 0.55},
        weekly_short_intensity=1.24,
        ssr_percentile=79.9,
        price="down",
        participation_high=True,
    )
    # oi=up 但强度/分位不足 → 不满足加仓五条件，也不满足其余 → 无法确认
    assert out2["state"] == "暂时无法确认"
    # sfc_pending → 后缀
    out3 = st.market_conclusion(sfc=None, sfc_pending=True)
    assert out3["state"].endswith(st.SFC_PENDING_SUFFIX)


def test_market_oi_direction_bands():
    t = {
        "mkt_sfc_delta_bp": 3.0,
        "mkt_sfc_breadth_pos": 0.55,
        "mkt_sfc_breadth_neg": 0.45,
    }
    assert (
        st._market_oi({"available": True, "delta_bps": 5.0, "breadth": 0.6}, t) == "up"
    )
    assert (
        st._market_oi({"available": True, "delta_bps": -5.0, "breadth": 0.4}, t)
        == "down"
    )
    # delta +4bp 但 breadth 0.50（<0.55）→ 不算 up → flat
    assert (
        st._market_oi({"available": True, "delta_bps": 4.0, "breadth": 0.50}, t)
        == "flat"
    )
    # delta -4bp 但 breadth 0.50（>0.45）→ 不算 down → flat
    assert (
        st._market_oi({"available": True, "delta_bps": -4.0, "breadth": 0.50}, t)
        == "flat"
    )
    assert st._market_oi({"available": False}, t) == "unavailable"
    assert st._market_oi(None, t) == "unavailable"


def test_stock_conclusion_and_oi_bands():
    t = {"stock_sfc_delta_bp": 5.0}
    assert st._stock_oi({"available": True, "delta_bp": 5.0}, t) == "up"  # >=
    assert st._stock_oi({"available": True, "delta_bp": -5.0}, t) == "down"  # <=
    assert st._stock_oi({"available": True, "delta_bp": 4.99}, t) == "flat"
    out = st.stock_conclusion(
        sfc={"available": True, "delta_bp": 6.0},
        weekly_short_intensity=1.30,
        ssr_percentile=85.0,
        price="down",
        participation_high=True,
    )
    assert out["state"] == "空头净加仓迹象明显"


def test_sfc_is_pending_grace_window():
    # 缺失的下一个应公布周 = 09-18（最新已完成周），其宽限期至 09-25 EOD
    cached = pd.Timestamp("2026-09-11")
    # 09-21（宽限期内，09-18 报告未超宽限期）→ 不 pending（与 Task 14 一致）
    assert not st.sfc_is_pending(
        latest_cached_pd=cached,
        as_of=pd.Timestamp("2026-09-21 18:45", tz="Asia/Shanghai"),
    )
    # 09-28（09-18 宽限期已过仍缺）→ pending
    assert st.sfc_is_pending(
        latest_cached_pd=cached,
        as_of=pd.Timestamp("2026-09-28 18:45", tz="Asia/Shanghai"),
    )
    # 09-16（本周五 09-18 未结束，最新已完成周=09-11，缓存已含）→ 不 pending
    assert not st.sfc_is_pending(
        latest_cached_pd=cached,
        as_of=pd.Timestamp("2026-09-16 10:00", tz="Asia/Shanghai"),
    )
    # 缓存已含最新周（09-18）→ 不 pending
    assert not st.sfc_is_pending(
        latest_cached_pd=pd.Timestamp("2026-09-18"),
        as_of=pd.Timestamp("2026-09-21 18:45", tz="Asia/Shanghai"),
    )
    # 无任何缓存 → pending（数据缺失）
    assert st.sfc_is_pending(
        latest_cached_pd=None,
        as_of=pd.Timestamp("2026-09-21 18:45", tz="Asia/Shanghai"),
    )
