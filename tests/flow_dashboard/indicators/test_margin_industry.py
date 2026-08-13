# tests/flow_dashboard/indicators/test_margin_industry.py
"""行业聚合 indicator 测试。"""
from __future__ import annotations

import pandas as pd
import pytest

from flow_dashboard.indicators.margin import aggregate_margin_by_industry


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
