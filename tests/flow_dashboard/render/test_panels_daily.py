"""9 个日度 ETF 面板测试。"""
from __future__ import annotations

import pandas as pd
import pytest

from flow_dashboard.render.panels_daily import (
    render_huijin_broad_daily,
    render_tech_tmt_daily,
    render_total_market_daily,
    render_broad_daily,
    render_industry_theme_daily,
    render_category_cumulative_daily,
    render_cycle_daily,
    render_cycle_cumulative_daily,
    render_top15_etf_daily,
)


def _flow_df(labels: list[str], n_days: int = 5):
    rows = []
    base = pd.Timestamp("2026-08-05")
    for label in labels:
        for i in range(n_days):
            rows.append({
                "trade_date": base + pd.Timedelta(days=i),
                "ts_code": f"X{i}.{label}",
                "label": label,
                "etf_estimated_flow_cny": (i + 1) * 1e8 * (1 if label != "tech" else -1),
                "share_in_shares": 100e8,
                "total_size_cny": 100e8 * 3,
                "cumulative_flow_cny": (i + 1) * 1e8,
                "dimension": "ownership",
            })
    return pd.DataFrame(rows)


PANEL_KWARGS = dict(data_date="2026-08-12", coverage=1.0, last_success_at="19:30")


def test_render_huijin_broad_daily_returns_html_fragment():
    df = _flow_df(["huijin"])
    html = render_huijin_broad_daily(df, **PANEL_KWARGS)
    assert "汇金" in html  # 标题含「汇金」
    assert "Plotly.newPlot" in html
    assert 'id="panel-huijin-broad-daily"' in html


def test_render_tech_tmt_daily_returns_html_fragment():
    df = _flow_df(["tech"])
    html = render_tech_tmt_daily(df, **PANEL_KWARGS)
    assert "科技" in html or "TMT" in html


def test_render_total_market_daily_returns_html_fragment():
    df = _flow_df(["broad", "industry", "tech"])
    html = render_total_market_daily(df, **PANEL_KWARGS)
    assert "全市场合计" in html or "合计" in html


def test_render_broad_daily_returns_html_fragment():
    df = _flow_df(["broad"])
    html = render_broad_daily(df, **PANEL_KWARGS)
    assert "宽基" in html


def test_render_industry_theme_daily_returns_html_fragment():
    df = _flow_df(["industry"])
    html = render_industry_theme_daily(df, **PANEL_KWARGS)
    assert "行业主题" in html or "行业" in html


def test_render_category_cumulative_daily_returns_html_fragment():
    df = _flow_df(["broad", "industry"])
    html = render_category_cumulative_daily(df, **PANEL_KWARGS)
    assert "资产类别" in html or "堆叠" in html


def test_render_cycle_daily_returns_html_fragment():
    df = _flow_df(["cycle"])
    html = render_cycle_daily(df, **PANEL_KWARGS)
    assert "周期" in html


def test_render_cycle_cumulative_daily_returns_html_fragment():
    df = _flow_df(["cycle"])
    html = render_cycle_cumulative_daily(df, **PANEL_KWARGS)
    assert "周期" in html
    assert "累计" in html


def test_render_top15_etf_daily_returns_html_fragment():
    df = _flow_df(["broad"] * 20)
    df["ts_code"] = [f"ETF{i:03d}.SH" for i in range(len(df))]
    html = render_top15_etf_daily(df, **PANEL_KWARGS)
    assert "TOP15" in html or "TOP" in html
    # TOP15 应被截断到前 15 只；ETF015（第 16 只）不应出现
    assert "ETF015" not in html


def test_render_handles_empty_df_gracefully():
    """spec §3.5 共通验收：上游失败时面板显式 stale，不渲染空 figure。"""
    empty = pd.DataFrame(columns=["trade_date", "ts_code", "label",
                                   "etf_estimated_flow_cny", "cumulative_flow_cny"])
    html = render_huijin_broad_daily(empty, data_date="2026-08-12",
                                     coverage=None, last_success_at=None)
    assert "stale" in html.lower() or "数据不可得" in html


def test_render_label_filter_yields_empty_sub_shows_stale():
    """df 非空但 label 过滤后无行：面板应 stale，不渲染空 figure。"""
    df = _flow_df(["broad"])  # df 有数据，但没有 huijin 标签
    html = render_huijin_broad_daily(df, **PANEL_KWARGS)
    assert "stale" in html.lower() or "数据不可得" in html
    # 不应该出现空 figure 的 Plotly 调用
    assert "Plotly.newPlot" not in html
