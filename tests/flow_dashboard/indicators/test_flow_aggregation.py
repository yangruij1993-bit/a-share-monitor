"""s2_flow_aggregation 契约测试。"""
from __future__ import annotations

import pandas as pd
import pytest

from flow_dashboard.indicators.flow_aggregation import (
    aggregate_weekly_flow,
    aggregate_monthly_flow,
    cumulative_flow_ytd,
    cumulative_flow_3y,
)


def _flow_rows():
    return pd.DataFrame([
        {"dimension": "ownership", "label": "huijin",
         "trade_date": pd.Timestamp("2026-08-07"),
         "ts_code": "510050.SH", "etf_estimated_flow_cny": 1e9,
         "share_in_shares": 100e8, "total_size_cny": 100e8 * 3},
        {"dimension": "ownership", "label": "huijin",
         "trade_date": pd.Timestamp("2026-08-08"),
         "ts_code": "510050.SH", "etf_estimated_flow_cny": -0.5e9,
         "share_in_shares": 95e8, "total_size_cny": 95e8 * 3.1},
    ])


def test_aggregate_weekly_flow_sums_within_iso_week():
    df = _flow_rows()  # 2026-08-07, 2026-08-08 同属 ISO W32
    out = aggregate_weekly_flow(df)
    assert len(out) == 1
    assert out.iloc[0]["etf_estimated_flow_cny"] == pytest.approx(0.5e9)
    assert "week_start" in out.columns


def test_aggregate_monthly_flow_sums_within_calendar_month():
    df = pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-07-31"),
         "ts_code": "X", "etf_estimated_flow_cny": 1e9,
         "share_in_shares": 100e8, "total_size_cny": 100e8 * 3,
         "dimension": "ownership", "label": "huijin"},
        {"trade_date": pd.Timestamp("2026-08-01"),
         "ts_code": "X", "etf_estimated_flow_cny": 0.5e9,
         "share_in_shares": 105e8, "total_size_cny": 105e8 * 3.1,
         "dimension": "ownership", "label": "huijin"},
    ])
    out = aggregate_monthly_flow(df)
    assert len(out) == 2  # 7月、8月
    jul = out[out["month_start"] == pd.Timestamp("2026-07-01")].iloc[0]
    aug = out[out["month_start"] == pd.Timestamp("2026-08-01")].iloc[0]
    assert jul["etf_estimated_flow_cny"] == pytest.approx(1e9)
    assert aug["etf_estimated_flow_cny"] == pytest.approx(0.5e9)


def test_cumulative_flow_ytd_sums_within_calendar_year():
    df = pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-01-31"),
         "ts_code": "X", "etf_estimated_flow_cny": 1e9,
         "share_in_shares": 100e8, "total_size_cny": 100e8 * 3,
         "dimension": "ownership", "label": "huijin"},
        {"trade_date": pd.Timestamp("2026-08-07"),
         "ts_code": "X", "etf_estimated_flow_cny": 0.5e9,
         "share_in_shares": 105e8, "total_size_cny": 105e8 * 3,
         "dimension": "ownership", "label": "huijin"},
    ])
    out = cumulative_flow_ytd(df)
    assert len(out) == 1
    assert out.iloc[0]["cumulative_flow_cny"] == pytest.approx(1.5e9)


def test_cumulative_flow_ytd_gated_when_coverage_below_threshold():
    """coverage_gates 未冻结（None）时，cumulative_flow_ytd 返回空 df + 注解。"""
    df = _flow_rows()
    out = cumulative_flow_ytd(df, coverage_gate=None)
    assert len(out) == 0
    # 不在数据上撒谎：返回空，不返回伪累计


def test_cumulative_flow_3y_returns_window_3_years():
    df = pd.DataFrame([
        {"trade_date": pd.Timestamp("2024-01-15"),
         "ts_code": "X", "etf_estimated_flow_cny": 1e9,
         "share_in_shares": 100e8, "total_size_cny": 100e8 * 3,
         "dimension": "ownership", "label": "huijin"},
        {"trade_date": pd.Timestamp("2026-08-07"),
         "ts_code": "X", "etf_estimated_flow_cny": 0.5e9,
         "share_in_shares": 105e8, "total_size_cny": 105e8 * 3,
         "dimension": "ownership", "label": "huijin"},
    ])
    out = cumulative_flow_3y(df, as_of=pd.Timestamp("2026-08-12"), coverage_gate=None)
    # gate=None → 返回空
    assert len(out) == 0
