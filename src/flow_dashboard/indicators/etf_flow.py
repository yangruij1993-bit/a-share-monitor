"""s1 ETF 资金流指标。

per spec §2.1:
    etf_estimated_flow_cny[t] = (share_in_shares[t] - share_in_shares[t-1]) × nav[t]

spec §1.3 红线:
- nav 缺失时标 missing_nav，禁止用 close 价代替
- 第一日无 t-1 时标 no_prior_share
- 多 ETF 按 ts_code group
"""
from __future__ import annotations

import pandas as pd


def compute_etf_flow(df: pd.DataFrame) -> pd.DataFrame:
    """计算 ETF 资金流。

    输入 df 必须含: ts_code, trade_date, share_in_shares, unit_nav, total_size_cny, quality_flags
    返回 df 加列: etf_estimated_flow_cny；并更新 quality_flags。
    """
    required = {"ts_code", "trade_date", "share_in_shares", "unit_nav", "quality_flags"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"compute_etf_flow 缺列: {missing}")

    df = df.sort_values(["ts_code", "trade_date"]).reset_index(drop=True).copy()
    df["etf_estimated_flow_cny"] = pd.NA

    rows: list[pd.DataFrame] = []
    for ts_code, group in df.groupby("ts_code", sort=False):
        group = group.sort_values("trade_date").reset_index(drop=True).copy()
        prev_share = group["share_in_shares"].shift(1)
        delta = group["share_in_shares"] - prev_share
        nav = group["unit_nav"]

        flow = delta * nav  # 任一为 NaN → NaN
        group["etf_estimated_flow_cny"] = flow.astype(float)

        # quality_flags 更新
        flags = group["quality_flags"].fillna("").astype(str).copy()
        # 第一行（无前日份额）
        no_prior = prev_share.isna()
        flags.loc[no_prior] = flags.loc[no_prior].apply(
            lambda s: _append_flag(s, "no_prior_share")
        )
        # nav 缺失
        missing_nav = nav.isna()
        flags.loc[missing_nav] = flags.loc[missing_nav].apply(
            lambda s: _append_flag(s, "missing_nav")
        )
        group["quality_flags"] = flags
        rows.append(group)

    return pd.concat(rows, ignore_index=True).sort_values(["ts_code", "trade_date"]).reset_index(drop=True)


def _append_flag(existing: str, flag: str) -> str:
    if not existing:
        return flag
    parts = [p for p in existing.split(";") if p]
    if flag not in parts:
        parts.append(flag)
    return ";".join(parts)
