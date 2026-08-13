# tests/flow_dashboard/indicators/test_margin_industry.py
"""行业聚合 indicator 测试。"""
from __future__ import annotations

import pandas as pd
import pytest

from flow_dashboard.indicators.margin import (
    aggregate_margin_by_industry,
    compute_net_margin_change,
)


def _margin_df():
    """2 只股票 × 2 天的个股两融。"""
    return pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "ts_code": "000001.SZ",
         "rzye": 1e9, "rqye": 1e8},
        {"trade_date": pd.Timestamp("2026-08-07"), "ts_code": "600000.SH",
         "rzye": 2e9, "rqye": 2e8},
        {"trade_date": pd.Timestamp("2026-08-08"), "ts_code": "000001.SZ",
         "rzye": 1.1e9, "rqye": 1.1e8},
        {"trade_date": pd.Timestamp("2026-08-08"), "ts_code": "600000.SH",
         "rzye": 2.1e9, "rqye": 2.1e8},
    ])


def _members_daily():
    """PIT 展开：2 只股票分别属于不同行业。"""
    return pd.DataFrame([
        {"trade_date": "2026-08-07", "con_code": "000001.SZ",
         "industry_code": "801770", "industry_name": "银行"},
        {"trade_date": "2026-08-07", "con_code": "600000.SH",
         "industry_code": "801780", "industry_name": "非银金融"},
        {"trade_date": "2026-08-08", "con_code": "000001.SZ",
         "industry_code": "801770", "industry_name": "银行"},
        {"trade_date": "2026-08-08", "con_code": "600000.SH",
         "industry_code": "801780", "industry_name": "非银金融"},
    ])


def test_aggregate_margin_by_industry_basic():
    out = aggregate_margin_by_industry(_margin_df(), _members_daily())
    # 2 行业 × 2 天 = 4 行
    assert len(out) == 4
    # 银行 08-07：rzye=1e9, rqye=1e8
    row = out[(out["industry_code"] == "801770") & (out["trade_date"] == pd.Timestamp("2026-08-07"))].iloc[0]
    assert row["rzye"] == 1e9
    assert row["rqye"] == 1e8


def test_aggregate_margin_by_industry_groups_correctly():
    """同一行业多只股票应聚合。"""
    margin = pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "ts_code": "000001.SZ",
         "rzye": 1e9, "rqye": 1e8},
        {"trade_date": pd.Timestamp("2026-08-07"), "ts_code": "000002.SZ",
         "rzye": 2e9, "rqye": 2e8},
    ])
    members = pd.DataFrame([
        {"trade_date": "2026-08-07", "con_code": "000001.SZ",
         "industry_code": "801770", "industry_name": "银行"},
        {"trade_date": "2026-08-07", "con_code": "000002.SZ",
         "industry_code": "801770", "industry_name": "银行"},
    ])
    out = aggregate_margin_by_industry(margin, members)
    # 1 行业 × 1 天 = 1 行，rzye 求和 = 3e9
    assert len(out) == 1
    assert out.iloc[0]["rzye"] == 3e9


def test_aggregate_margin_by_industry_pit_membership_change():
    """PIT 关键：股票 08-08 起换行业，应分别计入。"""
    margin = pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "ts_code": "000001.SZ",
         "rzye": 1e9, "rqye": 1e8},
        {"trade_date": pd.Timestamp("2026-08-08"), "ts_code": "000001.SZ",
         "rzye": 2e9, "rqye": 2e8},
    ])
    members = pd.DataFrame([
        {"trade_date": "2026-08-07", "con_code": "000001.SZ",
         "industry_code": "801770", "industry_name": "银行"},
        {"trade_date": "2026-08-08", "con_code": "000001.SZ",
         "industry_code": "801780", "industry_name": "非银金融"},
    ])
    out = aggregate_margin_by_industry(margin, members)
    bank_0807 = out[(out["industry_code"] == "801770") & (out["trade_date"] == pd.Timestamp("2026-08-07"))]
    nonbank_0808 = out[(out["industry_code"] == "801780") & (out["trade_date"] == pd.Timestamp("2026-08-08"))]
    assert len(bank_0807) == 1 and bank_0807.iloc[0]["rzye"] == 1e9
    assert len(nonbank_0808) == 1 and nonbank_0808.iloc[0]["rzye"] == 2e9


def test_aggregate_margin_by_industry_drops_stocks_without_industry():
    """个股两融里有但申万成分股里没有的股票（如新股），应被忽略 + 不抛错。"""
    margin = pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "ts_code": "NEW.SZ",
         "rzye": 1e9, "rqye": 1e8},
    ])
    members = pd.DataFrame(
        columns=["trade_date", "con_code", "industry_code", "industry_name"]
    )
    out = aggregate_margin_by_industry(margin, members)
    assert out.empty


def _industry_df():
    """1 行业 × 7 天的聚合表（用于测 5 日变化）。"""
    rows = []
    base = pd.Timestamp("2026-08-01")
    for i in range(7):
        rows.append({
            "trade_date": base + pd.Timedelta(days=i),
            "industry_code": "801770",
            "industry_name": "银行",
            "rzye": 1e9 + i * 1e8,  # 每日 +1e8
            "rqye": 1e8 + i * 1e7,
            "net_margin": (1e9 + i * 1e8) - (1e8 + i * 1e7),
            "stock_count": 10,
        })
    return pd.DataFrame(rows)


def test_compute_net_margin_change_5d():
    df = compute_net_margin_change(_industry_df(), n_trading_days=5)
    # 前 5 天变化为 NaN（无 t-5）；第 6、7 天有变化
    assert df["net_margin_5d_change"].isna().sum() == 5
    # 第 7 天（i=6）：net_margin(t) - net_margin(t-5)
    # net_margin(t=6) = (1.6e9 - 1.6e8) = 1.44e9
    # net_margin(t-5=1) = (1.1e9 - 1.1e8) = 0.99e9
    # 期望变化 = 1.44e9 - 0.99e9 = 4.5e8
    row_7 = df[df["trade_date"] == pd.Timestamp("2026-08-07")].iloc[0]
    expected = 4.5e8
    assert abs(row_7["net_margin_5d_change"] - expected) < 1.0  # 浮点容差


def test_compute_net_margin_change_per_industry():
    """多行业时各自独立算 5 日变化。"""
    df_a = _industry_df()
    df_b = _industry_df().copy()
    df_b["industry_code"] = "801780"
    df_b["industry_name"] = "非银金融"
    df = pd.concat([df_a, df_b], ignore_index=True)
    out = compute_net_margin_change(df, n_trading_days=5)
    # 每个行业 7 行 × 5 NaN = 10 NaN
    assert out["net_margin_5d_change"].isna().sum() == 10


def test_compute_net_margin_change_empty_df():
    empty = pd.DataFrame(columns=[
        "trade_date", "industry_code", "industry_name",
        "rzye", "rqye", "net_margin", "stock_count",
    ])
    out = compute_net_margin_change(empty, n_trading_days=5)
    assert out.empty
    assert "net_margin_5d_change" in out.columns
