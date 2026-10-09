"""s2_flow_aggregation 契约测试。"""
from __future__ import annotations

import pandas as pd
import pytest

from flow_dashboard.indicators.flow_aggregation import (
    aggregate_weekly_flow,
    aggregate_monthly_flow,
    cumulative_flow_ytd,
    cumulative_flow_3y,
    dedup_flow_by_etf_day,
    normalize_asset_scope,
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


def test_dedup_flow_by_etf_day_keeps_one_row_per_etf_day():
    """explode 后同一 (ts_code, trade_date) 多标签行只保留一行。"""
    day = pd.Timestamp("2026-08-07")
    df = pd.DataFrame([
        {"trade_date": day, "ts_code": "510050.SH", "label": "huijin",
         "dimension": "ownership", "etf_estimated_flow_cny": 1e8},
        {"trade_date": day, "ts_code": "510050.SH", "label": "broad",
         "dimension": "asset_scope", "etf_estimated_flow_cny": 1e8},
        {"trade_date": day, "ts_code": "510050.SH", "label": "csi50",
         "dimension": "benchmark", "etf_estimated_flow_cny": 1e8},
        {"trade_date": day, "ts_code": "512480.SH", "label": "tech",
         "dimension": "asset_scope", "etf_estimated_flow_cny": 2e8},
    ])
    out = dedup_flow_by_etf_day(df)
    assert len(out) == 2
    assert set(out["ts_code"]) == {"510050.SH", "512480.SH"}


def test_normalize_asset_scope_merged_two_categories():
    """合并模式：tech/cycle→industry、growth→broad，只剩宽基/行业两类。"""
    day = pd.Timestamp("2026-08-07")
    df = pd.DataFrame([
        {"trade_date": day, "ts_code": "159915.SZ", "label": "growth",
         "dimension": "asset_scope", "etf_estimated_flow_cny": 1e8},
        {"trade_date": day, "ts_code": "159915.SZ", "label": "broad",
         "dimension": "asset_scope", "etf_estimated_flow_cny": 1e8},
        {"trade_date": day, "ts_code": "512480.SH", "label": "tech",
         "dimension": "asset_scope", "etf_estimated_flow_cny": 2e8},
        {"trade_date": day, "ts_code": "515220.SH", "label": "cycle",
         "dimension": "asset_scope", "etf_estimated_flow_cny": 3e8},
        {"trade_date": day, "ts_code": "512660.SH", "label": "industry",
         "dimension": "asset_scope", "etf_estimated_flow_cny": 4e8},
    ])
    out = normalize_asset_scope(df)
    # 创业板双标签去重为一行
    assert len(out) == 4
    assert set(out["label"]) == {"broad", "industry"}
    broad_sum = out[out["label"] == "broad"]["etf_estimated_flow_cny"].sum()
    ind_sum = out[out["label"] == "industry"]["etf_estimated_flow_cny"].sum()
    assert broad_sum == pytest.approx(1e8)  # growth+broad 只计一次
    assert ind_sum == pytest.approx(2e8 + 3e8 + 4e8)  # tech/cycle/industry


def test_normalize_asset_scope_detail_four_categories():
    """细分模式：宽基 / 行业(传统 industry_core) / 科技 / 周期 四类。"""
    day = pd.Timestamp("2026-08-07")
    df = pd.DataFrame([
        {"trade_date": day, "ts_code": "159915.SZ", "label": "growth",
         "dimension": "asset_scope", "etf_estimated_flow_cny": 1e8},
        {"trade_date": day, "ts_code": "159915.SZ", "label": "broad",
         "dimension": "asset_scope", "etf_estimated_flow_cny": 1e8},
        {"trade_date": day, "ts_code": "512480.SH", "label": "tech",
         "dimension": "asset_scope", "etf_estimated_flow_cny": 2e8},
        {"trade_date": day, "ts_code": "512660.SH", "label": "industry",
         "dimension": "asset_scope", "etf_estimated_flow_cny": 4e8},
    ])
    out = normalize_asset_scope(df, merge_subcategories=False)
    assert set(out["label"]) == {"broad", "industry_core", "tech"}
    assert len(out) == 3  # 创业板去重
