"""基差面板：IC/IM 双 subplot，盘中/日终分层标识。"""
from __future__ import annotations

from html import escape as _html_escape

import pandas as pd

from flow_dashboard.render.figures import dual_subplot_basis_panel
from flow_dashboard.render.theme import render_figure_to_html


def _wrap_panel(body: str, stale: bool = False, layer_note: str = "") -> str:
    cls = " stale" if stale else ""
    title = _html_escape(f"期货基差 — IC/IM 逐合约 {layer_note}".rstrip())
    return f"""<div class="panel{cls}" id="panel-basis">
<h2 class="panel-title">{title}</h2>
{body}
</div>"""


def render_basis_panel(
    *,
    ic_df: pd.DataFrame,
    im_df: pd.DataFrame,
    data_date: str,
    coverage: float | None,
    last_success_at: str | None,
    layer: str = "eod",
) -> str:
    if (ic_df.empty and im_df.empty) or coverage is None:
        return _wrap_panel(
            '<div class="stale">⚠️ 数据不可得（stale）</div>',
            stale=True,
            layer_note="(预览)" if layer == "intraday" else "",
        )

    fig = dual_subplot_basis_panel(
        ic_df, im_df, data_date=data_date,
        coverage=coverage, last_success_at=last_success_at,
    )
    body = render_figure_to_html(fig, div_id="panel-basis-fig")
    layer_note = "(盘中预览)" if layer == "intraday" else ""
    return _wrap_panel(body, layer_note=layer_note)
