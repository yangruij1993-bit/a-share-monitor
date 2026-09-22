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
    prev = s.iloc[-window - 1:-1]
    if len(prev) < min_obs:
        return None
    return float((prev < s.iloc[-1]).mean() * 100.0)


def ret_n(close: pd.Series, n: int = 5) -> float | None:
    """n 日收益率（基期价 <=0 → None）。"""
    s = pd.Series(close).dropna().astype(float)
    if len(s) < n + 1 or s.iloc[-1 - n] <= 0:
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


def sfc_stock_metrics(sfc_df: pd.DataFrame, code: str, total_shares: float,
                      *, jump_threshold: float = 0.20) -> dict:
    """个股 SFC：淡仓/总股本比例周环比（bp）及 4 周斜率。隐含价跳变>阈值=公司行动嫌疑→unavailable。"""
    if sfc_df is None or sfc_df.empty or not total_shares or pd.isna(total_shares):
        return {"available": False}
    code5 = str(code).split(".")[0].zfill(5)
    df = sfc_df[sfc_df["code"] == code5].sort_values("position_date")
    if len(df) < 2:
        return {"available": False}
    latest, prev = df.iloc[-1], df.iloc[-2]
    implied_now = latest["short_amount_hkd"] / latest["short_shares"]
    implied_prev = prev["short_amount_hkd"] / prev["short_shares"]
    if implied_prev > 0 and abs(implied_now / implied_prev - 1.0) > jump_threshold:
        return {"available": False, "corp_action_suspect": True}
    p_now = latest["short_shares"] / total_shares
    p_prev = prev["short_shares"] / total_shares
    delta_4w = None
    if len(df) >= 5:
        p_4w = df.iloc[-5]["short_shares"] / total_shares
        delta_4w = float((p_now - p_4w) * 1e4)
    return {
        "available": True,
        "latest_pd": pd.Timestamp(latest["position_date"]),
        "prev_pd": pd.Timestamp(prev["position_date"]),
        "latest_shares": float(latest["short_shares"]),
        "delta_bp": float((p_now - p_prev) * 1e4),
        "delta_4w_bp": delta_4w,
    }


def sfc_market_metrics(sfc_df: pd.DataFrame, shares_df: pd.DataFrame, *,
                       min_comparable: int = 100, min_coverage: float = 0.80) -> dict:
    """市场 SFC：连续两期可比集合上 Σ淡仓金额/Σ市值 的比例差与扩散度。

    市值 = 隐含价（金额/股数）× 总股本（f84 缓存）。覆盖率 = 可比集合 t0 市值
    / 上一期全报告 t0 市值；不足门槛 → unavailable（设计 §6.1）。
    """
    if sfc_df is None or sfc_df.empty or shares_df is None or shares_df.empty:
        return {"available": False}
    pds = sorted(pd.to_datetime(sfc_df["position_date"].unique()))
    if len(pds) < 2:
        return {"available": False}
    latest, prev = pds[-1], pds[-2]
    cols = ["code", "short_shares", "short_amount_hkd"]
    cur = sfc_df[sfc_df["position_date"] == latest][cols]
    old = sfc_df[sfc_df["position_date"] == prev][cols]
    m = cur.merge(old, on="code", suffixes=("_t1", "_t0"))
    sh = shares_df[["code", "total_shares"]].drop_duplicates("code")
    m = m.merge(sh, on="code", how="left")
    m = m[(m["total_shares"] > 0)
          & (m["short_shares_t0"] > 0) & (m["short_shares_t1"] > 0)]
    if len(m) < min_comparable:
        return {"available": False, "n_comparable": int(len(m))}
    m = m.copy()
    m["mcap_t1"] = m["short_amount_hkd_t1"] / m["short_shares_t1"] * m["total_shares"]
    m["mcap_t0"] = m["short_amount_hkd_t0"] / m["short_shares_t0"] * m["total_shares"]
    old_full = old.merge(sh, on="code", how="left")
    old_full = old_full[old_full["total_shares"] > 0]
    denom = ((old_full["short_amount_hkd"] / old_full["short_shares"])
             * old_full["total_shares"]).sum()
    coverage = float(m["mcap_t0"].sum() / denom) if denom > 0 else None
    if coverage is None or coverage < min_coverage:
        return {"available": False, "n_comparable": int(len(m)), "coverage": coverage}
    ratio_t1 = m["short_amount_hkd_t1"].sum() / m["mcap_t1"].sum()
    ratio_t0 = m["short_amount_hkd_t0"].sum() / m["mcap_t0"].sum()
    return {
        "available": True,
        "latest_pd": latest, "prev_pd": prev,
        "delta_bps": float((ratio_t1 - ratio_t0) * 1e4),
        "breadth": float((m["short_shares_t1"] > m["short_shares_t0"]).mean()),
        "n_comparable": int(len(m)),
        "coverage": coverage,
    }
