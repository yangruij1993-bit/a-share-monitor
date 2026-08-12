"""Phase A 覆盖率基线计算。

per spec §2.1 s2_flow_aggregation:
- count_coverage = observed_count / eligible_count
- prior_share_coverage = sum(prior_share[observed]) / sum(prior_share[eligible])
- prior_aum_coverage = sum(prior_aum[observed]) / sum(prior_aum[eligible])

prior_share 与 prior_aum 使用 t 之前最近一个有效观测；本 Phase A 简化为"前一日"。
真正的 PIT 前一有效日逻辑由 Phase B 实现。
"""
from __future__ import annotations

import pandas as pd


def compute_coverage_series(
    flow_df: pd.DataFrame,
    universe: list[str],
) -> pd.DataFrame:
    """逐 (dimension, label, trade_date) 算 3 种覆盖率。

    flow_df 必须含列: ts_code, trade_date, dimension, label,
                     share_in_shares, total_size_cny, etf_estimated_flow_cny
    """
    required = {"ts_code", "trade_date", "dimension", "label",
                "share_in_shares", "total_size_cny"}
    missing = required - set(flow_df.columns)
    if missing:
        raise ValueError(f"flow_df 缺列: {missing}")

    df = flow_df.sort_values(["dimension", "label", "trade_date", "ts_code"]).copy()
    eligible_set = set(universe)
    n_eligible = len(eligible_set)

    rows: list[dict] = []
    for (dim, label, trade_date), group in df.groupby(["dimension", "label", "trade_date"], sort=False):
        observed = set(group["ts_code"]) & eligible_set
        n_observed = len(observed)

        prev_mask = (
            (df["dimension"] == dim)
            & (df["label"] == label)
            & (df["trade_date"] < trade_date)
        )
        prev_df = df[prev_mask]
        if not prev_df.empty:
            prev_max_date = prev_df["trade_date"].max()
            prev_snapshot = prev_df[prev_df["trade_date"] == prev_max_date]
        else:
            prev_snapshot = prev_df.iloc[0:0]

        prev_eligible = prev_snapshot[prev_snapshot["ts_code"].isin(eligible_set)]
        prior_share_eligible = prev_eligible["share_in_shares"].sum()
        prior_aum_eligible = prev_eligible["total_size_cny"].sum()

        prev_observed = prev_eligible[prev_eligible["ts_code"].isin(observed)]
        prior_share_observed = prev_observed["share_in_shares"].sum()
        prior_aum_observed = prev_observed["total_size_cny"].sum()

        count_cov = n_observed / n_eligible if n_eligible else float("nan")
        prior_share_cov = (
            prior_share_observed / prior_share_eligible
            if prior_share_eligible else float("nan")
        )
        prior_aum_cov = (
            prior_aum_observed / prior_aum_eligible
            if prior_aum_eligible else float("nan")
        )

        rows.append({
            "dimension": dim, "label": label, "trade_date": trade_date,
            "eligible_count": n_eligible, "observed_count": n_observed,
            "count_coverage": count_cov,
            "prior_share_coverage": prior_share_cov,
            "prior_aum_coverage": prior_aum_cov,
        })
    return pd.DataFrame(rows).sort_values(["dimension", "label", "trade_date"]).reset_index(drop=True)
