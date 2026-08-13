# src/flow_dashboard/render/panels_margin_industry.py
"""个股两融按申万 L1 行业热力图面板（Phase C 第 16 块面板）。"""
from __future__ import annotations

from html import escape as _html_escape

import pandas as pd

from flow_dashboard.render.figures import industry_heatmap_panel
from flow_dashboard.render.theme import render_figure_to_html


_PANEL_ID = "panel-margin-industry-heatmap"
_PANEL_TITLE = "个股两融 — 申万 L1 行业热力图（5 日净融资变化）"


def _wrap_panel(div_id: str, title: str, body: str, stale: bool = False) -> str:
    stale_cls = " stale" if stale else ""
    return f"""<div class="panel{stale_cls}" id="{div_id}">
<h2 class="panel-title">{_html_escape(title)}</h2>
{body}
</div>"""


def _stale_message(reason: str = "数据不可得") -> str:
    return f'<div class="stale">⚠️ {reason}（stale）</div>'


def render_margin_industry_heatmap(
    df: pd.DataFrame,
    *,
    data_date: str,
    coverage: float | None,
    last_success_at: str | None,
) -> str:
    """渲染行业热力图面板。

    Args:
        df: aggregate_margin_by_industry + compute_net_margin_change 输出
        coverage: None 表示上游未冻结，面板 stale
    """
    if df.empty or coverage is None:
        return _wrap_panel(_PANEL_ID, _PANEL_TITLE, _stale_message(), stale=True)

    fig = industry_heatmap_panel(
        df, title=_PANEL_TITLE, data_date=data_date,
        coverage=coverage, last_success_at=last_success_at,
    )
    body = render_figure_to_html(fig, div_id=_PANEL_ID)
    return _wrap_panel(_PANEL_ID, _PANEL_TITLE, body)
