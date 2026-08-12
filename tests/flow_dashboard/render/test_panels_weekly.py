"""4 个周度 ETF 面板测试。"""
from __future__ import annotations

import pandas as pd

from flow_dashboard.render.panels_weekly import (
    render_broad_weekly,
    render_industry_theme_weekly,
    render_category_cumulative_weekly,
    render_monthly_total,
)


def _weekly_df(label: str):
    return pd.DataFrame([
        {"period_start": pd.Timestamp("2026-08-03"), "label": label,
         "etf_estimated_flow_cny": 1e9},
        {"period_start": pd.Timestamp("2026-08-10"), "label": label,
         "etf_estimated_flow_cny": 1.5e9},
    ])


KW = dict(data_date="2026-08-12", coverage=0.95, last_success_at="19:30")


def test_render_broad_weekly():
    html = render_broad_weekly(_weekly_df("broad"), **KW)
    assert "宽基" in html and "周度" in html


def test_render_industry_theme_weekly():
    html = render_industry_theme_weekly(_weekly_df("industry"), **KW)
    assert "行业" in html and "周度" in html


def test_render_category_cumulative_weekly():
    df = pd.concat([_weekly_df("broad"), _weekly_df("industry"), _weekly_df("tech")])
    html = render_category_cumulative_weekly(df, **KW)
    assert "累计" in html or "分类" in html


def test_render_monthly_total():
    df = pd.DataFrame([
        {"month_start": pd.Timestamp("2026-07-01"), "label": "broad",
         "etf_estimated_flow_cny": 5e9},
        {"month_start": pd.Timestamp("2026-08-01"), "label": "broad",
         "etf_estimated_flow_cny": 3e9},
    ])
    html = render_monthly_total(df, **KW)
    assert "月度" in html or "月合计" in html


def test_render_weekly_empty_df_gracefully():
    empty = pd.DataFrame(columns=["period_start", "label", "etf_estimated_flow_cny"])
    html = render_broad_weekly(empty, data_date="2026-08-12",
                               coverage=None, last_success_at=None)
    assert "stale" in html.lower() or "数据不可得" in html


def test_render_broad_weekly_label_mismatch_shows_stale():
    """df 非空但 label 过滤后无行：面板应 stale（守护 Task 9 修复的同类 bug）。"""
    df = _weekly_df("industry")  # 无 broad 标签
    html = render_broad_weekly(df, **KW)
    assert "stale" in html.lower() or "数据不可得" in html
    assert "Plotly.newPlot" not in html
