"""Tushare 数据 provider。

逐函数从 行业轮动/src/data/etf.py 白名单迁移；已去除 Oracle、静态名单、sys.path 注入。
每个 pull_* 函数返回 normalized DataFrame，不写盘、不缓存（缓存由上层 loader 决定）。
"""
from __future__ import annotations

import pandas as pd

from flow_dashboard.data.tushare_client import get_pro_api


# ============================================================
# Task 4: fund_basic
# ============================================================

def pull_fund_basic(market: str = "E") -> pd.DataFrame:
    """拉取场内基金（market='E'）基础信息。

    Returns columns: ts_code, name, management, custodian, fund_type,
        found_date, due_date, list_date, issue_date, delist_date, market, status, ...
    """
    pro = get_pro_api()
    df = pro.fund_basic(market=market)
    return _normalize_fund_basic(df)


def _normalize_fund_basic(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ("found_date", "due_date", "list_date", "issue_date", "delist_date"):
        if col in df.columns:
            df[col] = _parse_mixed_date(df[col])
    return df


def _parse_mixed_date(values) -> pd.Series:
    """支持 YYYYMMDD 字符串和 ISO 日期字符串。"""
    s = pd.Series(values).astype("string")
    text = s.fillna("")
    compact = text.str.fullmatch(r"\d{8}")
    parsed = pd.to_datetime(text, errors="coerce")
    if compact.any():
        parsed.loc[compact] = pd.to_datetime(
            text.loc[compact], format="%Y%m%d", errors="coerce"
        )
    return parsed


# ============================================================
# Task 5: etf_share_size
# ============================================================

def pull_etf_share_size(
    codes: list[str],
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    """拉取 ETF 份额规模。

    原始字段：trade_date, ts_code, etf_name, total_share (万份), total_size (万元), exchange.
    标准化后额外字段：share_in_shares = total_share * 10000 (份)。

    spec §1.3 显式要求请求 nav/close；Tushare 当前 endpoint 不返回这两个字段，
    因此本函数不猜测，由上层 loader 写入 quality_flags=missing_nav。
    """
    pro = get_pro_api()
    frames = []
    for code in codes:
        for seg_start, seg_end in _iter_date_segments(start_date, end_date):
            df = pro.etf_share_size(ts_code=code, start_date=seg_start, end_date=seg_end)
            if df is not None and not df.empty:
                frames.append(df)
    if not frames:
        return pd.DataFrame(
            columns=["trade_date", "ts_code", "etf_name", "total_share",
                     "total_size", "exchange", "share_in_shares"]
        )
    combined = pd.concat(frames, ignore_index=True)
    return _normalize_etf_share_size(combined)


def _normalize_etf_share_size(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["trade_date"] = _parse_mixed_date(df["trade_date"])
    df["total_share"] = pd.to_numeric(df["total_share"], errors="coerce")
    df["total_size"] = pd.to_numeric(df["total_size"], errors="coerce")
    df["share_in_shares"] = df["total_share"] * 10000
    return df.drop_duplicates(subset=["ts_code", "trade_date"]).reset_index(drop=True)


def _iter_date_segments(start_date: str | None, end_date: str | None):
    """按自然年分段（Tushare 单次请求默认上限约 5000 行；ETF 份额日频足够）。"""
    if start_date is None or end_date is None:
        yield _fmt_date(start_date), _fmt_date(end_date)
        return
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    if start > end:
        raise ValueError(f"start_date 晚于 end_date: {start_date} > {end_date}")
    current = start
    while current <= end:
        seg_end = min(pd.Timestamp(year=current.year, month=12, day=31), end)
        yield _fmt_date(current), _fmt_date(seg_end)
        current = seg_end + pd.Timedelta(days=1)


def _fmt_date(value) -> str | None:
    if value is None:
        return None
    return pd.Timestamp(value).strftime("%Y%m%d")


# ============================================================
# Task 6: fund_nav, fund_daily, margin
# ============================================================

def pull_fund_nav(
    codes: list[str],
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    """拉取基金净值。spec §1.3 要求保留 ann_date（公告日）。"""
    pro = get_pro_api()
    fields = ["ts_code", "nav_date", "ann_date", "unit_nav", "accum_nav", "adj_nav"]
    frames = []
    for code in codes:
        for seg_start, seg_end in _iter_date_segments(start_date, end_date):
            df = pro.fund_nav(ts_code=code, start_date=seg_start, end_date=seg_end)
            if df is not None and not df.empty:
                frames.append(df[[c for c in fields if c in df.columns]])
    if not frames:
        return pd.DataFrame(columns=fields)
    combined = pd.concat(frames, ignore_index=True)
    df = combined.copy()
    df["nav_date"] = _parse_mixed_date(df["nav_date"])
    if "ann_date" in df.columns:
        df["ann_date"] = _parse_mixed_date(df["ann_date"])
    for col in ("unit_nav", "accum_nav", "adj_nav"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.drop_duplicates(subset=["ts_code", "nav_date"]).reset_index(drop=True)


def pull_fund_daily(
    codes: list[str],
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    """拉取 ETF 二级市场日行情。"""
    pro = get_pro_api()
    fields = ["ts_code", "trade_date", "pre_close", "open", "high", "low",
              "close", "change", "pct_chg", "vol", "amount"]
    frames = []
    for code in codes:
        for seg_start, seg_end in _iter_date_segments(start_date, end_date):
            df = pro.fund_daily(ts_code=code, start_date=seg_start, end_date=seg_end)
            if df is not None and not df.empty:
                frames.append(df[[c for c in fields if c in df.columns]])
    if not frames:
        return pd.DataFrame(columns=["ts_code", "trade_date", "close"])
    combined = pd.concat(frames, ignore_index=True)
    df = combined.copy()
    df["trade_date"] = _parse_mixed_date(df["trade_date"])
    for col in ("pre_close", "open", "high", "low", "close", "change", "vol", "amount"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "pct_chg" in df.columns:
        df["pct_chg"] = pd.to_numeric(df["pct_chg"], errors="coerce")
    return df.drop_duplicates(subset=["ts_code", "trade_date"]).reset_index(drop=True)


def pull_margin(
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    """拉取融资融券汇总（按交易所）。

    spec §1.3: rzye=融资余额, rzmre=融资买入额, rzche=融资偿还额, 单位=元。
    """
    pro = get_pro_api()
    frames = []
    for seg_start, seg_end in _iter_date_segments(start_date, end_date):
        df = pro.margin(start_date=seg_start, end_date=seg_end)
        if df is not None and not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["trade_date", "exchange_id", "rzye", "rzmre", "rzche"])
    df = pd.concat(frames, ignore_index=True).copy()
    df["trade_date"] = _parse_mixed_date(df["trade_date"])
    for col in ("rzye", "rzmre", "rzche", "rqye", "rqmcl", "rzrqye", "rqyl"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.drop_duplicates(subset=["trade_date", "exchange_id"]).reset_index(drop=True)


# ============================================================
# Task 7: fut_basic, fut_daily, index_daily
# ============================================================

def pull_fut_basic(exchange: str = "CFFEX", fut_code: str | None = None) -> pd.DataFrame:
    """拉取期货合约基本信息。"""
    pro = get_pro_api()
    kwargs = {"exchange": exchange}
    if fut_code:
        kwargs["fut_code"] = fut_code
    df = pro.fut_basic(**kwargs)
    df = df.copy()
    for col in ("list_date", "delist_date", "last_ddate"):
        if col in df.columns:
            df[col] = _parse_mixed_date(df[col])
    return df


def pull_fut_daily(
    ts_code: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    """拉取期货日线（含 close 与 settle）。

    spec §1.4: 日终同时保存 eod_close（close）和 eod_settlement（settle）。
    """
    pro = get_pro_api()
    frames = []
    for seg_start, seg_end in _iter_date_segments(start_date, end_date):
        df = pro.fut_daily(ts_code=ts_code, start_date=seg_start, end_date=seg_end)
        if df is not None and not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["ts_code", "trade_date", "close", "settle"])
    df = pd.concat(frames, ignore_index=True).copy()
    df["trade_date"] = _parse_mixed_date(df["trade_date"])
    for col in ("pre_close", "pre_settle", "open", "high", "low",
                "close", "settle", "change1", "change2", "vol", "amount", "oi", "oi_chg"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.drop_duplicates(subset=["ts_code", "trade_date"]).reset_index(drop=True)


def pull_index_daily(
    ts_code: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    """拉取指数日线（CSI500、CSI1000 等现货指数）。"""
    pro = get_pro_api()
    frames = []
    for seg_start, seg_end in _iter_date_segments(start_date, end_date):
        df = pro.index_daily(ts_code=ts_code, start_date=seg_start, end_date=seg_end)
        if df is not None and not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["ts_code", "trade_date", "close"])
    df = pd.concat(frames, ignore_index=True).copy()
    df["trade_date"] = _parse_mixed_date(df["trade_date"])
    for col in ("pre_close", "open", "high", "low", "close", "change", "vol", "amount"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "pct_chg" in df.columns:
        df["pct_chg"] = pd.to_numeric(df["pct_chg"], errors="coerce")
    return df.drop_duplicates(subset=["ts_code", "trade_date"]).reset_index(drop=True)
