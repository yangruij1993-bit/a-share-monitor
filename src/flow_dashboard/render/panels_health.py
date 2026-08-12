"""数据健康页：覆盖率矩阵 + 源状态 + 未冻结项。"""
from __future__ import annotations

from html import escape as _html_escape

import pandas as pd

from flow_dashboard.render.theme import COLORS


def render_health_page(
    *,
    coverage_df: pd.DataFrame,
    source_status: pd.DataFrame,
    unfrozen: list[str],
    data_date: str,
    run_at: str,
) -> str:
    sections: list[str] = []
    sections.append(_render_header(data_date, run_at))
    sections.append(_render_coverage_matrix(coverage_df))
    sections.append(_render_source_status(source_status))
    sections.append(_render_unfrozen(unfrozen))
    sections.append(_render_footer())
    return "\n".join(sections)


def _render_header(data_date: str, run_at: str) -> str:
    safe_date = _html_escape(str(data_date))
    safe_run = _html_escape(str(run_at))
    return f"""<section id="health-header">
<h1>数据健康 — 数据日期 {safe_date}</h1>
<div class="meta"><span>run_at: {safe_run}</span></div>
</section>"""


def _render_coverage_matrix(df: pd.DataFrame) -> str:
    if df.empty:
        return '<section><h2>覆盖率矩阵</h2><p class="stale">无数据</p></section>'
    cols = ["dimension", "label", "trade_date",
            "count_coverage", "prior_share_coverage", "prior_aum_coverage"]
    rows_html = []
    for _, row in df.iterrows():
        cells = "".join(
            f"<td>{_html_escape(str(row.get(c, '')))}</td>" for c in cols
        )
        rows_html.append(f"<tr>{cells}</tr>")
    head = "".join(f"<th>{c}</th>" for c in cols)
    return f"""<section id="health-coverage">
<h2>覆盖率矩阵</h2>
<table border="1" cellpadding="6" cellspacing="0">
<thead><tr>{head}</tr></thead>
<tbody>{''.join(rows_html)}</tbody>
</table>
</section>"""


def _render_source_status(df: pd.DataFrame) -> str:
    if df.empty:
        return '<section><h2>源状态</h2><p>无源</p></section>'
    rows_html = []
    for _, row in df.iterrows():
        row_cls = " class='stale'" if row.get("is_stale") else ""
        source = _html_escape(str(row.get("source", "")))
        endpoint = _html_escape(str(row.get("endpoint", "")))
        last_success = _html_escape(str(row.get("last_success_at", "")))
        source_date = _html_escape(str(row.get("source_date", "")))
        n_failures = _html_escape(str(row.get("n_failures_7d", 0)))
        status_text = "stale" if row.get("is_stale") else "ok"
        rows_html.append(
            f"<tr{row_cls}>"
            f"<td>{source}</td><td>{endpoint}</td>"
            f"<td>{last_success}</td><td>{source_date}</td>"
            f"<td>{status_text}</td>"
            f"<td>{n_failures}</td>"
            f"</tr>"
        )
    return f"""<section id="health-sources">
<h2>源状态（含 stale 标记）</h2>
<table border="1" cellpadding="6" cellspacing="0">
<thead><tr><th>source</th><th>endpoint</th><th>last_success_at</th>
<th>source_date</th><th>status</th><th>n_failures_7d</th></tr></thead>
<tbody>{''.join(rows_html)}</tbody>
</table>
</section>"""


def _render_unfrozen(items: list[str]) -> str:
    if not items:
        return '<section><h2>未冻结项</h2><p>所有阈值已冻结</p></section>'
    lis = "".join(f"<li>{_html_escape(str(i))}</li>" for i in items)
    return f"""<section id="health-unfrozen">
<h2>未冻结项（needs_human_review）</h2>
<ul>{lis}</ul>
</section>"""


def _render_footer() -> str:
    return """<footer>
<p>市场观察，非交易建议。数据健康仅描述可得性，不构成投资判断。</p>
</footer>"""
