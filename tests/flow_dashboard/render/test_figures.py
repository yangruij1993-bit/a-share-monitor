"""figures 工厂测试。"""
from __future__ import annotations

import pandas as pd

from flow_dashboard.render.figures import (
    bar_flow_panel,
    line_cumulative_panel,
    stacked_bar_breakdown_panel,
    horizontal_topn_panel,
    multi_line_period_panel,
    dual_subplot_basis_panel,
)


def _flow_df():
    return pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "label": "huijin",
         "etf_estimated_flow_cny": 1e9},
        {"trade_date": pd.Timestamp("2026-08-08"), "label": "huijin",
         "etf_estimated_flow_cny": -0.5e9},
    ])


def test_bar_flow_panel_returns_figure_with_color_split():
    fig = bar_flow_panel(
        _flow_df(), title="汇金宽基日度流量", data_date="2026-08-12",
        coverage=1.0, last_success_at="2026-08-12 19:30",
    )
    assert fig.data  # 有 trace
    # 正负柱分别着色
    colors = list(fig.data[0].marker.color)
    assert len(colors) == 2  # 一正一负


def test_line_cumulative_panel_y_axis_in_yi():
    df = pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "cumulative_flow_cny": 1e9},
    ])
    fig = line_cumulative_panel(
        df, title="累计", data_date="2026-08-12", y_unit="亿元",
    )
    assert fig.layout.yaxis.title.text == "亿元"


def test_stacked_bar_breakdown_panel_has_multi_traces():
    df = pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "label": "A", "etf_estimated_flow_cny": 1e9},
        {"trade_date": pd.Timestamp("2026-08-07"), "label": "B", "etf_estimated_flow_cny": 2e9},
    ])
    fig = stacked_bar_breakdown_panel(df, title="分类", data_date="2026-08-12")
    assert len(fig.data) == 2  # 两个 label 两个 trace


def test_horizontal_topn_panel_sorts_desc():
    df = pd.DataFrame([
        {"ts_code": "A", "etf_estimated_flow_cny": 1e9},
        {"ts_code": "B", "etf_estimated_flow_cny": 3e9},
        {"ts_code": "C", "etf_estimated_flow_cny": 2e9},
    ])
    fig = horizontal_topn_panel(df, title="TOP", data_date="2026-08-12", topn=15)
    # x = 流量，应按绝对值降序
    x_vals = list(fig.data[0].x)
    assert abs(x_vals[0]) >= abs(x_vals[-1])


def test_multi_line_period_panel_one_trace_per_label():
    df = pd.DataFrame([
        {"period_start": pd.Timestamp("2026-08-03"), "label": "broad", "etf_estimated_flow_cny": 1e9},
        {"period_start": pd.Timestamp("2026-08-10"), "label": "broad", "etf_estimated_flow_cny": 1.5e9},
        {"period_start": pd.Timestamp("2026-08-03"), "label": "tech", "etf_estimated_flow_cny": 0.5e9},
    ])
    fig = multi_line_period_panel(df, title="周度", data_date="2026-08-12")
    assert len(fig.data) == 2  # broad + tech


def test_dual_subplot_basis_panel_has_two_rows():
    ic = pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "ts_code": "IC2608.CFX",
         "basis_points": 18.2, "annualized_discount_rate": 0.47},
    ])
    im = pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "ts_code": "IM2608.CFX",
         "basis_points": 22.1, "annualized_discount_rate": 0.55},
    ])
    fig = dual_subplot_basis_panel(ic, im, data_date="2026-08-12")
    # 2 subplot rows
    assert "yaxis2" in str(fig.layout)


def test_horizontal_topn_panel_handles_nan_flow_without_crash():
    """NaN flow values must not raise (defensive against upstream gaps)."""
    df = pd.DataFrame([
        {"ts_code": "A", "etf_estimated_flow_cny": 1e9},
        {"ts_code": "B", "etf_estimated_flow_cny": float("nan")},
        {"ts_code": "C", "etf_estimated_flow_cny": -2e9},
    ])
    fig = horizontal_topn_panel(df, title="TOP", data_date="2026-08-12", topn=15)
    assert len(fig.data) == 1


def test_line_cumulative_panel_converts_y_to_yi():
    """1e9 元 → 10 亿元; verifies the _to_yi conversion is wired up."""
    df = pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "cumulative_flow_cny": 1e9},
    ])
    fig = line_cumulative_panel(df, title="累计", data_date="2026-08-12")
    assert list(fig.data[0].y) == [10.0]
