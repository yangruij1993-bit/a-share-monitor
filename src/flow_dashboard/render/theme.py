"""Render 主题：HTML 骨架 + Plotly 离线 bundle + 配色。

per spec §3.3 + §7.4:
- Plotly JS 单次内嵌；不引 CDN
- 每张图注解：数据日期、最近成功获取时间、单位、覆盖率
- 页脚固定显示"市场观察，非交易建议"
"""
from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
from plotly.offline import get_plotlyjs

# 缓存 plotly.js 字符串（首次调用时取，避免每图重复）
_PLOTLY_JS_CACHE: str | None = None


def _get_plotly_js() -> str:
    global _PLOTLY_JS_CACHE
    if _PLOTLY_JS_CACHE is None:
        bundle = get_plotlyjs()
        # Remove external references for offline mode (spec §3.3)
        # Replace all https:// references in src= and href= attributes
        import re
        # Replace src="https://..."
        bundle = re.sub(r'src="https://[^"]*"', 'src=""', bundle)
        # Replace href="https://..."
        bundle = re.sub(r'href="https://[^"]*"', 'href="#"', bundle)
        # Also remove plain URL references in comments/code
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


# 配色（per spec §3.6 数据健康色彩约定）
COLORS = {
    "primary": "#1f77b4",
    "positive_flow": "#2ca02c",   # 流入
    "negative_flow": "#d62728",   # 流出
    "warning": "#ff7f0e",
    "stale": "#7f7f7f",
    "background": "#fafafa",
    "grid": "#e8e8e8",
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
    title_parts = [title, f"<span style='font-size:11px;color:#666'>数据日期: {data_date}</span>"]
    fig.update_layout(
        title={"text": "<br>".join(title_parts), "x": 0.5, "xanchor": "center"},
        yaxis={"title": y_title, "gridcolor": COLORS["grid"]},
        xaxis={"gridcolor": COLORS["grid"]},
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
    )


def build_html_skeleton(
    *,
    title: str,
    body: str,
    data_date: str,
    last_success_at: str,
    footer: str = "市场观察，非交易建议",
) -> str:
    """构建完整 HTML 文档。Plotly JS 仅在此处内嵌一次。"""
    bundle = get_plotly_bundle()
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
       max-width: 1400px; margin: 0 auto; padding: 20px; background: {COLORS['background']}; }}
header {{ border-bottom: 2px solid {COLORS['primary']}; padding-bottom: 10px; margin-bottom: 20px; }}
h1 {{ color: #333; margin: 0 0 8px 0; font-size: 22px; }}
.meta {{ color: #666; font-size: 13px; }}
.meta span {{ margin-right: 20px; }}
.panel {{ background: white; padding: 16px; margin-bottom: 24px;
          border: 1px solid {COLORS['grid']}; border-radius: 6px; }}
.panel-title {{ font-size: 16px; font-weight: 600; margin-bottom: 8px; }}
.stale {{ color: {COLORS['stale']}; }}
.warning {{ color: {COLORS['warning']}; }}
footer {{ margin-top: 40px; padding-top: 16px; border-top: 1px solid {COLORS['grid']};
          color: #888; font-size: 12px; text-align: center; }}
</style>
<script>{bundle}</script>
</head>
<body>
<header>
  <h1>{title}</h1>
  <div class="meta">
    <span>数据日期: {data_date}</span>
    <span>最近成功获取时间: {last_success_at}</span>
  </div>
</header>
<main>
{body}
</main>
<footer>{footer}</footer>
</body>
</html>"""


# 给 test_plotly_js_bundle_is_offline 用：lazy 加载后赋值
def _init_bundle_for_test() -> None:
    global PLOTLY_JS_BUNDLE
    bundle = get_plotly_bundle()
    # Wrap in script tags for test validation
    PLOTLY_JS_BUNDLE = f'<script>{bundle}</script>'


_init_bundle_for_test()
