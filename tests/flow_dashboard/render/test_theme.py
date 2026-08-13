"""Render theme 契约测试。"""
from __future__ import annotations

import re

import plotly.graph_objects as go

from flow_dashboard.render.theme import (
    PLOTLY_JS_BUNDLE,
    build_html_skeleton,
    render_figure_to_html,
    apply_theme,
)


def test_plotly_js_bundle_is_offline():
    """spec §3.3: 不得引用 CDN。"""
    assert "cdn" not in PLOTLY_JS_BUNDLE.lower()
    assert "plotly.com" not in PLOTLY_JS_BUNDLE.lower()
    assert "<script>" in PLOTLY_JS_BUNDLE


def test_build_html_skeleton_has_required_sections():
    html = build_html_skeleton(
        title="A 股流动性日报 2026-08-12",
        body="<div id='panels'></div>",
        data_date="2026-08-12",
        last_success_at="2026-08-12 19:30 CST",
    )
    assert "<!DOCTYPE html>" in html
    assert "A 股流动性日报 2026-08-12" in html
    assert "数据日期: 2026-08-12" in html
    assert "最近获取" in html  # header meta label
    assert "市场观察，非交易建议" in html  # spec §7.4
    assert PLOTLY_JS_BUNDLE in html
    # Plotly bundle 只内嵌一次
    assert html.count(PLOTLY_JS_BUNDLE) == 1


def test_build_html_skeleton_offline_no_external_resource():
    html = build_html_skeleton(title="X", body="", data_date="2026-08-12",
                               last_success_at="X")
    # 不引用 http(s)
    assert not re.search(r'src="https?://', html)
    assert not re.search(r'href="https?://', html)


def test_apply_theme_returns_styled_figure():
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[1, 2, 3], y=[4, 5, 6]))
    out = apply_theme(fig, title="测试", y_title="亿元", data_date="2026-08-12",
                      coverage=0.75, last_success_at="2026-08-12 19:30")
    assert out.layout.title.text is not None
    assert "数据日期: 2026-08-12" in out.layout.title.text
    assert out.layout.yaxis.title.text == "亿元"
    assert out.layout.annotations is not None
    # 注解应包含覆盖率和最新获取时间
    annotation_texts = " ".join(a.text for a in out.layout.annotations)
    assert "覆盖率" in annotation_texts
    assert "19:30" in annotation_texts


def test_render_figure_to_html_includes_div_and_script():
    fig = go.Figure()
    fig.add_trace(go.Bar(x=["A", "B"], y=[1, 2]))
    html = render_figure_to_html(fig, div_id="panel-1")
    assert 'id="panel-1"' in html
    assert "Plotly.newPlot" in html
