"""数据健康页测试。"""
from __future__ import annotations

import pandas as pd

from flow_dashboard.render.panels_health import render_health_page


def _coverage_df():
    return pd.DataFrame([
        {"dimension": "ownership", "label": "huijin", "trade_date": "2026-08-12",
         "count_coverage": 0.75, "prior_share_coverage": 1.0, "prior_aum_coverage": 1.0},
        {"dimension": "asset_scope", "label": "broad", "trade_date": "2026-08-12",
         "count_coverage": 1.0, "prior_share_coverage": 1.0, "prior_aum_coverage": 1.0},
    ])


def _source_status():
    return pd.DataFrame([
        {"source": "tushare", "endpoint": "etf_share_size", "last_success_at": "2026-08-12 19:30",
         "source_date": "2026-08-12", "is_stale": False, "n_failures_7d": 0},
        {"source": "tushare", "endpoint": "margin", "last_success_at": "2026-08-12 19:30",
         "source_date": "2026-08-12", "is_stale": False, "n_failures_7d": 1},
        {"source": "sina", "endpoint": "futures_node_IC", "last_success_at": "2026-08-12 14:30",
         "source_date": "2026-08-12", "is_stale": True, "n_failures_7d": 3},
    ])


def _unfrozen():
    return ["coverage_gates", "reconciliation_tolerance", "max_quote_skew_seconds"]


def test_render_health_page_has_required_sections():
    html = render_health_page(
        coverage_df=_coverage_df(),
        source_status=_source_status(),
        unfrozen=_unfrozen(),
        data_date="2026-08-12", run_at="2026-08-12 19:35 CST",
    )
    assert "数据健康" in html
    assert "覆盖率" in html
    assert "源状态" in html or "Source" in html
    assert "未冻结" in html or "needs_human_review" in html


def test_render_health_page_highlights_stale_sources():
    html = render_health_page(
        coverage_df=_coverage_df(),
        source_status=_source_status(),
        unfrozen=_unfrozen(),
        data_date="2026-08-12", run_at="2026-08-12 19:35 CST",
    )
    # is_stale=True 的 sina 应该被标红/警告
    assert "stale" in html.lower() or "warning" in html.lower()


def test_render_health_page_lists_unfrozen_items():
    html = render_health_page(
        coverage_df=_coverage_df(),
        source_status=_source_status(),
        unfrozen=_unfrozen(),
        data_date="2026-08-12", run_at="2026-08-12 19:35 CST",
    )
    for item in _unfrozen():
        assert item in html
