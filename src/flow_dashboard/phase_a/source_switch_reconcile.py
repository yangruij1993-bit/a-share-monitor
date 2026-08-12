"""etf_share_size vs fund_share 源切换对账。

per spec §1.3:
- etf_share_size 为首版主源；fund_share 仅补主源最早覆盖日之前历史
- 两源重叠期逐 ETF 对账
- 换源边界两侧数值不一致时输出 source_switch_break
"""
from __future__ import annotations

import pandas as pd

from flow_dashboard.data.tushare_client import get_pro_api


def reconcile_share_sources(
    etf_share: pd.DataFrame,
    fund_share: pd.DataFrame,
    tolerance_pct: float = 0.01,
) -> pd.DataFrame:
    """逐 (ts_code, trade_date) 对账两源的 share_in_shares。

    输出列: ts_code, trade_date, etf_share_in_shares, fund_share_in_shares,
            abs_diff, diff_pct, flag ∈ {ok, over_tolerance, only_etf, only_fund_share}
    """
    e = etf_share[["ts_code", "trade_date", "share_in_shares"]].rename(
        columns={"share_in_shares": "etf_share_in_shares"}
    )
    f = fund_share[["ts_code", "trade_date", "share_in_shares"]].rename(
        columns={"share_in_shares": "fund_share_in_shares"}
    )
    merged = pd.merge(e, f, on=["ts_code", "trade_date"], how="outer")
    merged["abs_diff"] = (merged["etf_share_in_shares"] - merged["fund_share_in_shares"]).abs()
    merged["diff_pct"] = merged["abs_diff"] / merged[["etf_share_in_shares", "fund_share_in_shares"]].mean(axis=1)

    def _flag(row):
        if pd.isna(row["etf_share_in_shares"]):
            return "only_fund_share"
        if pd.isna(row["fund_share_in_shares"]):
            return "only_etf"
        if pd.isna(row["diff_pct"]):
            return "ok"
        if abs(row["diff_pct"]) > tolerance_pct:
            return "over_tolerance"
        return "ok"

    merged["flag"] = merged.apply(_flag, axis=1)
    return merged.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)


def fetch_fund_share(
    codes: list[str],
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """从 Tushare fund_share 拉取并规范化为 share_in_shares（份）。

    fund_share 原始字段 fd_share 单位万份；share_in_shares = fd_share * 10000。
    本函数与 etf_share_size 共享单位，便于直接 diff。
    """
    pro = get_pro_api()
    frames = []
    for code in codes:
        df = pro.fund_share(ts_code=code, start_date=start_date, end_date=end_date)
        if df is not None and not df.empty:
            frames.append(df[["ts_code", "trade_date", "fd_share"]])
    if not frames:
        return pd.DataFrame(columns=["ts_code", "trade_date", "share_in_shares"])
    df = pd.concat(frames, ignore_index=True).copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d", errors="coerce")
    df["fd_share"] = pd.to_numeric(df["fd_share"], errors="coerce")
    df["share_in_shares"] = df["fd_share"] * 10000
    return df.drop_duplicates(subset=["ts_code", "trade_date"]).reset_index(drop=True)
