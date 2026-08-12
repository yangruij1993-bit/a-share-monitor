"""覆盖率基线契约测试。"""
from __future__ import annotations

import pandas as pd
import pytest

from flow_dashboard.phase_a.coverage_baseline import compute_coverage_series


def _sample_flow():
    """3 ETF，2 天，第二天缺一只。"""
    return pd.DataFrame([
        {"ts_code": "A", "trade_date": pd.Timestamp("2026-08-07"),
         "dimension": "asset_scope", "label": "broad",
         "share_in_shares": 100e8, "total_size_cny": 100e8 * 5,
         "etf_estimated_flow_cny": 1e8},
        {"ts_code": "B", "trade_date": pd.Timestamp("2026-08-07"),
         "dimension": "asset_scope", "label": "broad",
         "share_in_shares": 200e8, "total_size_cny": 200e8 * 6,
         "etf_estimated_flow_cny": 2e8},
        {"ts_code": "C", "trade_date": pd.Timestamp("2026-08-07"),
         "dimension": "asset_scope", "label": "broad",
         "share_in_shares": 300e8, "total_size_cny": 300e8 * 7,
         "etf_estimated_flow_cny": -1e8},
        # 第二天 C 缺
        {"ts_code": "A", "trade_date": pd.Timestamp("2026-08-08"),
         "dimension": "asset_scope", "label": "broad",
         "share_in_shares": 100e8, "total_size_cny": 100e8 * 5,
         "etf_estimated_flow_cny": 0.5e8},
        {"ts_code": "B", "trade_date": pd.Timestamp("2026-08-08"),
         "dimension": "asset_scope", "label": "broad",
         "share_in_shares": 200e8, "total_size_cny": 200e8 * 6,
         "etf_estimated_flow_cny": -0.5e8},
    ])


def test_compute_coverage_series_count():
    df = _sample_flow()
    out = compute_coverage_series(df, universe=["A", "B", "C"])
    d1 = out[out["trade_date"] == pd.Timestamp("2026-08-07")].iloc[0]
    d2 = out[out["trade_date"] == pd.Timestamp("2026-08-08")].iloc[0]
    assert d1["count_coverage"] == pytest.approx(1.0)
    assert d2["count_coverage"] == pytest.approx(2 / 3)


def test_compute_coverage_series_prior_share():
    df = _sample_flow()
    out = compute_coverage_series(df, universe=["A", "B", "C"])
    d2 = out[out["trade_date"] == pd.Timestamp("2026-08-08")].iloc[0]
    assert d2["prior_share_coverage"] == pytest.approx(300e8 / 600e8)


def test_compute_coverage_series_prior_aum():
    df = _sample_flow()
    out = compute_coverage_series(df, universe=["A", "B", "C"])
    d2 = out[out["trade_date"] == pd.Timestamp("2026-08-08")].iloc[0]
    assert d2["prior_aum_coverage"] == pytest.approx(1700e8 / 3800e8)
