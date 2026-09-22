"""港股沽空 tab 渲染（设计 §4）：只读缓存确定性重放，不发起网络请求。

render_hk_short_body 是唯一入口，返回 (html, hk_data_date)；缓存为空时
返回“数据待更新”横幅与 None（A股 tab 不受影响，设计 §3）。
"""

from __future__ import annotations

from html import escape as _esc
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from flow_dashboard.config import (
    HK_INDEX_SECIDS,
    HK_SHORT_CACHE_DIR,
    HK_THRESHOLDS,
    HK_WATCH_LIST,
)
from flow_dashboard.data.hk_short.hkex_client import etf_set
from flow_dashboard.data.hk_short.loaders import (
    load_em_days_covered,
    load_em_sellshort,
    load_etf_master,
    load_hk_kline,
    load_hkex_dayquot,
    load_sfc_weekly,
    load_total_shares,
)
from flow_dashboard.indicators import hk_short_metrics as mx
from flow_dashboard.indicators import hk_short_state as state
from flow_dashboard.render.theme import (
    COLORS,
    apply_theme,
    render_figure_to_html,
    render_kpi_cards,
    render_section_band,
)

T = HK_THRESHOLDS

_TH = (
    "border:1px solid #e8e8e8;padding:4px 8px;background:#f0f3f7;"
    "text-align:right;font-weight:600;white-space:nowrap"
)
_TD = "border:1px solid #e8e8e8;padding:4px 8px;text-align:right;white-space:nowrap"

_COLS = [
    "交易日期",
    "卖空股数",
    "卖空金额",
    "未平仓卖空期末值·股数",
    "未平仓卖空期末值·金额",
    "收盘价",
    "涨跌幅%",
    "成交量",
    "成交额",
    "卖空金额/成交额%",
    "期末未平仓/总股本%",
]


def _fmt_amount(v) -> str:
    if v is None or pd.isna(v):
        return "—"
    if abs(v) >= 1e8:
        return f"{v / 1e8:.2f}亿"
    if abs(v) >= 1e4:
        return f"{v / 1e4:.1f}万"
    return f"{v:,.0f}"


def _fmt_pct(v, digits: int = 2) -> str:
    return "—" if v is None or pd.isna(v) else f"{v * 100:.{digits}f}%"


def _fmt_x(v) -> str:
    return "样本不足" if v is None or pd.isna(v) else f"{v:.2f}x"


def _price_direction(kline: pd.DataFrame) -> str:
    if kline is None or kline.empty:
        return "unavailable"
    rets = []
    for secid in ("HSI", "HSTECH"):
        s = kline[kline["secid"] == HK_INDEX_SECIDS[secid]].sort_values("trade_date")[
            "close"
        ]
        rets.append(mx.ret_n(s, n=5))
    return mx.price_direction(
        rets[0] if len(rets) > 0 else None,
        rets[1] if len(rets) > 1 else None,
        threshold_bp=T["price_ret_bp"],
    )


def _secid_of(code: str) -> str:
    return f"116.{code.split('.')[0].zfill(5)}"


def _code5(code: str) -> str:
    """'2800.HK' -> '02800'（与 loaders._code5 一致，匹配缓存代码格式）。"""
    return str(code).split(".")[0].zfill(5)


def _build_context(*, as_of, cdir: Path) -> dict:
    em = load_em_sellshort(as_of=as_of, allow_fetch=False, cache_dir=cdir)
    full_days = load_em_days_covered(as_of=as_of, cache_dir=cdir)
    hkex = load_hkex_dayquot(as_of=as_of, allow_fetch=False, cache_dir=cdir)
    sfc = load_sfc_weekly(as_of=as_of, allow_fetch=False, cache_dir=cdir)
    secids = list(HK_INDEX_SECIDS.values()) + [_secid_of(c) for _, c in HK_WATCH_LIST]
    kline = load_hk_kline(as_of=as_of, secids=secids, allow_fetch=False, cache_dir=cdir)
    los, _eff = load_etf_master(as_of=as_of, allow_fetch=False, cache_dir=cdir)
    shares = load_total_shares(as_of=as_of, codes=[], allow_fetch=False, cache_dir=cdir)

    mkt = mx.market_daily_aggregate(em, full_days) if not em.empty else pd.DataFrame()
    weekly_i = mx.weekly_intensity(mkt["short_amount"]) if not mkt.empty else None
    ssr_pct = (
        mx.percentile_rank(
            mkt["ssr"], window=T["ssr_pct_window"], min_obs=T["ssr_pct_min_obs"]
        )
        if not mkt.empty
        else None
    )
    m20 = (
        mx.daily_intensity(mkt["short_amount"], window=T["daily_intensity_window"])
        if not mkt.empty
        else None
    )
    part = (
        mx.daily_intensity(mkt["turnover"], window=T["daily_intensity_window"])
        if not mkt.empty
        else None
    )
    price = _price_direction(kline)
    sfc_mkt = (
        mx.sfc_market_metrics(
            sfc,
            shares,
            min_comparable=T["sfc_min_comparable"],
            min_coverage=T["sfc_min_coverage"],
        )
        if not sfc.empty and not shares.empty
        else {"available": False}
    )
    etf_codes = etf_set(los)
    if not mkt.empty:
        hk_date = mkt["trade_date"].max()
    elif not kline.empty:
        hk_date = pd.to_datetime(kline["trade_date"]).max()
    elif not sfc.empty:
        hk_date = pd.to_datetime(sfc["position_date"]).max()
    else:
        hk_date = None
    dstr = pd.Timestamp(hk_date).strftime("%Y-%m-%d") if hk_date is not None else ""
    etf_share = (
        mx.etf_interference_share(hkex, etf_codes, dstr)
        if not hkex.empty and etf_codes
        else None
    )
    full_total = (
        hkex.loc[hkex["trade_date"] == pd.Timestamp(dstr), "short_amount"].sum()
        if not hkex.empty
        else None
    )
    pending = state.sfc_is_pending(
        latest_cached_pd=(
            pd.to_datetime(sfc["position_date"]).max() if not sfc.empty else None
        ),
        as_of=as_of,
    )
    conclusion = state.market_conclusion(
        sfc=sfc_mkt,
        weekly_short_intensity=weekly_i,
        ssr_percentile=ssr_pct,
        price=price,
        participation_high=part is not None and part >= T["participation_high"],
        sfc_pending=pending,
        etf_interference=etf_share is not None and etf_share >= T["etf_interference"],
    )
    return {
        "as_of": as_of,
        "em": em,
        "hkex": hkex,
        "sfc": sfc,
        "kline": kline,
        "los": los,
        "shares": shares,
        "mkt": mkt,
        "weekly_i": weekly_i,
        "ssr_pct": ssr_pct,
        "m20": m20,
        "part": part,
        "price": price,
        "sfc_mkt": sfc_mkt,
        "etf_share": etf_share,
        "full_total": full_total,
        "pending": pending,
        "conclusion": conclusion,
        "dstr": dstr,
    }


def render_hk_short_body(*, as_of, cache_dir=None) -> tuple[str, str | None]:
    cdir = Path(cache_dir) if cache_dir else HK_SHORT_CACHE_DIR
    ctx = _build_context(as_of=as_of, cdir=cdir)
    if (
        ctx["em"].empty
        and ctx["sfc"].empty
        and ctx["hkex"].empty
        and ctx["kline"].empty
    ):
        banner = (
            '<div class="panel stale">⚠️ 港股沽空数据待更新 — 缓存为空。'
            "请检查 com.ygr.hk-short.eod runner、HKEX/东财/SFC 网络与 launchd 日志。</div>"
        )
        return banner, None
    parts = [
        render_section_band(
            anchor_id="section-hk-conclusion",
            num="HK",
            title="港股沽空 · 空头状态",
            subtitle=f"数据截至 {ctx['dstr']} · 股票口径，不含 ETF/ETP",
        ),
        _render_conclusion(ctx),
        _render_market_chart(ctx),
        _render_watch(ctx),
        _render_top20(ctx),
    ]
    return "\n".join(parts), ctx["dstr"]


def _render_conclusion(ctx: dict) -> str:
    out = ctx["conclusion"]
    mkt = ctx["mkt"]
    latest_short = mkt["short_amount"].iloc[-1] if not mkt.empty else None
    latest_ssr = mkt["ssr"].iloc[-1] if not mkt.empty else None
    sfc_m = ctx["sfc_mkt"]
    if sfc_m.get("available"):
        sfc_val = f"{sfc_m['delta_bps']:+.0f}bp"
        sfc_delta = (
            f"可比 {sfc_m['n_comparable']} 只 · 覆盖 {sfc_m['coverage']:.0%}"
            f" · 报告期 {pd.Timestamp(sfc_m['latest_pd']).strftime('%m-%d')}"
        )
    elif ctx["pending"]:
        sfc_val, sfc_delta = "待公布", "已超宽限期，等待 SFC 周报"
    else:
        sfc_val, sfc_delta = "—", "宽限期内 / 可比集合不足"

    cards = render_kpi_cards(
        [
            {
                "label": "今日全市场沽空额（股票口径）",
                "value": _fmt_amount(latest_short),
                "delta": f"vs 前{T['daily_intensity_window']}日均值 {_fmt_x(ctx['m20'])}",
            },
            {
                "label": "市场加权 SSR（股票口径，不含 ETF/ETP）",
                "value": _fmt_pct(latest_ssr),
                "delta": (
                    f"前{T['ssr_pct_window']}日分位 {ctx['ssr_pct']:.0f}%"
                    if ctx["ssr_pct"] is not None
                    else "样本不足"
                ),
            },
            {"label": "SFC 须申报淡仓比例变化", "value": sfc_val, "delta": sfc_delta},
        ]
    )
    notes = "".join(
        f'<div class="panel-subtitle">· {_esc(n)}</div>' for n in out["notes"]
    )
    return (
        f'<div class="panel" id="panel-hk-conclusion">'
        f'<div class="panel-title">市场结论</div>'
        f'<div style="font-size:20px;font-weight:700;color:{COLORS["primary"]};'
        f'margin:8px 0">{_esc(out["state"])}</div>{notes}{cards}</div>'
    )


def _render_market_chart(ctx: dict) -> str:
    fig = go.Figure()
    mkt = ctx["mkt"]
    if not mkt.empty:
        x = mkt["trade_date"].dt.strftime("%Y-%m-%d")
        fig.add_bar(
            x=x,
            y=mkt["short_amount"] / 1e8,
            name="总沽空额·股票口径(亿)",
            marker_color=COLORS["primary_light"],
        )
        fig.add_scatter(
            x=x,
            y=mkt["ssr"] * 100,
            name="市场加权SSR%(股票口径)",
            mode="lines",
            line={"color": COLORS["warning"]},
            yaxis="y2",
        )
    for key, label, color in (
        ("HSI", "恒指(归一=100)", "#8c564b"),
        ("HSTECH", "恒生科技(归一=100)", "#e377c2"),
    ):
        s = (
            ctx["kline"][ctx["kline"]["secid"] == HK_INDEX_SECIDS[key]].sort_values(
                "trade_date"
            )
            if not ctx["kline"].empty
            else pd.DataFrame()
        )
        if s.empty:
            continue
        fig.add_scatter(
            x=s["trade_date"].dt.strftime("%Y-%m-%d"),
            y=s["close"] / s["close"].iloc[0] * 100,
            name=label,
            mode="lines",
            line={"color": color, "width": 1.2, "dash": "dot"},
            yaxis="y2",
        )
    fig.update_layout(
        yaxis={"title": "沽空额(亿港元)", "gridcolor": COLORS["grid"]},
        yaxis2={
            "title": "SSR% / 指数(归一)",
            "overlaying": "y",
            "side": "right",
            "gridcolor": COLORS["grid"],
        },
    )
    note = ""
    if (
        ctx["full_total"] is not None
        and not pd.isna(ctx["full_total"])
        and ctx["full_total"] > 0
    ):
        note = f"HKEX 全口径总沽空 {_fmt_amount(ctx['full_total'])}" + (
            f"，ETF 占比 {_fmt_pct(ctx['etf_share'])}"
            if ctx["etf_share"] is not None
            else ""
        )
    fig = apply_theme(
        fig,
        title="市场总览 · 沽空额 / SSR / 指数",
        y_title="沽空额(亿港元)",
        data_date=ctx["dstr"],
        coverage=None,
        last_success_at=None,
        unit=note or None,
    )
    return (
        '<div class="panel" id="panel-hk-market">'
        + render_figure_to_html(fig, div_id="hk-market-overview")
        + "</div>"
    )


def _watch_stock_df(code: str, ctx: dict) -> pd.DataFrame:
    code5 = _code5(code)
    em_stock = (
        mx.stock_daily(ctx["em"], code) if not ctx["em"].empty else pd.DataFrame()
    )
    hk_stock = (
        ctx["hkex"][ctx["hkex"]["code"] == code5].sort_values("trade_date")
        if not ctx["hkex"].empty
        else pd.DataFrame()
    )
    cols = ["trade_date", "short_shares", "short_amount", "turnover"]
    if not em_stock.empty:
        short_df = em_stock[cols + ["ssr"]].copy()
    elif not hk_stock.empty:
        short_df = hk_stock[cols].copy()
        short_df["ssr"] = short_df["short_amount"] / short_df["turnover"]
    else:
        short_df = pd.DataFrame(columns=cols + ["ssr"])
    # 合并键统一 datetime64：parquet 读写对各源列的 dtype 保持不一致，重放不得依赖存储格式
    short_df["trade_date"] = pd.to_datetime(short_df["trade_date"])
    k = (
        ctx["kline"][ctx["kline"]["secid"] == _secid_of(code)].sort_values("trade_date")
        if not ctx["kline"].empty
        else pd.DataFrame()
    )
    if not k.empty:
        kx = k[["trade_date", "close", "volume", "amount"]].copy()
        kx["trade_date"] = pd.to_datetime(kx["trade_date"])
        kx["chg_pct"] = kx["close"].pct_change() * 100
        df = short_df.merge(kx, on="trade_date", how="outer")
    else:
        df = short_df.copy()
        df["close"] = df["volume"] = df["amount"] = df["chg_pct"] = float("nan")
    if ctx["sfc"].empty:
        oi = pd.DataFrame(columns=["trade_date", "oi_shares", "oi_amount"])
    else:
        oi = ctx["sfc"][ctx["sfc"]["code"] == code5][
            ["position_date", "short_shares", "short_amount_hkd"]
        ].rename(
            columns={
                "position_date": "trade_date",
                "short_shares": "oi_shares",
                "short_amount_hkd": "oi_amount",
            }
        )
        oi["trade_date"] = pd.to_datetime(oi["trade_date"])
    df = df.merge(oi, on="trade_date", how="left").sort_values("trade_date")
    total = float("nan")
    if not ctx["shares"].empty:
        n = ctx["shares"].loc[ctx["shares"]["code"] == code5, "total_shares"]
        if len(n):
            total = float(n.iloc[0])
    df["oi_pct"] = (
        df["oi_shares"] / total * 100 if total and not pd.isna(total) else float("nan")
    )
    return df.tail(20).reset_index(drop=True)


def _stock_status(code: str, ctx: dict) -> str:
    code5 = _code5(code)
    sd = mx.stock_daily(ctx["em"], code) if not ctx["em"].empty else pd.DataFrame()
    if sd.empty:
        weekly_i = ssr_pct = part = None
    else:
        weekly_i = mx.weekly_intensity(sd["short_amount"])
        ssr_pct = mx.percentile_rank(
            sd["ssr"], window=T["ssr_pct_window"], min_obs=T["ssr_pct_min_obs"]
        )
        part = mx.daily_intensity(sd["turnover"], window=T["daily_intensity_window"])
    price = "unavailable"
    if not ctx["kline"].empty:
        s = ctx["kline"][ctx["kline"]["secid"] == _secid_of(code)].sort_values(
            "trade_date"
        )["close"]
        price = mx.price_direction(
            mx.ret_n(s, n=5), None, threshold_bp=T["price_ret_bp"]
        )
    total = float("nan")
    if not ctx["shares"].empty:
        n = ctx["shares"].loc[ctx["shares"]["code"] == code5, "total_shares"]
        if len(n):
            total = float(n.iloc[0])
    sfc_s = (
        mx.sfc_stock_metrics(ctx["sfc"], code, total)
        if not ctx["sfc"].empty and total and not pd.isna(total)
        else {"available": False}
    )
    return state.stock_conclusion(
        sfc=sfc_s if sfc_s.get("available") else None,
        weekly_short_intensity=weekly_i,
        ssr_percentile=ssr_pct,
        price=price,
        participation_high=part is not None and part >= T["participation_high"],
    )["state"]


def _watch_table_html(name: str, code: str, df: pd.DataFrame, status: str) -> str:
    head = "".join(f"<th style='{_TH}'>{_esc(c)}</th>" for c in _COLS)

    def td(v) -> str:
        return f"<td style='{_TD}'>{v}</td>"

    rows = []
    for r in df.itertuples():
        vals = [
            pd.Timestamp(r.trade_date).strftime("%Y-%m-%d"),
            f"{r.short_shares:,.0f}" if pd.notna(r.short_shares) else "—",
            _fmt_amount(r.short_amount),
            f"{r.oi_shares:,.0f}" if pd.notna(r.oi_shares) else "",
            _fmt_amount(r.oi_amount) if pd.notna(r.oi_amount) else "",
            f"{r.close:,.2f}" if pd.notna(r.close) else "—",
            f"{r.chg_pct:+.2f}" if pd.notna(r.chg_pct) else "—",
            f"{r.volume:,.0f}" if pd.notna(r.volume) else "—",
            _fmt_amount(r.amount) if pd.notna(r.amount) else "—",
            f"{r.ssr * 100:.2f}" if pd.notna(r.ssr) else "—",
            f"{r.oi_pct:.2f}" if pd.notna(r.oi_pct) else "",
        ]
        rows.append("<tr>" + "".join(td(v) for v in vals) + "</tr>")
    return (
        f'<div class="panel" id="panel-hk-watch-{code.split(".")[0]}">'
        f'<div class="panel-title">{_esc(name)} ({_esc(code)})'
        f' <span style="font-size:12px;color:{COLORS["warning"]}">[{_esc(status)}]</span></div>'
        f'<div class="panel-subtitle">最近 20 个交易日；未平仓两列仅 SFC 周报日（周度）有值</div>'
        f'<div style="overflow-x:auto"><table style="border-collapse:collapse;font-size:12px">'
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div></div>"
    )


def _render_watch(ctx: dict) -> str:
    parts = [
        render_section_band(
            anchor_id="section-hk-watch",
            num="HK·2",
            title="Watch List 逐日明细",
            subtitle="股票来自东财；ETF(2800/3033)来自 HKEX；未平仓=SFC 周度",
        )
    ]
    for name, code in HK_WATCH_LIST:
        df = _watch_stock_df(code, ctx)
        parts.append(_watch_table_html(name, code, df, _stock_status(code, ctx)))
    return "\n".join(parts)


def _top20_tag(weekly_i, pct) -> str:
    a = weekly_i is not None and weekly_i >= T["weekly_intensity_high"]
    b = pct is not None and pct >= T["ssr_pct_high"]
    if a and b:
        return "沽空额高·SSR高分位"
    if a:
        return "沽空额高"
    if b:
        return "SSR高分位"
    return "—"


def _render_top20(ctx: dict) -> str:
    em, dstr = ctx["em"], ctx["dstr"]
    if em.empty:
        return ""
    day = em[em["trade_date"] == pd.Timestamp(dstr)]
    if day.empty:
        return ""
    top = day.sort_values("short_amount", ascending=False).head(20)
    rows = []
    for r in top.itertuples():
        hist = mx.stock_daily(em, f"{r.code}.HK")
        pct = (
            mx.percentile_rank(
                hist["ssr"], window=T["ssr_pct_window"], min_obs=T["ssr_pct_min_obs"]
            )
            if not hist.empty
            else None
        )
        w_i = mx.weekly_intensity(hist["short_amount"]) if not hist.empty else None
        ssr = r.short_amount / r.turnover if r.turnover else None
        rows.append(
            f"<tr><td style='{_TD}'>{_esc(r.code)}</td>"
            f"<td style='{_TD}'>{_esc(str(r.name))}</td>"
            f"<td style='{_TD}'>{_fmt_amount(r.short_amount)}</td>"
            f"<td style='{_TD}'>{_fmt_pct(ssr)}</td>"
            f"<td style='{_TD}'>{'样本不足' if pct is None else f'{pct:.0f}%'}</td>"
            f"<td style='{_TD}'>{_esc(_top20_tag(w_i, pct))}</td></tr>"
        )
    head = "".join(
        f"<th style='{_TH}'>{_esc(c)}</th>"
        for c in ("代码", "名称", "沽空额", "SSR", "SSR 60日分位", "状态标签")
    )
    return (
        f'<div class="panel" id="panel-hk-top20">'
        f'<div class="panel-title">当日沽空额 TOP20（股票口径，不含 ETF）</div>'
        f'<div style="overflow-x:auto"><table style="border-collapse:collapse;font-size:12px">'
        f"<thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div></div>"
    )
