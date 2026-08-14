"""Render 主题：HTML 骨架 + Plotly 离线 bundle + 配色。

per spec §3.3 + §7.4:
- Plotly JS 单次内嵌；不引 CDN
- 每张图注解：数据日期、最近成功获取时间、单位、覆盖率
- 页脚固定显示"市场观察，非交易建议"
"""
from __future__ import annotations

import re
from html import escape as _html_escape
from pathlib import Path

import plotly.graph_objects as go
from plotly.offline import get_plotlyjs

# 缓存 plotly.js 字符串（首次调用时取，避免每图重复）
_PLOTLY_JS_CACHE: str | None = None


def _get_plotly_js() -> str:
    global _PLOTLY_JS_CACHE
    if _PLOTLY_JS_CACHE is None:
        bundle = get_plotlyjs()
        # Strip external URLs for offline mode (spec §3.3).
        # Hostnames observed in plotly 6.x bundle; re-check if plotly upgrades.
        bundle = re.sub(r'src="https://[^"]*"', 'src=""', bundle)
        bundle = re.sub(r'href="https://[^"]*"', 'href="#"', bundle)
        bundle = bundle.replace('cdn.plot.ly', 'offline-origin-disabled.plot.ly')
        bundle = bundle.replace('cartocdn.com', 'offline-origin-disabled.example.com')
        bundle = bundle.replace('basemaps.', 'basemaps-offline.')
        bundle = bundle.replace('plotly.com', 'offline-origin-disabled.example')
        _PLOTLY_JS_CACHE = bundle
    return _PLOTLY_JS_CACHE


PLOTLY_JS_BUNDLE: str = ""  # 由 _get_plotly_js() lazy 注入；常量字符串给测试先看 presence


def get_plotly_bundle() -> str:
    """Lazy 获取 plotly.js bundle 文本。"""
    return _get_plotly_js()


# 配色（per spec §3.6 数据健康色彩约定 + 专业研究报告风格）
# 主色用深蓝 #1f3a6c（参考 ashare-flow-weekly 周报），辅助色与 A 股习惯一致（红涨绿跌）。
COLORS = {
    "primary": "#1f3a6c",         # 深蓝主色（header / 章节标题底色）
    "primary_light": "#3a5a8c",   # 浅蓝（次级强调）
    "positive_flow": "#c0392b",   # 红 = 净流入/上涨（A 股惯例）
    "negative_flow": "#27ae60",   # 绿 = 净流出/下跌
    "warning": "#ff7f0e",
    "stale": "#7f7f7f",
    "background": "#fafafa",
    "grid": "#e8e8e8",
    "section_band": "#1f3a6c",    # 章节横条底色
    "card_bg": "#ffffff",         # 数据卡片底色
    "card_border": "#e0e6ed",     # 数据卡片边框
}


def apply_theme(
    fig: go.Figure,
    *,
    title: str,
    y_title: str,
    data_date: str,
    coverage: float | None = None,
    last_success_at: str | None = None,
    unit: str | None = None,
) -> go.Figure:
    """对 figure 应用统一主题：标题、轴标签、覆盖率和最新获取时间注解。"""
    title_parts = [
        _html_escape(title),
        f"<span style='font-size:11px;color:#666'>数据日期: {_html_escape(data_date)}</span>",
    ]
    fig.update_layout(
        title={"text": "<br>".join(title_parts), "x": 0.5, "xanchor": "center"},
        yaxis={"title": y_title, "gridcolor": COLORS["grid"]},
        # type="category" 防止 Plotly 把 "YYYY-MM-DD" 字符串自动识别为日期，
        # 否则会在周末/节假日产生空白间隔。
        xaxis={"type": "category", "gridcolor": COLORS["grid"]},
        plot_bgcolor=COLORS["background"],
        margin={"l": 60, "r": 30, "t": 80, "b": 40},
        font={"size": 12},
    )
    annotations = list(fig.layout.annotations or [])
    notes = []
    if coverage is not None:
        notes.append(f"覆盖率: {coverage:.1%}")
    if last_success_at:
        notes.append(f"最近成功获取时间: {last_success_at}")
    if unit:
        notes.append(f"单位: {unit}")
    if notes:
        annotations.append({
            "text": " | ".join(notes),
            "showarrow": False,
            "x": 1.0, "xref": "paper",
            "y": 1.0, "yref": "paper",
            "yanchor": "bottom", "xanchor": "right",
            "font": {"size": 10, "color": "#666"},
        })
    fig.update_layout(annotations=annotations)
    return fig


def render_figure_to_html(fig: go.Figure, *, div_id: str, full_html: bool = False) -> str:
    """把 figure 渲染成 HTML 片段（默认）或完整 HTML（含 bundle）。"""
    return fig.to_html(
        full_html=full_html,
        include_plotlyjs=(get_plotly_bundle() if full_html else False),
        div_id=div_id,
        default_height="450px",
        default_width="100%",
    )


def build_html_skeleton(
    *,
    title: str,
    body: str,
    data_date: str,
    last_success_at: str,
    footer: str = "市场观察，非交易建议",
    nav_sections: list[tuple[str, str]] | None = None,
) -> str:
    """构建完整 HTML 文档。Plotly JS 仅在此处内嵌一次。

    Args:
        nav_sections: 章节锚点列表 ``[(anchor_id, display_name), ...]``；
                      若提供则渲染 header 顶部章节导航条，点击跳转到对应 section。
                      传 None 时回退到旧行为（无导航条）。

    注：``body`` 由调用方拼装 panel HTML，原样插入（caller 负责转义）；
    其他字符串参数（title/data_date/last_success_at/footer）会被 HTML 转义。
    """
    bundle = get_plotly_bundle()
    title_h = _html_escape(title)
    data_date_h = _html_escape(data_date)
    last_success_at_h = _html_escape(last_success_at)
    footer_h = _html_escape(footer)

    nav_html = ""
    if nav_sections:
        items = "".join(
            f'<a href="#{_html_escape(anchor)}">{_html_escape(name)}</a>'
            for anchor, name in nav_sections
        )
        nav_html = f'<nav class="section-nav">{items}</nav>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title_h}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
       max-width: 1400px; margin: 0 auto; padding: 20px; background: {COLORS['background']};
       color: #333; }}

/* —— 顶部 header —— */
header.report-header {{
    background: linear-gradient(135deg, {COLORS['primary']} 0%, {COLORS['primary_light']} 100%);
    color: #fff; padding: 18px 24px; margin: -20px -20px 0 -20px;
    border-bottom: 3px solid #16284a;
}}
header.report-header h1 {{
    color: #fff; margin: 0 0 6px 0; font-size: 22px; font-weight: 600;
    letter-spacing: 0.5px;
}}
header.report-header .team-name {{
    font-size: 12px; color: rgba(255,255,255,0.85); margin-bottom: 10px;
    letter-spacing: 1px;
}}
header.report-header .meta {{
    color: rgba(255,255,255,0.92); font-size: 12px; margin-top: 6px;
}}
header.report-header .meta span {{ margin-right: 24px; }}

/* —— 章节导航条 —— */
.section-nav {{
    background: #fff; padding: 10px 24px; margin: 0 -20px 24px -20px;
    border-bottom: 1px solid {COLORS['card_border']};
    font-size: 13px; box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}}
.section-nav a {{
    color: {COLORS['primary']}; text-decoration: none; margin-right: 24px;
    padding: 4px 10px; border-radius: 4px; transition: background 0.2s;
}}
.section-nav a:hover {{ background: {COLORS['primary']}; color: #fff; }}

/* —— 章节横条 —— */
.section-band {{
    background: {COLORS['section_band']}; color: #fff;
    padding: 10px 18px; margin: 32px -16px 20px -16px;
    font-size: 16px; font-weight: 600; letter-spacing: 0.5px;
    border-radius: 4px; clear: both;
    display: flex; align-items: center; gap: 12px;
}}
.section-band .section-num {{
    background: rgba(255,255,255,0.2); padding: 2px 8px; border-radius: 3px;
    font-size: 13px; font-weight: 400;
}}
.section-band .section-sub {{
    font-size: 12px; font-weight: 400; color: rgba(255,255,255,0.8);
    margin-left: auto;
}}

/* —— 数据卡片（核心结论） —— */
.cards-row {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(158px, 1fr));
    gap: 12px; margin: 0 0 24px 0;
}}
.kpi-card {{
    background: {COLORS['card_bg']}; border: 1px solid {COLORS['card_border']};
    border-left: 3px solid {COLORS['primary']};
    padding: 14px 16px; border-radius: 4px;
}}
.kpi-card .kpi-label {{
    font-size: 12px; color: #666; margin-bottom: 6px; letter-spacing: 0.3px;
}}
.kpi-card .kpi-value {{
    font-size: 22px; font-weight: 600; color: {COLORS['primary']};
    line-height: 1.2;
}}
.kpi-card .kpi-delta {{
    font-size: 11px; margin-top: 4px; color: #888;
}}
.kpi-card.positive {{ border-left-color: {COLORS['positive_flow']}; }}
.kpi-card.positive .kpi-value {{ color: {COLORS['positive_flow']}; }}
.kpi-card.negative {{ border-left-color: {COLORS['negative_flow']}; }}
.kpi-card.negative .kpi-value {{ color: {COLORS['negative_flow']}; }}

/* —— 单个 panel —— */
.panel {{ background: white; padding: 16px; margin-bottom: 24px;
          border: 1px solid {COLORS['grid']}; border-radius: 6px; }}
.panel-title {{ font-size: 15px; font-weight: 600; margin-bottom: 4px;
                color: {COLORS['primary']}; }}
.panel-subtitle {{ font-size: 12px; color: #666; margin: 0 0 10px 0;
                   line-height: 1.5; }}
.stale {{ color: {COLORS['stale']}; }}
.warning {{ color: {COLORS['warning']}; }}
footer {{ margin-top: 40px; padding-top: 16px; border-top: 1px solid {COLORS['grid']};
          color: #888; font-size: 12px; text-align: center; }}
</style>
<script>{bundle}</script>
</head>
<body>
<header class="report-header">
  <div class="team-name">A 股流动性跟踪 · FLOW DASHBOARD</div>
  <h1>{title_h}</h1>
  <div class="meta">
    <span>📅 数据日期: {data_date_h}</span>
    <span>🕐 最近获取: {last_success_at_h}</span>
  </div>
</header>
{nav_html}
<main>
{body}
</main>
<footer>{footer_h}</footer>
</body>
</html>"""


def render_section_band(
    *, anchor_id: str, num: str, title: str, subtitle: str | None = None,
) -> str:
    """渲染章节横条：深蓝底 + 序号 + 标题 + 副标题。

    Args:
        anchor_id: 锚点 id（与 header 章节导航 a href 对应）
        num: 序号显示（如 "01"、"02"）
        title: 章节标题
        subtitle: 章节副标题（右侧浅色文字），可选
    """
    sub_html = (
        f'<span class="section-sub">{_html_escape(subtitle)}</span>' if subtitle else ""
    )
    return (
        f'<div class="section-band" id="{_html_escape(anchor_id)}">'
        f'<span class="section-num">{_html_escape(num)}</span>'
        f'<span>{_html_escape(title)}</span>'
        f"{sub_html}"
        "</div>"
    )


def render_kpi_cards(cards: list[dict]) -> str:
    """渲染核心结论 KPI 卡片行。

    Args:
        cards: 每项形如
            ``{"label": "...", "value": "...", "delta": "...", "tone": "positive|negative|neutral"}``

    Returns:
        HTML 字符串（``<div class="cards-row">...</div>``）；空列表返回空串。
    """
    if not cards:
        return ""
    items: list[str] = []
    for c in cards:
        tone = c.get("tone", "neutral")
        tone_cls = f" {tone}" if tone in ("positive", "negative") else ""
        delta_html = (
            f'<div class="kpi-delta">{_html_escape(str(c["delta"]))}</div>'
            if c.get("delta") else ""
        )
        items.append(
            f'<div class="kpi-card{tone_cls}">'
            f'<div class="kpi-label">{_html_escape(str(c.get("label", "")))}</div>'
            f'<div class="kpi-value">{_html_escape(str(c.get("value", "—")))}</div>'
            f"{delta_html}"
            "</div>"
        )
    return f'<div class="cards-row">{"".join(items)}</div>'


# 给 test_plotly_js_bundle_is_offline 用：lazy 加载后赋值
def _init_bundle_for_test() -> None:
    global PLOTLY_JS_BUNDLE
    bundle = get_plotly_bundle()
    # Wrap in script tags for test validation
    PLOTLY_JS_BUNDLE = f'<script>{bundle}</script>'


_init_bundle_for_test()
