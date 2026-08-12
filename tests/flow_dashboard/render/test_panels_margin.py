"""两融面板测试。"""
from __future__ import annotations

import pandas as pd

from flow_dashboard.render.panels_margin import render_margin_exchange_panel


def _margin_df():
    return pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "exchange_id": "SSE",
         "rzye": 8100e8, "weekly_change_rzye": 50e8},
        {"trade_date": pd.Timestamp("2026-08-07"), "exchange_id": "SZSE",
         "rzye": 7100e8, "weekly_change_rzye": 40e8},
        {"trade_date": pd.Timestamp("2026-08-07"), "exchange_id": "BSE",
         "rzye": 8.6e9, "weekly_change_rzye": 0.1e8},
        {"trade_date": pd.Timestamp("2026-08-07"), "exchange_id": "ALL",
         "rzye": 15_008.6e8, "weekly_change_rzye": 90.1e8},
    ])


def test_render_margin_exchange_panel_returns_html_with_sse_szse_bse():
    html = render_margin_exchange_panel(
        _margin_df(), data_date="2026-08-12",
        coverage=1.0, last_success_at="19:30",
        reconciliation_tolerance=None,  # 未冻结
    )
    assert "融资余额" in html
    assert "SSE" in html and "SZSE" in html and "BSE" in html
    assert 'id="panel-margin-exchange"' in html


def test_render_margin_exchange_panel_handles_empty_df():
    html = render_margin_exchange_panel(
        pd.DataFrame(columns=["trade_date", "exchange_id", "rzye"]),
        data_date="2026-08-12", coverage=None, last_success_at=None,
        reconciliation_tolerance=None,
    )
    assert "stale" in html.lower() or "数据不可得" in html
