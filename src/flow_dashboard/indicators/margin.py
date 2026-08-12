"""s3 两融市场汇总指标。

per spec §2.1 s3_margin + §3.5 验收:
- market_scope=None 时返回三所分别 + ALL 合计
- weekly_change 用最近 5 个交易日的差
- reconciliation_tolerance 未冻结（None）时，不在面板上标 ok/out_of_tolerance
- 行业热力、个股两融属于 Phase C，本文件不实现
"""
from __future__ import annotations

import pandas as pd


def aggregate_market_margin(
    df: pd.DataFrame,
    *,
    market_scope: list[str] | None = None,
    reconciliation_tolerance_abs: float | None = None,
) -> pd.DataFrame:
    """按 trade_date 聚合 margin_detail。

    Args:
        df: margin_detail（含 trade_date, exchange_id, rzye, rzmre, rzche）
        market_scope: None 或子集 ["SSE", "SZSE", "BSE"]
                     None 表示保留全部三所，并加 ALL 行
        reconciliation_tolerance_abs: None 表示未冻结，不做对账校验

    Returns:
        DataFrame: trade_date, exchange_id, rzye, rzmre, rzche
                   （ALL 行的 exchange_id="ALL"）
    """
    required = {"trade_date", "exchange_id", "rzye", "rzmre", "rzche"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"aggregate_market_margin 缺列: {missing}")

    df = df.copy()
    if market_scope is not None:
        df = df[df["exchange_id"].isin(market_scope)]

    # 明细行
    detail = df[["trade_date", "exchange_id", "rzye", "rzmre", "rzche"]].copy()

    # ALL 行（按 trade_date 汇总）
    all_rows = df.groupby("trade_date", as_index=False).agg(
        rzye=("rzye", "sum"),
        rzmre=("rzmre", "sum"),
        rzche=("rzche", "sum"),
    )
    all_rows["exchange_id"] = "ALL"

    out = pd.concat([detail, all_rows], ignore_index=True)
    return out.sort_values(["trade_date", "exchange_id"]).reset_index(drop=True)


def compute_weekly_change(
    df: pd.DataFrame,
    n_trading_days: int = 5,
) -> pd.DataFrame:
    """按 exchange_id 分组，计算 rzye[rzye - rzye(t-n_trading_days)]。

    Args:
        df: 含 trade_date, exchange_id, rzye（已按 exchange_id 排序或未排）
        n_trading_days: 默认 5（一周 5 个交易日）

    Returns:
        df 增加 weekly_change_rzye 列
    """
    df = df.copy().sort_values(["exchange_id", "trade_date"]).reset_index(drop=True)
    out_frames: list[pd.DataFrame] = []
    for exch, group in df.groupby("exchange_id", sort=False):
        group = group.sort_values("trade_date").reset_index(drop=True).copy()
        group["weekly_change_rzye"] = group["rzye"] - group["rzye"].shift(n_trading_days)
        out_frames.append(group)
    return pd.concat(out_frames, ignore_index=True).sort_values(
        ["trade_date", "exchange_id"]
    ).reset_index(drop=True)
