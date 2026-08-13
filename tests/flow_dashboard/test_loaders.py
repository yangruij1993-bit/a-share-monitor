"""loaders 契约测试：PIT 过滤、缓存命中、审计列、单位。"""
from __future__ import annotations

import pandas as pd
import pytest

from flow_dashboard.data.loaders import load_etf_share, load_margin, load_fut_daily


def _mock_etf_provider():
    """模拟 3 行 etf_share_size 数据，available_at 不同。"""
    base = pd.Timestamp("2026-08-12 09:00:00", tz="Asia/Shanghai")
    return pd.DataFrame([
        {"ts_code": "510050.SH", "trade_date": pd.Timestamp("2026-08-07"),
         "total_share": 100.0, "total_size": 100.0, "exchange": "SSE",
         "etf_name": "50ETF"},
        {"ts_code": "510050.SH", "trade_date": pd.Timestamp("2026-08-08"),
         "total_share": 105.0, "total_size": 105.0, "exchange": "SSE",
         "etf_name": "50ETF"},
        {"ts_code": "510050.SH", "trade_date": pd.Timestamp("2026-08-11"),
         "total_share": 110.0, "total_size": 110.0, "exchange": "SSE",
         "etf_name": "50ETF"},
    ])


def test_load_etf_share_filters_future_available_at(monkeypatch, tmp_path):
    """as_of < 某行 available_at 时，该行必须被剔除。"""
    df = _mock_etf_provider()
    monkeypatch.setattr(
        "flow_dashboard.data.loaders._pull_etf_share_for_load",
        lambda codes, start, end: df,
    )
    as_of = pd.Timestamp("2026-08-11 08:00:00", tz="Asia/Shanghai")
    out = load_etf_share(
        codes=["510050.SH"],
        start=pd.Timestamp("2026-08-01"),
        end=pd.Timestamp("2026-08-31"),
        as_of=as_of,
        cache_dir=tmp_path,
    )
    assert len(out) == 2  # 只有 8-7 和 8-8 available_at <= as_of
    assert (out["available_at"] <= as_of).all()


def test_load_etf_share_writes_audit_columns(monkeypatch, tmp_path):
    df = _mock_etf_provider()
    monkeypatch.setattr(
        "flow_dashboard.data.loaders._pull_etf_share_for_load",
        lambda codes, start, end: df,
    )
    out = load_etf_share(
        codes=["510050.SH"],
        start=pd.Timestamp("2026-08-01"),
        end=pd.Timestamp("2026-08-31"),
        as_of=pd.Timestamp("2026-08-12 09:00", tz="Asia/Shanghai"),
        cache_dir=tmp_path,
    )
    for col in ("source_date", "first_observed_at", "available_at",
                "fetched_at", "source", "source_version", "is_stale", "quality_flags"):
        assert col in out.columns, f"missing audit col: {col}"
    assert (out["source"] == "tushare").all()
    assert (out["quality_flags"] == "").all()  # 无标记


def test_load_etf_share_cache_hit_skips_network(monkeypatch, tmp_path):
    """第二次 load，cache 内 trade_date 已覆盖到 end-1day → 命中缓存不调 provider。"""
    df = _mock_etf_provider()  # 最新 trade_date = 2026-08-11
    call_count = {"n": 0}

    def mock_pull(codes, start, end):
        call_count["n"] += 1
        return df

    monkeypatch.setattr(
        "flow_dashboard.data.loaders._pull_etf_share_for_load", mock_pull
    )
    as_of = pd.Timestamp("2026-08-12 09:00", tz="Asia/Shanghai")
    # end=2026-08-12 → end-1day=2026-08-11；cache_max=2026-08-11 不 stale
    load_etf_share(
        codes=["510050.SH"], start=pd.Timestamp("2026-08-01"),
        end=pd.Timestamp("2026-08-12"), as_of=as_of, cache_dir=tmp_path,
    )
    load_etf_share(
        codes=["510050.SH"], start=pd.Timestamp("2026-08-01"),
        end=pd.Timestamp("2026-08-12"), as_of=as_of, cache_dir=tmp_path,
    )
    assert call_count["n"] == 1


def test_load_etf_share_stale_cache_refetches(monkeypatch, tmp_path):
    """cache_max 落后于 end-1day → 视为 stale，第二次 load 重拉。"""
    # 模拟 provider：第一次返回旧数据，第二次返回新数据
    state = {"call": 0}

    def mock_pull(codes, start, end):
        state["call"] += 1
        if state["call"] == 1:
            return pd.DataFrame([
                {"ts_code": "510050.SH", "trade_date": pd.Timestamp("2026-08-07"),
                 "total_share": 100.0, "total_size": 100.0, "exchange": "SSE",
                 "etf_name": "50ETF"},
            ])
        return pd.DataFrame([
            {"ts_code": "510050.SH", "trade_date": pd.Timestamp("2026-08-11"),
             "total_share": 110.0, "total_size": 110.0, "exchange": "SSE",
             "etf_name": "50ETF"},
        ])

    monkeypatch.setattr(
        "flow_dashboard.data.loaders._pull_etf_share_for_load", mock_pull
    )
    as_of = pd.Timestamp("2026-08-13 09:00", tz="Asia/Shanghai")
    # 第一次：cache 为空，拉到 8-7
    load_etf_share(
        codes=["510050.SH"], start=pd.Timestamp("2026-08-01"),
        end=pd.Timestamp("2026-08-13"), as_of=as_of, cache_dir=tmp_path,
    )
    # 第二次：cache_max=8-7 < end-1day=8-12 → stale → 重拉
    out = load_etf_share(
        codes=["510050.SH"], start=pd.Timestamp("2026-08-01"),
        end=pd.Timestamp("2026-08-13"), as_of=as_of, cache_dir=tmp_path,
    )
    assert state["call"] == 2  # 重拉一次
    # 合并后最新日期应为 8-11
    assert out["trade_date"].max() == pd.Timestamp("2026-08-11")


def test_load_etf_share_use_cache_false_bypasses(monkeypatch, tmp_path):
    df = _mock_etf_provider()
    call_count = {"n": 0}

    def mock_pull(codes, start, end):
        call_count["n"] += 1
        return df

    monkeypatch.setattr(
        "flow_dashboard.data.loaders._pull_etf_share_for_load", mock_pull
    )
    as_of = pd.Timestamp("2026-08-12 09:00", tz="Asia/Shanghai")
    kwargs = dict(codes=["510050.SH"], start=pd.Timestamp("2026-08-01"),
                  end=pd.Timestamp("2026-08-31"), as_of=as_of, cache_dir=tmp_path)
    load_etf_share(**kwargs)
    load_etf_share(use_cache=False, **kwargs)
    assert call_count["n"] == 2


@pytest.mark.live
def test_load_etf_share_live_integration(tushare_token, tmp_path):
    """端到端：真实拉取 + 缓存 + PIT 过滤。"""
    as_of = pd.Timestamp("2026-08-12 19:30", tz="Asia/Shanghai")
    df = load_etf_share(
        codes=["510050.SH"],
        start=pd.Timestamp("2026-08-01"),
        end=pd.Timestamp("2026-08-12"),
        as_of=as_of,
        cache_dir=tmp_path,
    )
    assert len(df) > 0
    assert (df["available_at"] <= as_of).all()
    assert (df["source"] == "tushare").all()


@pytest.mark.live
def test_load_margin_live_integration(tushare_token, tmp_path):
    as_of = pd.Timestamp("2026-08-12 19:30", tz="Asia/Shanghai")
    df = load_margin(
        start=pd.Timestamp("2026-08-01"),
        end=pd.Timestamp("2026-08-12"),
        as_of=as_of,
        cache_dir=tmp_path,
    )
    assert len(df) > 0
    assert {"SSE", "SZSE", "BSE"}.issubset(set(df["exchange_id"].unique()))


@pytest.mark.live
def test_load_fut_daily_live_integration(tushare_token, tmp_path):
    as_of = pd.Timestamp("2026-08-12 19:30", tz="Asia/Shanghai")
    df = load_fut_daily(
        ts_code="IC2608.CFX",
        start=pd.Timestamp("2026-08-01"),
        end=pd.Timestamp("2026-08-12"),
        as_of=as_of,
        cache_dir=tmp_path,
    )
    assert len(df) > 0
    assert pd.api.types.is_numeric_dtype(df["close"])
