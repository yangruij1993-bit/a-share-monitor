# src/flow_dashboard/render/panels_margin_industry.py
"""个股两融按申万 L1 行业表（Phase C 第 16 块面板）。

参考周报原型用 HTML 表格而不是 Plotly Heatmap：
- 表格能精确显示每个单元的数字（Heatmap 在 28 行 × 30 列时数字密度过低，难以速读）
- 行业按"近 N 日合计"降序，方便看哪个行业最近在加杠杆 / 去杠杆
- 颜色用 inline style 做条件色（红正绿负），避免外部 CSS 依赖
"""
from __future__ import annotations

from html import escape as _html_escape

import pandas as pd


_PANEL_ID = "panel-margin-industry-heatmap"
_PANEL_TITLE = "个股两融 — 申万 L1 行业资金 5 日净变化（亿元）"
_YI = 1e8


def _wrap_panel(div_id: str, title: str, subtitle: str, body: str, stale: bool = False) -> str:
    stale_cls = " stale" if stale else ""
    return f"""<div class="panel{stale_cls}" id="{div_id}">
<h2 class="panel-title">{_html_escape(title)}</h2>
<p class="panel-subtitle">{_html_escape(subtitle)}</p>
{body}
</div>"""


def _stale_message(reason: str = "数据不可得") -> str:
    return f'<div class="stale">⚠️ {reason}（stale）</div>'


def _cell_style(v: float | None) -> str:
    """红正绿负条件色；NaN 给浅灰。"""
    if v is None or pd.isna(v):
        return "background:#f5f5f5;color:#999;"
    if v > 0:
        # 数值越大红越深，上限 +5 亿
        intensity = min(abs(v) / 5.0, 1.0)
        bg = f"rgba(192, 57, 43, {0.12 + 0.55 * intensity})"
        return f"background:{bg};color:#7a1f12;"
    elif v < 0:
        intensity = min(abs(v) / 5.0, 1.0)
        bg = f"rgba(39, 174, 96, {0.12 + 0.55 * intensity})"
        return f"background:{bg};color:#1e6b3a;"
    return "background:#fff;color:#333;"


def _fmt_cell(v: float | None) -> str:
    if v is None or pd.isna(v):
        return "—"
    return f"{v / _YI:+.2f}"


def _build_table_html(
    df: pd.DataFrame, *, n_trading_days: int,
) -> str:
    """构造 HTML 表格。

    每格 = 该行业当日 net_margin_5d_change（5 日滑动净融资变化）。
    最右两列：
        - "近 5 日"：最新一天的 5d_change（最近一周的杠杆变化）
        - "近 N 日"：区间末-首 net_margin 差（N 日真实累计净融资增减）
    """
    df = df.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    recent_dates = sorted(df["trade_date"].unique())[-n_trading_days:]
    df = df[df["trade_date"].isin(recent_dates)]

    pivot = df.pivot_table(
        index="industry_name",
        columns="trade_date",
        values="net_margin_5d_change",
        aggfunc="first",
    )
    pivot = pivot.reindex(sorted(pivot.index))
    pivot = pivot[sorted(pivot.columns)]

    # 最近 5 日变化 = 最后一列的 5d_change
    last_5d = pivot.iloc[:, -1]

    # 近 N 日累计 = net_margin 的末-首差（不能求和 5d_change，窗口重叠会重复累加）
    if "net_margin" in df.columns:
        nm_pivot = df.pivot_table(
            index="industry_name",
            columns="trade_date",
            values="net_margin",
            aggfunc="first",
        ).reindex(sorted(df["industry_name"].unique()))
        nm_pivot = nm_pivot[sorted(nm_pivot.columns)]
        first_nm = nm_pivot.bfill(axis=1).iloc[:, 0]
        last_nm = nm_pivot.ffill(axis=1).iloc[:, -1]
        cum_n = last_nm - first_nm
    else:
        cum_n = last_5d  # 回退：无 net_margin 时与 5d 一致

    # 按近 5 日变化降序：表格主体是 5d 变化，读者最关心"最近一周谁在加杠杆"。
    # 近 N 日累计仅作辅助参考，不参与排序（否则会出现"最近 5 日 +167 但 20 日 -542"
    # 的行业排到最后这种反直觉情况）。
    order = last_5d.sort_values(ascending=False).index
    pivot = pivot.loc[order]
    last_5d = last_5d.loc[order]
    cum_n = cum_n.loc[order]

    # 表头
    date_headers = "".join(
        f"<th>{pd.Timestamp(d).strftime('%m-%d')}</th>" for d in pivot.columns
    )
    header = (
        "<tr><th>行业</th>"
        f"{date_headers}"
        f"<th>近 5 日</th><th>近 {n_trading_days} 日</th></tr>"
    )

    # 表体
    body_rows: list[str] = []
    for industry, row in pivot.iterrows():
        cells = "".join(
            f'<td style="{_cell_style(v)}">{_fmt_cell(v)}</td>'
            for v in row.values
        )
        v5 = last_5d[industry]
        vn = cum_n[industry]
        sum_cells = (
            f'<td style="{_cell_style(v5)};font-weight:600;">{_fmt_cell(v5)}</td>'
            f'<td style="{_cell_style(vn)};font-weight:600;">{_fmt_cell(vn)}</td>'
        )
        body_rows.append(
            f"<tr><th style='text-align:left;'>{_html_escape(str(industry))}</th>"
            f"{cells}{sum_cells}</tr>"
        )

    return (
        '<div class="table-wrap" style="overflow-x:auto;">'
        '<table class="industry-margin-table" '
        'style="border-collapse:collapse;width:100%;font-size:11px;'
        'font-variant-numeric:tabular-nums;">'
        f"<thead>{header}</thead>"
        f"<tbody>{''.join(body_rows)}</tbody>"
        "</table></div>"
    )


def render_margin_industry_heatmap(
    df: pd.DataFrame,
    *,
    data_date: str,
    coverage: float | None,
    last_success_at: str | None,
    n_trading_days: int = 20,
) -> str:
    """渲染行业资金 5 日净变化表格。

    Args:
        df: aggregate_margin_by_industry + compute_net_margin_change 输出，
            必须含 trade_date, industry_name, net_margin_5d_change；
            建议同时含 net_margin（用于最右"近 N 日"列）
        coverage: None 表示上游未冻结，面板 stale
        n_trading_days: 显示最近 N 个交易日（默认 20，影响最右"近 N 日"列标题）
    """
    subtitle = (
        f"每格 = 该行业个股两融净额（融资 - 融券）的 5 日滑动变化（亿元），正红负绿；"
        f"最右两列为'近 5 日'（最新一日 5d 变化）和'近 {n_trading_days} 日'（区间累计净融资增减），"
        f"按近 5 日变化降序排列。"
    )

    if df.empty or coverage is None:
        return _wrap_panel(
            _PANEL_ID, _PANEL_TITLE, subtitle,
            _stale_message(), stale=True,
        )

    table_html = _build_table_html(df, n_trading_days=n_trading_days)
    last_line = (
        f'<div style="font-size:11px;color:#888;margin-top:8px;">'
        f"数据日期: {_html_escape(data_date)} | "
        f"最近获取: {_html_escape(last_success_at or '—')} | "
        f"覆盖率: {coverage:.0%}"
        f"</div>"
    )
    return _wrap_panel(
        _PANEL_ID, _PANEL_TITLE, subtitle,
        f"{table_html}{last_line}",
    )
