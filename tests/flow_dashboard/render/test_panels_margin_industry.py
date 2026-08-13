# tests/flow_dashboard/render/test_panels_margin_industry.py
"""个股两融行业热力图面板 renderer 测试。"""
from __future__ import annotations

import pandas as pd
import pytest

from flow_dashboard.render.panels_margin_industry import (
    render_margin_industry_heatmap,
)


def _industry_df(n_days: int = 5):
    rows = []
    base = pd.Timestamp("2026-08-05")
    for d_offset in range(n_days):
        for ind_code, ind_name in [("801770", "银行"), ("801780", "非银金融")]:
            rows.append({
                "trade_date": base + pd.Timedelta(days=d_offset),
                "industry_code": ind_code,
                "industry_name": ind_name,
                "rzye": 1e9, "rqye": 1e8, "net_margin": 9e8,
                "stock_count": 5,
                "net_margin_5d_change": 1e8 if d_offset >= 4 else None,
            })
    return pd.DataFrame(rows)


def test_render_margin_industry_heatmap_basic():
    html = render_margin_industry_heatmap(
        _industry_df(),
        data_date="2026-08-12",
        coverage=0.95, last_success_at="19:30",
    )
    assert "申万 L1 行业资金" in html
    assert "<table" in html  # 新版用 HTML 表格替代 Plotly heatmap
    assert 'id="panel-margin-industry-heatmap"' in html


def test_render_margin_industry_heatmap_empty_df_stale():
    empty = pd.DataFrame(columns=[
        "trade_date", "industry_code", "industry_name",
        "rzye", "rqye", "net_margin", "stock_count", "net_margin_5d_change",
    ])
    html = render_margin_industry_heatmap(
        empty, data_date="2026-08-12",
        coverage=None, last_success_at=None,
    )
    assert "stale" in html.lower() or "数据不可得" in html
    assert "<table" not in html


def test_render_margin_industry_heatmap_coverage_none_stale():
    """df 有数据但 coverage=None（上游未冻结）也应 stale。"""
    html = render_margin_industry_heatmap(
        _industry_df(), data_date="2026-08-12",
        coverage=None, last_success_at="19:30",
    )
    assert "stale" in html.lower() or "数据不可得" in html
