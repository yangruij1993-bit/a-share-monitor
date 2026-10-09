"""s2 流量聚合：周度/月度/YTD/3Y 累计。

per spec §2.1 + §3.5 共通验收:
- 累计流量在 ETF 覆盖不全时不应继续累加（coverage_gates）
- coverage_gates 未冻结（None）时，cumulative_flow_ytd / 3y 不返回伪数据
- 周度按 ISO week（week_start 为周一）
- 月度按日历月（month_start 为月初）
"""
from __future__ import annotations

import pandas as pd

_SCOPE_MERGE = {"tech": "industry", "growth": "broad", "cycle": "industry"}
_SCOPE_DETAIL = {"growth": "broad", "industry": "industry_core"}


def dedup_flow_by_etf_day(flow_df: pd.DataFrame) -> pd.DataFrame:
    """跨标签聚合前按 (ts_code, trade_date) 去重。

    pipeline 在 compute_etf_flow 之后 merge pit_labels，同一 (ts_code, trade_date)
    会按标签数复制多行（如 510050 同时挂 huijin/broad/csi50 三行）。
    任何"把不同标签的行加总"的面板（全市场合计 / TOP15 / 月度合计）必须先
    去重，否则多标签 ETF 会被重复计数。
    """
    if flow_df.empty:
        return flow_df
    return flow_df.drop_duplicates(subset=["ts_code", "trade_date"])


def normalize_asset_scope(
    flow_df: pd.DataFrame, *, merge_subcategories: bool = True
) -> pd.DataFrame:
    """asset_scope 维度归一，并按 (ts_code, trade_date, label) 去重。

    merge_subcategories=True → 两类：宽基 / 行业
    - tech / cycle 并入 industry（科技、钢铁、煤炭均属行业口径）
    - growth 并入 broad（创业板 ETF 归宽基，与宽基面板一致）

    merge_subcategories=False → 细分：宽基 / 行业(传统) / 科技 / 周期
    - growth 并入 broad；industry 重命名为 industry_core 以区分行业全口径

    输入应已过滤 dimension == "asset_scope"。归一后每只 ETF 每日只计一次，
    各段之和 = 全市场合计（不重复计数）。
    """
    if flow_df.empty:
        return flow_df
    df = flow_df.copy()
    mapping = _SCOPE_MERGE if merge_subcategories else _SCOPE_DETAIL
    df["label"] = df["label"].map(mapping).fillna(df["label"])
    return df.drop_duplicates(subset=["ts_code", "trade_date", "label"])


def aggregate_weekly_flow(flow_df: pd.DataFrame) -> pd.DataFrame:
    """按 (dimension, label, week_start) 聚合 etf_estimated_flow_cny。"""
    df = flow_df.copy()
    df["week_start"] = df["trade_date"] - pd.to_timedelta(
        df["trade_date"].dt.weekday, unit="D"
    )
    grouped = df.groupby(["dimension", "label", "week_start"], as_index=False).agg(
        etf_estimated_flow_cny=("etf_estimated_flow_cny", "sum"),
        n_days=("trade_date", "count"),
        first_observed_at=("first_observed_at", "min") if "first_observed_at" in df.columns else ("trade_date", "min"),
    )
    return grouped.sort_values(["dimension", "label", "week_start"]).reset_index(drop=True)


def aggregate_monthly_flow(flow_df: pd.DataFrame) -> pd.DataFrame:
    """按 (dimension, label, month_start) 聚合。"""
    df = flow_df.copy()
    df["month_start"] = df["trade_date"].dt.to_period("M").dt.to_timestamp()
    grouped = df.groupby(["dimension", "label", "month_start"], as_index=False).agg(
        etf_estimated_flow_cny=("etf_estimated_flow_cny", "sum"),
        n_days=("trade_date", "count"),
    )
    return grouped.sort_values(["dimension", "label", "month_start"]).reset_index(drop=True)


def cumulative_flow_ytd(
    flow_df: pd.DataFrame,
    coverage_gate: float | None = 1.0,
) -> pd.DataFrame:
    """YTD 累计流量。coverage_gate=None 时返回空（不冻结不累加）。"""
    if coverage_gate is None:
        return pd.DataFrame(columns=["dimension", "label", "year", "cumulative_flow_cny"])
    df = flow_df.copy()
    df["year"] = df["trade_date"].dt.year
    grouped = df.groupby(["dimension", "label", "year"], as_index=False).agg(
        cumulative_flow_cny=("etf_estimated_flow_cny", "sum"),
    )
    return grouped.sort_values(["dimension", "label", "year"]).reset_index(drop=True)


def cumulative_flow_3y(
    flow_df: pd.DataFrame,
    as_of: pd.Timestamp,
    coverage_gate: float | None = 1.0,
) -> pd.DataFrame:
    """3 年滚动累计。coverage_gate=None 时返回空。"""
    if coverage_gate is None:
        return pd.DataFrame(columns=["dimension", "label", "cumulative_flow_cny"])
    df = flow_df.copy()
    cutoff = pd.Timestamp(as_of) - pd.DateOffset(years=3)
    df = df[df["trade_date"] >= cutoff]
    grouped = df.groupby(["dimension", "label"], as_index=False).agg(
        cumulative_flow_cny=("etf_estimated_flow_cny", "sum"),
        n_days=("trade_date", "count"),
    )
    return grouped.reset_index(drop=True)
