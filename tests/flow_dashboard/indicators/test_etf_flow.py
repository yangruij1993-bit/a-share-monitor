"""s1_etf_flow 契约测试。"""
from __future__ import annotations

import pandas as pd
import pytest

from flow_dashboard.indicators.etf_flow import compute_etf_flow


def _row(ts_code, date, share, nav=None):
    return {
        "ts_code": ts_code,
        "trade_date": pd.Timestamp(date),
        "share_in_shares": share,
        "unit_nav": nav,
        "total_size_cny": share * (nav or 0),
        "quality_flags": "",
    }


def test_compute_etf_flow_basic():
    df = pd.DataFrame([
        _row("510050.SH", "2026-08-07", 100e8, nav=3.0),
        _row("510050.SH", "2026-08-08", 105e8, nav=3.1),
    ])
    out = compute_etf_flow(df)
    assert len(out) == 2
    # 第一行无前日，flow=NaN
    assert pd.isna(out.iloc[0]["etf_estimated_flow_cny"])
    # 第二行 flow = (105e8 - 100e8) × 3.1 = 5e8 × 3.1 = 1.55e9
    assert out.iloc[1]["etf_estimated_flow_cny"] == pytest.approx(1.55e9)


def test_compute_etf_flow_missing_nav_marks_flag():
    df = pd.DataFrame([
        _row("X", "2026-08-07", 100e8, nav=3.0),
        _row("X", "2026-08-08", 110e8, nav=None),  # nav 缺失
    ])
    out = compute_etf_flow(df)
    assert pd.isna(out.iloc[1]["etf_estimated_flow_cny"])
    assert "missing_nav" in out.iloc[1]["quality_flags"]


def test_compute_etf_flow_no_prior_share():
    """第一行无法算 flow；应标 no_prior_share。"""
    df = pd.DataFrame([
        _row("X", "2026-08-07", 100e8, nav=3.0),
    ])
    out = compute_etf_flow(df)
    assert pd.isna(out.iloc[0]["etf_estimated_flow_cny"])
    assert "no_prior_share" in out.iloc[0]["quality_flags"]


def test_compute_etf_flow_does_not_substitute_close_price():
    """spec §1.3 红线：禁止用 close 价代替 nav。"""
    df = pd.DataFrame([
        _row("X", "2026-08-07", 100e8, nav=3.0),
        _row("X", "2026-08-08", 110e8, nav=None),
    ])
    df.loc[1, "close"] = 3.2  # 故意提供 close，但不应被使用
    out = compute_etf_flow(df)
    assert pd.isna(out.iloc[1]["etf_estimated_flow_cny"])
    assert "missing_nav" in out.iloc[1]["quality_flags"]


def test_compute_etf_flow_per_ts_code():
    """多 ETF 必须分别按 ts_code 计算 t-1，不混淆。"""
    df = pd.DataFrame([
        _row("A", "2026-08-07", 100e8, nav=3.0),
        _row("B", "2026-08-07", 50e8, nav=5.0),
        _row("A", "2026-08-08", 110e8, nav=3.1),
        _row("B", "2026-08-08", 55e8, nav=5.0),
    ])
    out = compute_etf_flow(df)
    a_d2 = out[(out["ts_code"] == "A") & (out["trade_date"] == pd.Timestamp("2026-08-08"))].iloc[0]
    b_d2 = out[(out["ts_code"] == "B") & (out["trade_date"] == pd.Timestamp("2026-08-08"))].iloc[0]
    # A: (110-100)e8 × 3.1 = 3.1e9
    assert a_d2["etf_estimated_flow_cny"] == pytest.approx(3.1e9)
    # B: (55-50)e8 × 5.0 = 2.5e9
    assert b_d2["etf_estimated_flow_cny"] == pytest.approx(2.5e9)


def test_compute_etf_flow_suffix_invariant():
    """Red Line 1: 追加未来行不改变历史行。"""
    base = pd.DataFrame([
        _row("X", "2026-08-07", 100e8, nav=3.0),
        _row("X", "2026-08-08", 105e8, nav=3.1),
    ])
    suffix = pd.DataFrame([
        _row("X", "2026-08-09", 110e8, nav=3.2),
    ])
    out_base = compute_etf_flow(base).set_index("trade_date")
    out_full = compute_etf_flow(
        pd.concat([base, suffix], ignore_index=True)
    ).set_index("trade_date")
    common = out_base.index.intersection(out_full.index)
    pd.testing.assert_frame_equal(
        out_base.loc[common], out_full.loc[common], check_like=True,
    )
