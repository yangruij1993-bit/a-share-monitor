"""基差面板测试。"""
from __future__ import annotations

import pandas as pd

from flow_dashboard.render.panels_basis import render_basis_panel


def _basis_df(prefix: str):
    return pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "ts_code": f"{prefix}2608.CFX",
         "basis_points": 18.2, "annualized_discount_rate": 0.47,
         "quality_flags": "quote_time_unverified"},
        {"trade_date": pd.Timestamp("2026-08-08"), "ts_code": f"{prefix}2608.CFX",
         "basis_points": 22.1, "annualized_discount_rate": 0.55,
         "quality_flags": "quote_time_unverified"},
    ])


def test_render_basis_panel_returns_html_with_ic_im():
    html = render_basis_panel(
        ic_df=_basis_df("IC"), im_df=_basis_df("IM"),
        data_date="2026-08-12", coverage=1.0, last_success_at="19:30",
        layer="eod",
    )
    assert "IC" in html and "IM" in html
    assert "基差" in html
    assert 'id="panel-basis"' in html


def test_render_basis_panel_intraday_layer_marked_preview():
    html = render_basis_panel(
        ic_df=_basis_df("IC"), im_df=_basis_df("IM"),
        data_date="2026-08-12", coverage=None, last_success_at="14:30",
        layer="intraday",
    )
    assert "盘中" in html or "preview" in html.lower() or "预览" in html


def test_render_basis_panel_empty_gracefully():
    empty = pd.DataFrame(columns=["trade_date", "ts_code", "basis_points"])
    html = render_basis_panel(
        ic_df=empty, im_df=empty, data_date="2026-08-12",
        coverage=None, last_success_at=None, layer="eod",
    )
    assert "stale" in html.lower() or "数据不可得" in html
