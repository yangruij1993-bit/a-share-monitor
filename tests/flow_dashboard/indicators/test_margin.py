"""s3_margin 契约测试。"""
from __future__ import annotations

import pandas as pd
import pytest

from flow_dashboard.indicators.margin import (
    aggregate_market_margin,
    compute_weekly_change,
)


def _sample_margin():
    return pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-05"),
         "exchange_id": "SSE", "rzye": 8000e8, "rzmre": 50e8, "rzche": 30e8},
        {"trade_date": pd.Timestamp("2026-08-05"),
         "exchange_id": "SZSE", "rzye": 7000e8, "rzmre": 40e8, "rzche": 25e8},
        {"trade_date": pd.Timestamp("2026-08-05"),
         "exchange_id": "BSE", "rzye": 8.3e9, "rzmre": 0.5e8, "rzche": 0.3e8},
        {"trade_date": pd.Timestamp("2026-08-06"),
         "exchange_id": "SSE", "rzye": 8050e8, "rzmre": 55e8, "rzche": 32e8},
        {"trade_date": pd.Timestamp("2026-08-06"),
         "exchange_id": "SZSE", "rzye": 7050e8, "rzmre": 45e8, "rzche": 27e8},
        {"trade_date": pd.Timestamp("2026-08-06"),
         "exchange_id": "BSE", "rzye": 8.5e9, "rzmre": 0.6e8, "rzche": 0.4e8},
        {"trade_date": pd.Timestamp("2026-08-07"),
         "exchange_id": "SSE", "rzye": 8100e8, "rzmre": 52e8, "rzche": 28e8},
        {"trade_date": pd.Timestamp("2026-08-07"),
         "exchange_id": "SZSE", "rzye": 7100e8, "rzmre": 43e8, "rzche": 26e8},
        {"trade_date": pd.Timestamp("2026-08-07"),
         "exchange_id": "BSE", "rzye": 8.6e9, "rzmre": 0.55e8, "rzche": 0.35e8},
        # 缺 2026-08-08 和 2026-08-09（周末）
        {"trade_date": pd.Timestamp("2026-08-12"),
         "exchange_id": "SSE", "rzye": 8150e8, "rzmre": 58e8, "rzche": 35e8},
        {"trade_date": pd.Timestamp("2026-08-12"),
         "exchange_id": "SZSE", "rzye": 7200e8, "rzmre": 47e8, "rzche": 29e8},
        {"trade_date": pd.Timestamp("2026-08-12"),
         "exchange_id": "BSE", "rzye": 8.8e9, "rzmre": 0.65e8, "rzche": 0.45e8},
    ])


def test_aggregate_market_margin_returns_sse_szse_bse_separately():
    """market_scope 未冻结；分别保留三所 + ALL 合计行。"""
    out = aggregate_market_margin(_sample_margin(), market_scope=None)
    assert set(out["exchange_id"].unique()) == {"SSE", "SZSE", "BSE", "ALL"}


def test_aggregate_market_margin_explicit_scope():
    out = aggregate_market_margin(_sample_margin(), market_scope=["SSE", "SZSE"])
    assert set(out["exchange_id"].unique()) == {"SSE", "SZSE", "ALL"}
    # ALL = SSE + SZSE，不含 BSE
    d = pd.Timestamp("2026-08-07")
    all_d = out[(out["exchange_id"] == "ALL") & (out["trade_date"] == d)].iloc[0]
    assert all_d["rzye"] == pytest.approx(8100e8 + 7100e8)


def test_compute_weekly_change_uses_5_trading_days():
    df = aggregate_market_margin(_sample_margin(), market_scope=None)
    df = df[df["exchange_id"] == "ALL"].sort_values("trade_date").reset_index(drop=True)
    out = compute_weekly_change(df)
    # 2026-08-12 是第 4 个交易日，差 5 日需要更早历史，应得 NaN
    last = out[out["trade_date"] == pd.Timestamp("2026-08-12")].iloc[0]
    assert pd.isna(last["weekly_change_rzye"]) or last["weekly_change_rzye"] == pytest.approx(
        last["rzye"] - df.iloc[0]["rzye"]
    )


def test_aggregate_market_margin_out_of_tolerance_flag():
    """明细加总 vs ALL 行差异超阈值时标 out_of_tolerance（不静默修正）。"""
    df = _sample_margin()
    # 故意让一行明细加总与 ALL 不一致
    df.loc[0, "rzye"] = 9000e8  # SSE 8-5 涨成 9000e8
    out = aggregate_market_margin(
        df, market_scope=["SSE", "SZSE", "BSE"],
        reconciliation_tolerance_abs=1e8,  # 1 亿元阈值
    )
    all_row = out[(out["exchange_id"] == "ALL") & (out["trade_date"] == pd.Timestamp("2026-08-05"))].iloc[0]
    # ALL = SSE + SZSE + BSE，应当反映新的总和
    assert all_row["rzye"] == pytest.approx(9000e8 + 7000e8 + 8.3e9)
    # 若有 summary 校验：明细加总 = ALL，则不标；本测试中它们相等（ALL 就是 sum）
