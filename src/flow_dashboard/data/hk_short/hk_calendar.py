"""香港交易日历（2026 假日硬编码）+ SFC 宽限期。

设计 §6.3：宽限期 = position_date 后第 5 个香港交易日（EOD）。
注意：2026-04-04 为复活节周六；清明 2026-04-05 为周日、补假未定 → 未列入；该周如遇空数据由 loader 容错。
年份 > 2026：假日表缺失，回退仅过滤周末并 log 告警（届时须更新假日表）。

时间语义（与 runner 18:45 收盘后触发对齐）：
- 纯日期输入（午夜）= 问"当日开盘前"，当日不计入（周一 → 上周五）；
- 带具体时间的时间戳且当日为交易日 → 当日计入（EOD runner / @live 冒烟）。
"""
from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)

HK_HOLIDAYS_2026 = {
    # 元旦
    "2026-01-01",
    # 农历年初二/三/四（首日 02-17 周二）
    "2026-02-17", "2026-02-18", "2026-02-19",
    # 耶稣受难日 / 复活节周六 / 复活节周一
    "2026-04-03", "2026-04-04", "2026-04-06",
    # 劳动节 / 佛诞 / 特区成立纪念日
    "2026-05-01", "2026-05-25", "2026-06-19", "2026-07-01",
    # 国庆 / 重阳
    "2026-10-01", "2026-10-19",
    # 圣诞 / 圣诞翌日
    "2026-12-25", "2026-12-28",
}

_warned = {"flag": False}


def _to_naive(ts: pd.Timestamp) -> pd.Timestamp:
    """tz-aware → Asia/Shanghai 语义的 naive 时间戳（保留时间分量）。"""
    if ts.tzinfo is not None:
        ts = ts.tz_convert("Asia/Shanghai").tz_localize(None)
    return ts


def _norm(d) -> pd.Timestamp:
    return _to_naive(pd.Timestamp(d)).normalize()


def is_hk_trading_day(d) -> bool:
    ts = _norm(d)
    if ts.weekday() >= 5:
        return False
    if ts.year == 2026:
        return ts.strftime("%Y-%m-%d") not in HK_HOLIDAYS_2026
    if ts.year > 2026 and not _warned["flag"]:
        log.warning("HK holiday table only covers 2026; %s falls back to weekday-only", ts.date())
        _warned["flag"] = True
    return True


def latest_trading_day_on_or_before(d) -> pd.Timestamp:
    """最近一个"已收盘"的香港交易日。

    纯日期（午夜）输入：当日不计入，回溯到前一交易日（周一 → 上周五；
    假日 → 前一交易日）。带时间输入且当日为交易日：当日计入（EOD runner
    收盘后调用；@live 冒烟传 now-1d 带时间，同样落到上一完整交易日）。
    """
    ts = _to_naive(pd.Timestamp(d))
    day = ts.normalize()
    if ts != day and is_hk_trading_day(day):
        return day
    ts = day - pd.Timedelta(days=1)
    while not is_hk_trading_day(ts):
        ts -= pd.Timedelta(days=1)
    return ts


def prev_trading_day(d) -> pd.Timestamp:
    """严格早于 d 的最近一个香港交易日。"""
    ts = _norm(d) - pd.Timedelta(days=1)
    while not is_hk_trading_day(ts):
        ts -= pd.Timedelta(days=1)
    return ts


def next_trk_days(d, n: int) -> list[pd.Timestamp]:
    """严格在 d 之后的 n 个香港交易日（升序）。"""
    out: list[pd.Timestamp] = []
    ts = _norm(d)
    while len(out) < n:
        ts += pd.Timedelta(days=1)
        if is_hk_trading_day(ts):
            out.append(ts.normalize())
    return out


def sfc_grace_deadline(position_date) -> pd.Timestamp:
    """position_date 后第 5 个香港交易日的 EOD（设计 §6.3）。"""
    days = next_trk_days(position_date, 5)
    return days[-1] + pd.Timedelta(hours=23, minutes=59, seconds=59)


def recent_sfc_position_dates(as_of, n: int = 8) -> list[pd.Timestamp]:
    """最近 n 个"已结束交易周"的最后一个香港交易日（降序）。

    本周若已过周五（含周末），其周五也计入；本周未到周五则从上周五开始，
    并继续向更早的交易周回溯，直到取满 n 期。
    """
    ts = _norm(as_of)
    monday = ts - pd.Timedelta(days=ts.weekday())
    out: list[pd.Timestamp] = []
    k = 0
    while len(out) < n:
        week_mon = monday - pd.Timedelta(weeks=k)
        week_sun = week_mon + pd.Timedelta(days=6)
        d = week_sun
        while d >= week_mon and not is_hk_trading_day(d):
            d -= pd.Timedelta(days=1)
        if d >= week_mon and d < ts:
            out.append(d.normalize())
        k += 1
    return out
