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


# === 融资余额长期趋势面板（全市场 / 创业板双子图） ===

def _trend_inputs():
    dates = pd.date_range("2026-05-01", periods=10, freq="D")
    market = pd.DataFrame({
        "trade_date": dates,
        "exchange_id": "ALL",
        "rzye": [28_000e8 + i * 10e8 for i in range(10)],
    })
    chinext = pd.DataFrame({
        "trade_date": dates,
        "chinext_rzye": [5000e8 + i * 5e8 for i in range(10)],
    })
    return market, chinext


def test_render_margin_trend_panel_returns_two_subplots():
    from flow_dashboard.render.panels_margin import render_margin_trend_panel

    market, chinext = _trend_inputs()
    html = render_margin_trend_panel(
        market, chinext,
        data_date="2026-08-12", coverage=1.0, last_success_at="19:30",
    )
    assert 'id="panel-margin-trend"' in html
    assert "全市场" in html and "创业板" in html
    assert "Plotly.newPlot" in html
    # 全市场余额折线值（亿元）：28000 起步
    assert "28000.0" in html
    # 创业板：5000 起步
    assert "5000.0" in html


def _html_contains(html: str, text: str) -> bool:
    """plotly to_html 内嵌 JSON 转义非 ASCII 为 \\uXXXX、/ 为 \\u002f，各形态都查。"""
    if text in html:
        return True
    esc = text.encode("unicode_escape").decode().replace("/", "\\u002f")
    return esc in html


def test_render_margin_trend_panel_keeps_subplot_titles():
    """角标注释不得覆盖 make_subplots 的子图标题。

    回归：make_subplots 把子图标题存为 layout.annotations，
    fig.update_layout(annotations=[...]) 会整体替换导致两个子图标题消失。
    """
    from flow_dashboard.render.panels_margin import render_margin_trend_panel

    market, chinext = _trend_inputs()
    html = render_margin_trend_panel(
        market, chinext,
        data_date="2026-08-12", coverage=1.0, last_success_at="19:30",
    )
    assert _html_contains(html, "全市场融资余额（沪深北合计）")
    assert _html_contains(html, "创业板融资余额（300/301）")
    # 角标注释也应在
    assert _html_contains(html, "数据日期: 2026-08-12")


def test_render_margin_trend_panel_stale_when_both_empty():
    from flow_dashboard.render.panels_margin import render_margin_trend_panel

    html = render_margin_trend_panel(
        pd.DataFrame(columns=["trade_date", "exchange_id", "rzye"]),
        pd.DataFrame(columns=["trade_date", "chinext_rzye"]),
        data_date="2026-08-12", coverage=None, last_success_at=None,
    )
    assert "stale" in html.lower() or "数据不可得" in html
    assert "Plotly.newPlot" not in html
