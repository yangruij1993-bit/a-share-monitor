"""hk_short 状态引擎（设计 §6.3 判断顺序 + §6.4 状态矩阵，纯规则）。

冻结原则：
- 状态按矩阵自上而下匹配，首个命中即返回，未命中返回"暂时无法确认"
- 任何需要淡仓方向的状态在 oi=unavailable 时不得输出（含"活跃但净仓有限"，
  该状态要求 淡仓Δ≈0 即 flat，unavailable ≠ ≈0）
- "·SFC待确认"后缀只在超过宽限期仍缺最新一期时添加
- ETF 干扰只加注释，不改状态
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from flow_dashboard.config import HK_THRESHOLDS
from flow_dashboard.data.hk_short.hk_calendar import (
    recent_sfc_position_dates, sfc_grace_deadline,
)

ETF_HEDGE_NOTE = "总沽空增加或主要来自指数对冲，不宜直接解读为个股看空增强"
SFC_PENDING_SUFFIX = "·SFC待确认"
FALL_NOTE = "下跌压力或来自长仓卖盘而非新增空头"
COVER_NOTE = "沽空额仍高，回补或伴随激烈博弈"


@dataclass
class Evidence:
    oi: str = "unavailable"          # up / down / flat / unavailable
    short_high: bool = False
    ssr_high: bool = False
    price: str = "neutral"           # up / down / neutral / unavailable
    participation_high: bool = False
    sfc_pending: bool = False
    etf_interference: bool = False
    notes: list[str] = field(default_factory=list)


def _classify(ev: Evidence) -> dict:
    """§6.4 状态矩阵（自上而下，首个命中即返回）。"""
    state, notes = "暂时无法确认", list(ev.notes)
    if (ev.oi == "up" and ev.short_high and ev.ssr_high
            and ev.price == "down" and ev.participation_high):
        state = "空头净加仓迹象明显"
    elif ev.oi == "up" and ev.price == "up":
        state = "多空分歧扩大"
    elif ev.oi == "down" and ev.price == "up" and ev.participation_high:
        state = "空头净回补迹象明显"
        if ev.short_high:
            notes.append(COVER_NOTE)
    elif ev.short_high and ev.ssr_high and ev.oi == "flat":
        state = "沽空活跃但净仓变化有限"
    elif ev.price == "down" and ev.oi == "down":
        notes.append(FALL_NOTE)

    if ev.etf_interference:
        notes.append(ETF_HEDGE_NOTE)
    if ev.sfc_pending:
        state = state + SFC_PENDING_SUFFIX
    return {"state": state, "notes": notes}


def _market_oi(sfc: dict | None, t: dict) -> str:
    """市场淡仓方向：delta ±3bp 且 breadth 55%/45% 同向才给方向。"""
    if not sfc or not sfc.get("available"):
        return "unavailable"
    d, b = sfc["delta_bps"], sfc["breadth"]
    if d >= t["mkt_sfc_delta_bp"] and b >= t["mkt_sfc_breadth_pos"]:
        return "up"
    if d <= -t["mkt_sfc_delta_bp"] and b <= t["mkt_sfc_breadth_neg"]:
        return "down"
    return "flat"


def _stock_oi(stock_sfc: dict | None, t: dict) -> str:
    if not stock_sfc or not stock_sfc.get("available"):
        return "unavailable"
    d = stock_sfc["delta_bp"]
    if d >= t["stock_sfc_delta_bp"]:
        return "up"
    if d <= -t["stock_sfc_delta_bp"]:
        return "down"
    return "flat"


def market_conclusion(
    *,
    sfc: dict | None = None,
    weekly_short_intensity: float | None = None,
    ssr_percentile: float | None = None,
    price: str = "unavailable",
    participation_high: bool = False,
    sfc_pending: bool = False,
    etf_interference: bool = False,
    extra_notes: list[str] | None = None,
) -> dict:
    t = HK_THRESHOLDS
    ev = Evidence(
        oi=_market_oi(sfc, t),
        short_high=(weekly_short_intensity is not None
                    and weekly_short_intensity >= t["weekly_intensity_high"]),
        ssr_high=(ssr_percentile is not None
                  and ssr_percentile >= t["ssr_pct_high"]),
        price=price,
        participation_high=participation_high,
        sfc_pending=sfc_pending,
        etf_interference=etf_interference,
        notes=list(extra_notes or []),
    )
    return _classify(ev)


def stock_conclusion(
    *,
    sfc: dict | None = None,
    weekly_short_intensity: float | None = None,
    ssr_percentile: float | None = None,
    price: str = "neutral",
    participation_high: bool = False,
    etf_interference: bool = False,
    extra_notes: list[str] | None = None,
) -> dict:
    t = HK_THRESHOLDS
    ev = Evidence(
        oi=_stock_oi(sfc, t),
        short_high=(weekly_short_intensity is not None
                    and weekly_short_intensity >= t["weekly_intensity_high"]),
        ssr_high=(ssr_percentile is not None
                  and ssr_percentile >= t["ssr_pct_high"]),
        price=price,
        participation_high=participation_high,
        etf_interference=etf_interference,
        notes=list(extra_notes or []),
    )
    return _classify(ev)


def sfc_is_pending(*, latest_cached_pd, as_of) -> bool:
    """缓存是否缺失已超宽限期的 SFC 周报（设计 §6.3，勘误修正版）。

    从最新缓存一期之后的第一个应公布周 W（recent 列表中 > 缓存期的最小一周）
    起算：W 的宽限期（position_date 后第 5 个香港交易日 EOD）已过仍缺该期
    → True。宽限期内沿用最新已公布一期，不加"待确认"。
    latest_cached_pd=None（缓存里没有任何一期）→ 恒 True（数据缺失）。
    """
    if latest_cached_pd is None or pd.isna(latest_cached_pd):
        return True
    ts = pd.Timestamp(as_of)
    ts = ts.tz_convert("Asia/Shanghai").tz_localize(None) if ts.tzinfo else ts
    recent = recent_sfc_position_dates(ts, n=8)
    if not recent:
        return False
    cached = pd.Timestamp(latest_cached_pd).normalize()
    newer = [w for w in recent if w > cached]
    if not newer:
        return False  # 已含最新已完成周
    return ts > sfc_grace_deadline(min(newer))
