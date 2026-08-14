"""s4 期货基差指标（IC/IM 逐合约）。

per spec §2.1 s4_basis + §3.5.2 红线:
- 不拼接当季连续基差
- 正值=贴水，负值=升水
- annualized 用 365/days_to_delist
- max_quote_skew_seconds=None 时标 quote_time_unverified
"""
from __future__ import annotations

import calendar

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


def _third_friday(year: int, month: int) -> pd.Timestamp:
    """股指期货到期日 = 当月第三个周五。"""
    first_day_wd, _ = calendar.monthrange(year, month)
    first_friday = 1 + (4 - first_day_wd) % 7
    return pd.Timestamp(year=year, month=month, day=first_friday + 14)


def third_friday_of_contract(ts_code: str) -> pd.Timestamp:
    """IC2608.CFX → 2026-08-21（合约月份的第三个周五，即到期日）。"""
    head = ts_code.split(".")[0]
    ym = head[-4:]  # IC2608 → 2608
    year = 2000 + int(ym[:2])
    month = int(ym[2:])
    return _third_friday(year, month)


def tenor_contracts(data_date: pd.Timestamp) -> list[tuple[str, str]]:
    """三档合约月份（当月/当季/下季），返回 [(YYMM, 档位标签)]。

    当月 = data_date 所在月；过了当月第三个周五（到期日）即滚到下月。
    当季 = 当月所在季度的季末月；下季 = 再下一季末。
    同一月份身兼多档时合并标签（如 9 月的当月与当季同为 2609）。
    """
    d = pd.Timestamp(data_date).normalize()
    y, m = d.year, d.month
    if d > _third_friday(y, m):
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    q_m = 3 * ((m - 1) // 3) + 3
    nq_y, nq_m = (y + 1, 3) if q_m == 12 else (y, q_m + 3)

    merged: dict[str, list[str]] = {}
    for tenor, (yy, mm) in [("当月", (y, m)), ("当季", (y, q_m)), ("下季", (nq_y, nq_m))]:
        merged.setdefault(f"{yy % 100:02d}{mm:02d}", []).append(tenor)
    return [(code, "·".join(tenors)) for code, tenors in merged.items()]


def _append(existing: str, flag: str) -> str:
    if not existing:
        return flag
    parts = [p for p in existing.split(";") if p]
    if flag not in parts:
        parts.append(flag)
    return ";".join(parts)
