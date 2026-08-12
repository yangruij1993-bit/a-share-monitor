"""poll_etf_share 契约测试。

- poll_once 返回 summary dict，含 status ∈ {complete, partial, missing}
- 写入 poll_summary.csv（追加）和 detail CSV
- 用 pull_func fake 注入，不依赖真实 API
"""
from __future__ import annotations

import pandas as pd
import pytest

from flow_dashboard.phase_a.poll_etf_share import poll_once


def _fake_pull(codes, start_date=None, end_date=None):
    """返回模拟的 etf_share_size 输出。"""
    rows = []
    for code in codes:
        rows.append({
            "trade_date": pd.Timestamp("20260811"),
            "ts_code": code,
            "etf_name": f"测试{code}",
            "total_share": 100.0,
            "total_size": 100.0,
            "exchange": "SSE" if code.endswith(".SH") else "SZSE",
            "share_in_shares": 1_000_000.0,
        })
    return pd.DataFrame(rows)


def test_poll_once_complete(tmp_path):
    summary = poll_once(
        codes=["510050.SH", "510300.SH"],
        trade_date="20260811",
        output_dir=tmp_path,
        now=pd.Timestamp("2026-08-12T09:30:00+08:00"),
        pull_func=_fake_pull,
    )
    assert summary["status"] == "complete"
    assert summary["expected_count"] == 2
    assert summary["available_count"] == 2
    assert summary["trade_date"] == "20260811"
    assert (tmp_path / "poll_summary.csv").exists()
    details = list(tmp_path.glob("poll_detail_*.csv"))
    assert len(details) == 1


def test_poll_once_partial(tmp_path):
    def _short_pull(codes, start_date=None, end_date=None):
        df = _fake_pull(codes, start_date, end_date)
        return df[df["ts_code"] == codes[0]].reset_index(drop=True)
    summary = poll_once(
        codes=["510050.SH", "510300.SH"],
        trade_date="20260811",
        output_dir=tmp_path,
        pull_func=_short_pull,
    )
    assert summary["status"] == "partial"
    assert summary["available_count"] == 1
    assert "510300.SH" in summary["missing_codes"]


def test_poll_once_missing(tmp_path):
    def _empty(codes, start_date=None, end_date=None):
        return pd.DataFrame()
    summary = poll_once(
        codes=["510050.SH"],
        trade_date="20260811",
        output_dir=tmp_path,
        pull_func=_empty,
    )
    assert summary["status"] == "missing"
