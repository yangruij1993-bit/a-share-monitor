"""etf_share_size vs fund_share 对账测试。"""
from __future__ import annotations

import pandas as pd

from flow_dashboard.phase_a.source_switch_reconcile import (
    reconcile_share_sources,
    fetch_fund_share,
)


def _fake_etf_share_size():
    return pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "ts_code": "510050.SH",
         "total_share": 689466.68, "total_size": 2115766.0, "exchange": "SSE",
         "share_in_shares": 689466.68 * 10000, "etf_name": "50ETF"},
        {"trade_date": pd.Timestamp("2026-08-08"), "ts_code": "510050.SH",
         "total_share": 680000.00, "total_size": 2085000.0, "exchange": "SSE",
         "share_in_shares": 680000.00 * 10000, "etf_name": "50ETF"},
    ])


def _fake_fund_share():
    return pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "ts_code": "510050.SH",
         "share_in_shares": 689466.68 * 10000, "source": "fund_share"},
        {"trade_date": pd.Timestamp("2026-08-08"), "ts_code": "510050.SH",
         "share_in_shares": 720000.00 * 10000, "source": "fund_share"},  # 差异 > 5%
    ])


def test_reconcile_flags_large_diff():
    report = reconcile_share_sources(
        etf_share=_fake_etf_share_size(),
        fund_share=_fake_fund_share(),
        tolerance_pct=0.01,
    )
    assert len(report) == 2  # 两天
    flagged = report[report["diff_pct"].abs() > 0.01]
    assert len(flagged) == 1
    assert flagged.iloc[0]["trade_date"] == pd.Timestamp("2026-08-08")


def test_reconcile_handles_disjoint_dates():
    etf = pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "ts_code": "510050.SH",
         "share_in_shares": 100.0 * 10000, "total_size": 100.0, "exchange": "SSE",
         "total_share": 100.0, "etf_name": "X"},
    ])
    fs = pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-08"), "ts_code": "510050.SH",
         "share_in_shares": 100.0 * 10000, "source": "fund_share"},
    ])
    report = reconcile_share_sources(etf_share=etf, fund_share=fs, tolerance_pct=0.01)
    assert report["diff_pct"].isna().all()


def test_fetch_fund_share_signature_contract():
    """fetch_fund_share 必须可被无 token 调用签名校验（不实际拉取）。"""
    import inspect
    sig = inspect.signature(fetch_fund_share)
    assert list(sig.parameters) == ["codes", "start_date", "end_date"]
