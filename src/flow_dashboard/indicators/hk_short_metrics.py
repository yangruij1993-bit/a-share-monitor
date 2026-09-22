"""hk_short 纯函数指标（设计 §6.1，窗口均不含当日；不足观测/除零 → None）。"""
from __future__ import annotations

import pandas as pd


def daily_intensity(series: pd.Series, window: int = 20) -> float | None:
    """日沽空强度 = 当日 / 前 window 个值均值（均值不含当日）。"""
    s = pd.Series(series).dropna().astype(float)
    if len(s) < window + 1:
        return None
    denom = s.iloc[-window - 1:-1].mean()
    return float(s.iloc[-1] / denom) if denom > 0 else None


def weekly_intensity(series: pd.Series, window_days: int = 5,
                     n_windows: int = 12) -> float | None:
    """周沽空强度 = 最近 window_days 合计 / 此前 n_windows 个非重叠窗口均值。"""
    s = pd.Series(series).dropna().astype(float)
    need = window_days * (n_windows + 1)
    if len(s) < need:
        return None
    recent = s.iloc[-window_days:].sum()
    prior = s.iloc[-need:-window_days].to_numpy().reshape(n_windows, window_days)
    denom = prior.sum(axis=1).mean()
    return float(recent / denom) if denom > 0 else None


def percentile_rank(series: pd.Series, window: int = 60,
                    min_obs: int = 20) -> float | None:
    """当日值在前 window 个历史值（不含当日）中的分位（%，严格小于计次）。"""
    s = pd.Series(series).dropna().astype(float)
    if len(s) < min_obs + 1:
        return None
    prev = s.iloc[-window - 1:-1].dropna()
    if len(prev) < min_obs:
        return None
    return float((prev < s.iloc[-1]).mean() * 100.0)


def ret_n(close: pd.Series, n: int = 5) -> float | None:
    s = pd.Series(close).dropna().astype(float)
    if len(s) < n + 1 or s.iloc[-1 - n] == 0:
        return None
    return float(s.iloc[-1] / s.iloc[-1 - n] - 1.0)


def price_direction(hsi_ret5, hstech_ret5, threshold_bp: float = 100.0) -> str:
    """恒指/恒生科技 5 日收益等权平均；±threshold_bp 之外才有方向。"""
    vals = [v for v in (hsi_ret5, hstech_ret5)
            if v is not None and pd.notna(v)]
    if not vals:
        return "unavailable"
    bp = (sum(vals) / len(vals)) * 1e4
    if bp >= threshold_bp:
        return "up"
    if bp <= -threshold_bp:
        return "down"
    return "neutral"


def market_daily_aggregate(em_df: pd.DataFrame, full_days) -> pd.DataFrame:
    """股票口径市场日度聚合：Σ沽空金额 / Σ总成交金额，只用 full 覆盖日。"""
    if em_df.empty:
        return pd.DataFrame()
    df = em_df[em_df["trade_date"].isin(set(pd.to_datetime(list(full_days))))].copy()
    if df.empty:
        return pd.DataFrame()
    g = (df.groupby("trade_date")
         .agg(short_amount=("short_amount", "sum"),
              turnover=("turnover", "sum"),
              n_secs=("code", "nunique"))
         .sort_index().reset_index())
    g["ssr"] = g["short_amount"] / g["turnover"]
    return g


def etf_interference_share(hkex_df: pd.DataFrame, etf_codes, trade_date) -> float | None:
    """当日 ETF 沽空额 / 全口径沽空额（HKEX dayquot 当日值，设计 §6.3 第 6 步）。"""
    if hkex_df is None or hkex_df.empty:
        return None
    day = hkex_df[hkex_df["trade_date"] == pd.Timestamp(trade_date)]
    if day.empty:
        return None
    total = day["short_amount"].sum()
    if total <= 0:
        return None
    etf = day[day["code"].isin(set(etf_codes))]["short_amount"].sum()
    return float(etf / total)


def stock_daily(em_df: pd.DataFrame, code: str) -> pd.DataFrame:
    """个股日频序列（升序），SSR 按金额口径重算：short_amount / turnover。"""
    if em_df.empty:
        return pd.DataFrame()
    code5 = str(code).split(".")[0].zfill(5)
    df = em_df[em_df["code"] == code5].sort_values("trade_date").copy()
    if df.empty:
        return df
    df["ssr"] = df["short_amount"] / df["turnover"]
    return df
