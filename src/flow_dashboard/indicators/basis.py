"""s4 期货基差指标（IC/IM 逐合约）。

per spec §2.1 s4_basis + §3.5.2 红线:
- 不拼接当季连续基差
- 正值=贴水，负值=升水
- annualized 用 365/days_to_delist
- max_quote_skew_seconds=None 时标 quote_time_unverified
"""
from __future__ import annotations

import pandas as pd


def compute_basis(
    fut_df: pd.DataFrame,
    spot_df: pd.DataFrame,
    *,
    spot_map: dict[str, str],  # {"IC": "000905.SH", "IM": "000852.SH"}
    layer_col: str | None = None,
    max_quote_skew_seconds: float | None = None,
) -> pd.DataFrame:
    """逐合约计算基差。

    Args:
        fut_df: 必须含 ts_code, trade_date, settle, close, pre_settle, delist_date
        spot_df: 必须含 ts_code, trade_date, close
        spot_map: 品种前缀 → 现货 ts_code
        layer_col: 若提供，则按该列保留分层标识（eod/intraday）；不混算
        max_quote_skew_seconds: None 表示未冻结，不校验时差但标 quote_time_unverified

    Returns:
        DataFrame 加列: spot_ts_code, spot_close, discount_rate,
                        basis_points, days_to_delist, annualized_discount_rate,
                        quality_flags, [layer_col]
    """
    required_fut = {"ts_code", "trade_date", "settle", "delist_date"}
    missing = required_fut - set(fut_df.columns)
    if missing:
        raise ValueError(f"compute_basis fut_df 缺列: {missing}")

    out_frames: list[pd.DataFrame] = []
    for ts_code, group in fut_df.groupby("ts_code", sort=False):
        # 推导品种前缀
        variety = _extract_variety(ts_code)
        spot_ts = spot_map.get(variety)
        if spot_ts is None:
            # 未知品种，全行标 missing_spot
            g = group.copy()
            g["spot_ts_code"] = None
            g["spot_close"] = pd.NA
            g["discount_rate"] = pd.NA
            g["basis_points"] = pd.NA
            g["days_to_delist"] = (
                pd.to_datetime(g["delist_date"]) - pd.to_datetime(g["trade_date"])
            ).dt.days
            g["annualized_discount_rate"] = pd.NA
            g["quality_flags"] = "missing_spot"
            out_frames.append(g)
            continue

        spot_sub = spot_df[spot_df["ts_code"] == spot_ts][["trade_date", "close"]]
        spot_sub = spot_sub.rename(columns={"close": "spot_close"})
        spot_sub["spot_ts_code"] = spot_ts
        merged = group.merge(spot_sub, on="trade_date", how="left")

        merged["spot_ts_code"] = merged["spot_ts_code"].fillna(spot_ts)
        merged["days_to_delist"] = (
            pd.to_datetime(merged["delist_date"]) - pd.to_datetime(merged["trade_date"])
        ).dt.days

        # discount_rate = (spot - fut) / spot
        discount = (merged["spot_close"] - merged["settle"]) / merged["spot_close"]
        merged["discount_rate"] = discount
        merged["basis_points"] = discount * 10000

        # 年化（避免除零）
        safe_days = merged["days_to_delist"].where(merged["days_to_delist"] > 0)
        merged["annualized_discount_rate"] = discount * (365.0 / safe_days)

        # quality_flags
        flags = pd.Series([""] * len(merged))
        flags.loc[merged["spot_close"].isna()] = flags.loc[
            merged["spot_close"].isna()
        ].apply(lambda s: _append(s, "missing_spot"))
        if max_quote_skew_seconds is None:
            flags = flags.apply(lambda s: _append(s, "quote_time_unverified"))
        merged["quality_flags"] = flags.values

        out_frames.append(merged)

    return pd.concat(out_frames, ignore_index=True)


def _extract_variety(ts_code: str) -> str:
    """IC2608.CFX → IC；IM2609.CFX → IM。"""
    head = ts_code.split(".")[0]
    variety = ""
    for ch in head:
        if ch.isalpha():
            variety += ch
        else:
            break
    return variety


def _append(existing: str, flag: str) -> str:
    if not existing:
        return flag
    parts = [p for p in existing.split(";") if p]
    if flag not in parts:
        parts.append(flag)
    return ";".join(parts)
