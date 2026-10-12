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


CHINEXT_CODE_PREFIXES = ("300", "301")


def aggregate_chinext_margin(df: pd.DataFrame) -> pd.DataFrame:
    """按交易日汇总创业板融资余额（个股两融明细 300/301 前缀）。

    Args:
        df: margin_detail，含 trade_date, ts_code, rzye

    Returns:
        DataFrame[trade_date, chinext_rzye]（单位：元），按 trade_date 升序
    """
    out_cols = ["trade_date", "chinext_rzye"]
    if df.empty:
        return pd.DataFrame(columns=out_cols)
    mask = df["ts_code"].str[:3].isin(CHINEXT_CODE_PREFIXES)
    sub = df[mask]
    if sub.empty:
        return pd.DataFrame(columns=out_cols)
    agg = sub.groupby("trade_date", as_index=False).agg(
        chinext_rzye=("rzye", "sum"),
    )
    return agg.sort_values("trade_date").reset_index(drop=True)


def aggregate_margin_by_industry(
    margin_df: pd.DataFrame,
    members_daily: pd.DataFrame,
) -> pd.DataFrame:
    """按申万 L1 行业聚合个股两融。

    PIT 关键：用 members_daily（每日成分表）决定每只股票该日属于哪个行业，
    不用"今天的归属"。

    Args:
        margin_df: 个股两融明细，含 trade_date, ts_code, rzye, rqye
        members_daily: 每日成分股，含 trade_date, con_code, industry_code, industry_name

    Returns:
        DataFrame[trade_date, industry_code, industry_name,
                  rzye, rqye, net_margin (= rzye - rqye), stock_count]
    """
    if margin_df.empty or members_daily.empty:
        return pd.DataFrame(columns=[
            "trade_date", "industry_code", "industry_name",
            "rzye", "rqye", "net_margin", "stock_count",
        ])

    # 对齐 trade_date 类型为 datetime
    margin = margin_df.copy()
    margin["trade_date"] = pd.to_datetime(margin["trade_date"])
    members = members_daily.copy()
    members["trade_date"] = pd.to_datetime(members["trade_date"])

    # 内连接：股票两融 × 行业归属
    merged = margin.merge(
        members,
        left_on=["trade_date", "ts_code"],
        right_on=["trade_date", "con_code"],
        how="inner",
    )
    if merged.empty:
        return pd.DataFrame(columns=[
            "trade_date", "industry_code", "industry_name",
            "rzye", "rqye", "net_margin", "stock_count",
        ])

    # 按行业 × 日期聚合
    agg = merged.groupby(
        ["trade_date", "industry_code", "industry_name"], as_index=False
    ).agg(
        rzye=("rzye", "sum"),
        rqye=("rqye", "sum"),
        stock_count=("ts_code", "count"),
    )
    agg["net_margin"] = agg["rzye"] - agg["rqye"]
    return agg.sort_values(
        ["trade_date", "industry_code"]
    ).reset_index(drop=True)


def compute_net_margin_change(
    df: pd.DataFrame,
    *,
    n_trading_days: int = 5,
) -> pd.DataFrame:
    """按 industry_code 分组，算 net_margin 的 N 日变化。

    Args:
        df: aggregate_margin_by_industry 的输出
        n_trading_days: 滑动窗口（默认 5 个交易日）

    Returns:
        df 增加 net_margin_5d_change 列（前 N-1 日为 NaN）
    """
    if df.empty:
        out = df.copy()
        out["net_margin_5d_change"] = pd.Series(dtype=float)
        return out

    df = df.sort_values(
        ["industry_code", "trade_date"]
    ).reset_index(drop=True).copy()

    out_frames: list[pd.DataFrame] = []
    for industry_code, group in df.groupby("industry_code", sort=False):
        group = group.sort_values("trade_date").reset_index(drop=True).copy()
        group["net_margin_5d_change"] = (
            group["net_margin"] - group["net_margin"].shift(n_trading_days)
        )
        out_frames.append(group)
    return pd.concat(out_frames, ignore_index=True).sort_values(
        ["trade_date", "industry_code"]
    ).reset_index(drop=True)
