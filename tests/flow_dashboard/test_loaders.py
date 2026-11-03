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
    # as_of 09:00 < 19:00 → 可得最新为 08-11；cache_max=2026-08-11 不 stale
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
    """cache_max 落后于 PIT 可得阈值 → 视为 stale，第二次 load 重拉。"""
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
    # 第二次：cache_max=8-7 < 阈值=8-12（as_of 8-13 09:00 → 可得 8-12）→ stale → 重拉
    out = load_etf_share(
        codes=["510050.SH"], start=pd.Timestamp("2026-08-01"),
        end=pd.Timestamp("2026-08-13"), as_of=as_of, cache_dir=tmp_path,
    )
    assert state["call"] == 2  # 重拉一次
    # 合并后最新日期应为 8-11
    assert out["trade_date"].max() == pd.Timestamp("2026-08-11")


def test_load_etf_share_morning_finalize_refetches_latest_day(monkeypatch, tmp_path):
    """早上定稿场景（回归）：T+1 09:15 定稿 end=T，cache 只有 T-1 → 必须重拉。

    旧阈值 end-1day 会把 cache_max=T-1 误判为新鲜，导致图表永远缺最后一个交易日。
    """
    state = {"call": 0}

    def mock_pull(codes, start, end):
        state["call"] += 1
        if state["call"] == 1:
            return pd.DataFrame([
                {"ts_code": "510050.SH", "trade_date": pd.Timestamp("2026-08-12"),
                 "total_share": 100.0, "total_size": 100.0, "exchange": "SSE",
                 "etf_name": "50ETF"},
            ])
        return pd.DataFrame([
            {"ts_code": "510050.SH", "trade_date": pd.Timestamp("2026-08-13"),
             "total_share": 105.0, "total_size": 105.0, "exchange": "SSE",
             "etf_name": "50ETF"},
        ])

    monkeypatch.setattr(
        "flow_dashboard.data.loaders._pull_etf_share_for_load", mock_pull
    )
    as_of = pd.Timestamp("2026-08-14 09:15", tz="Asia/Shanghai")
    load_etf_share(
        codes=["510050.SH"], start=pd.Timestamp("2026-08-01"),
        end=pd.Timestamp("2026-08-13"), as_of=as_of, cache_dir=tmp_path,
    )
    # 第二次：cache_max=8-12，end=8-13，as_of 8-14 09:15 时 8-13 已可得 → stale
    out = load_etf_share(
        codes=["510050.SH"], start=pd.Timestamp("2026-08-01"),
        end=pd.Timestamp("2026-08-13"), as_of=as_of, cache_dir=tmp_path,
    )
    assert state["call"] == 2
    assert out["trade_date"].max() == pd.Timestamp("2026-08-13")


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


def _mock_margin_rows(date, exchanges):
    return pd.DataFrame([
        {"trade_date": pd.Timestamp(date), "exchange_id": ex,
         "rzye": 1e11, "rzmre": 1e9, "rzche": 1e9}
        for ex in exchanges
    ])


def test_load_margin_repairs_partial_latest_day(monkeypatch, tmp_path):
    """回归 2026-11-02：缓存最新交易日缺所（深市发布滞后）时不得短路，
    需重拉补齐缺失交易所。"""
    calls = {"n": 0}

    def mock_pull(start, end):
        calls["n"] += 1
        if calls["n"] == 1:
            frames = [
                _mock_margin_rows("2026-10-30", ["SSE", "SZSE", "BSE"]),
                _mock_margin_rows("2026-11-02", ["SSE", "BSE"]),  # SZSE 未发布
            ]
        else:
            frames = [
                _mock_margin_rows("2026-10-30", ["SSE", "SZSE", "BSE"]),
                _mock_margin_rows("2026-11-02", ["SSE", "SZSE", "BSE"]),
            ]
        return pd.concat(frames, ignore_index=True)

    monkeypatch.setattr(
        "flow_dashboard.data.loaders._pull_margin_for_load", mock_pull
    )
    as_of = pd.Timestamp("2026-11-03 08:00", tz="Asia/Shanghai")
    # start 落在缓存覆盖内，确保第二次调用真正走到"日期范围满足"的短路分支
    kwargs = dict(
        start=pd.Timestamp("2026-10-30"),
        end=pd.Timestamp("2026-11-02"),
        as_of=as_of, cache_dir=tmp_path,
    )
    load_margin(**kwargs)  # 第一次：部分数据写盘
    out = load_margin(**kwargs)  # 第二次：应检测缺所并重拉修复
    assert calls["n"] == 2
    day = out[out["trade_date"] == pd.Timestamp("2026-11-02")]
    assert set(day["exchange_id"]) == {"SSE", "SZSE", "BSE"}


def test_load_margin_complete_cache_short_circuits(monkeypatch, tmp_path):
    """缓存三所齐全时仍走短路，不重复拉取。"""
    calls = {"n": 0}

    def mock_pull(start, end):
        calls["n"] += 1
        return pd.concat([
            _mock_margin_rows("2026-10-30", ["SSE", "SZSE", "BSE"]),
            _mock_margin_rows("2026-11-02", ["SSE", "SZSE", "BSE"]),
        ], ignore_index=True)

    monkeypatch.setattr(
        "flow_dashboard.data.loaders._pull_margin_for_load", mock_pull
    )
    as_of = pd.Timestamp("2026-11-03 08:00", tz="Asia/Shanghai")
    kwargs = dict(
        start=pd.Timestamp("2026-10-30"),
        end=pd.Timestamp("2026-11-02"),
        as_of=as_of, cache_dir=tmp_path,
    )
    load_margin(**kwargs)
    load_margin(**kwargs)
    assert calls["n"] == 1


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
