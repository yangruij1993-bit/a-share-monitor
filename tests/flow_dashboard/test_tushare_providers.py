"""tushare_providers 契约测试。

每个 provider 必须满足：
- 返回 pandas.DataFrame
- 含契约列（normalized 名称）
- 关键数值列已转 numeric
- 不含 Oracle/sys.path 主项目依赖

注：import 用 flow_dashboard.* （src-layout），不是 src.flow_dashboard.*。
"""
from __future__ import annotations

import pandas as pd
import pytest

from flow_dashboard.data.tushare_providers import (
    pull_fund_basic,
    pull_etf_share_size,
    pull_fund_nav,
    pull_fund_daily,
    pull_margin,
    pull_fut_basic,
    pull_fut_daily,
    pull_index_daily,
)


# === Task 4: fund_basic ===

@pytest.mark.live
def test_pull_fund_basic_contract(tushare_token):
    df = pull_fund_basic(market="E")
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 0
    for col in ("ts_code", "name", "fund_type", "found_date", "list_date", "delist_date", "market"):
        assert col in df.columns, f"missing column: {col}"
    assert pd.api.types.is_datetime64_any_dtype(df["found_date"])
    assert (df["market"] == "E").all()


# === Task 5: etf_share_size ===

@pytest.mark.live
def test_pull_etf_share_size_contract(tushare_token):
    df = pull_etf_share_size(
        codes=["510050.SH", "510300.SH"],
        start_date="20260807",
        end_date="20260812",
    )
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 0
    for col in ("trade_date", "ts_code", "etf_name", "total_share", "total_size", "exchange"):
        assert col in df.columns, f"missing column: {col}"
    assert (df["total_share"] > 0).all()
    assert (df["total_size"] > 0).all()
    assert pd.api.types.is_datetime64_any_dtype(df["trade_date"])
    assert set(df["exchange"].unique()).issubset({"SSE", "SZSE", "BSE"})


@pytest.mark.live
def test_pull_etf_share_size_has_share_in_shares_unit(tushare_token):
    """spec §1.3: 份额统一转成"份"再计算。万份→份乘 10000。"""
    df = pull_etf_share_size(
        codes=["510050.SH"], start_date="20260811", end_date="20260811"
    )
    # 当天可能没数据；如果有，校验单位换算
    if len(df) >= 1:
        assert "share_in_shares" in df.columns
        row = df.iloc[0]
        assert abs(row["share_in_shares"] - row["total_share"] * 10000) <= 1.0


# === Task 6: fund_nav, fund_daily, margin ===

@pytest.mark.live
def test_pull_fund_nav_contract(tushare_token):
    df = pull_fund_nav(
        codes=["510050.SH"], start_date="20260807", end_date="20260812"
    )
    assert len(df) > 0
    for col in ("ts_code", "nav_date", "ann_date", "unit_nav", "accum_nav", "adj_nav"):
        assert col in df.columns
    assert pd.api.types.is_datetime64_any_dtype(df["nav_date"])
    assert pd.api.types.is_datetime64_any_dtype(df["ann_date"])


@pytest.mark.live
def test_pull_fund_daily_contract(tushare_token):
    df = pull_fund_daily(
        codes=["510050.SH"], start_date="20260807", end_date="20260812"
    )
    assert len(df) > 0
    for col in ("ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"):
        assert col in df.columns
    assert pd.api.types.is_numeric_dtype(df["close"])


@pytest.mark.live
def test_pull_margin_contract(tushare_token):
    df = pull_margin(start_date="20260811", end_date="20260811")
    # 当天可能没数据，回退到上一个交易日
    if len(df) == 0:
        df = pull_margin(start_date="20260804", end_date="20260811")
    assert len(df) >= 1
    for col in ("trade_date", "exchange_id", "rzye", "rzmre", "rzche"):
        assert col in df.columns
    # 单位：元（SSE/SZSE rzye 余额 > 1e10；BSE 较小不参与此断言）
    big = df[df["exchange_id"].isin(["SSE", "SZSE"])]
    assert (big["rzye"] > 1e10).all()
    # BSE 仍应是正数
    bse = df[df["exchange_id"] == "BSE"]
    assert (bse["rzye"] > 0).all()


# === Task 7: fut_basic, fut_daily, index_daily ===

@pytest.mark.live
def test_pull_fut_basic_contract(tushare_token):
    df = pull_fut_basic(exchange="CFFEX", fut_code="IC")
    assert len(df) > 0
    for col in ("ts_code", "symbol", "exchange", "name", "fut_code",
                "multiplier", "list_date", "delist_date"):
        assert col in df.columns
    assert pd.api.types.is_datetime64_any_dtype(df["list_date"])
    assert pd.api.types.is_datetime64_any_dtype(df["delist_date"])


@pytest.mark.live
def test_pull_fut_daily_contract(tushare_token):
    # IC2608.CFX 在 2026-08 仍然活跃（delist 20260821）
    df = pull_fut_daily(
        ts_code="IC2608.CFX", start_date="20260807", end_date="20260812"
    )
    assert len(df) > 0
    for col in ("ts_code", "trade_date", "close", "settle", "pre_settle", "oi"):
        assert col in df.columns
    assert pd.api.types.is_numeric_dtype(df["close"])
    assert pd.api.types.is_numeric_dtype(df["settle"])


@pytest.mark.live
def test_pull_index_daily_contract(tushare_token):
    df = pull_index_daily(
        ts_code="000905.SH", start_date="20260807", end_date="20260812"
    )
    assert len(df) > 0
    for col in ("ts_code", "trade_date", "close", "open", "high", "low"):
        assert col in df.columns
    assert pd.api.types.is_datetime64_any_dtype(df["trade_date"])


# === Task 16: Suffix-invariant regression (Red Line 1 守护) ===

def test_normalize_etf_share_size_suffix_invariant():
    """per spec §3.5 后缀不变测试：追加未来日数据不应改写历史行。"""
    from flow_dashboard.data.tushare_providers import _normalize_etf_share_size

    base = pd.DataFrame([
        {"trade_date": "20260807", "ts_code": "510050.SH", "etf_name": "X",
         "total_share": 100.0, "total_size": 100.0, "exchange": "SSE"},
        {"trade_date": "20260808", "ts_code": "510050.SH", "etf_name": "X",
         "total_share": 110.0, "total_size": 110.0, "exchange": "SSE"},
    ])
    suffix = pd.DataFrame([
        {"trade_date": "20260809", "ts_code": "510050.SH", "etf_name": "X",
         "total_share": 150.0, "total_size": 150.0, "exchange": "SSE"},
    ])
    out_base = _normalize_etf_share_size(base).set_index("trade_date")
    out_suffix = _normalize_etf_share_size(
        pd.concat([base, suffix], ignore_index=True)
    ).set_index("trade_date")

    common = out_base.index.intersection(out_suffix.index)
    pd.testing.assert_frame_equal(
        out_base.loc[common], out_suffix.loc[common],
        check_like=True,
    )


# === Task 2: margin_detail（个股两融明细，分页拉全沪深北） ===

def test_pull_margin_detail_paginates_until_short_page(monkeypatch):
    """单次请求被截断（约 2000 行沪市），必须 limit/offset 分页拉全沪深北。

    实测 2026-10-09 全量 4455 行（SH 2001 / SZ 2108 / BJ 346）；
    不分页时深市（含创业板 300/301）整体缺失。
    """
    from flow_dashboard.data import tushare_providers

    page_rows = 1000
    total = 2445  # 3 页：1000 + 1000 + 445

    class _FakePro:
        def __init__(self):
            self.calls: list[dict] = []

        def margin_detail(self, trade_date, limit=None, offset=None):
            self.calls.append({"trade_date": trade_date, "limit": limit, "offset": offset})
            start = offset or 0
            n = min(page_rows, max(total - start, 0))
            return pd.DataFrame({
                "trade_date": ["20261009"] * n,
                "ts_code": [f"{300000 + start + i}.SZ" for i in range(n)],
                "rzye": [1e8] * n,
                "rqye": [0.0] * n,
                "rzmre": [1e7] * n,
                "rqyl": [0.0] * n,
            })

    fake = _FakePro()
    monkeypatch.setattr(tushare_providers, "get_pro_api", lambda: fake)

    df = tushare_providers.pull_margin_detail("20261009")
    assert len(df) == total
    assert len(fake.calls) == 3
    assert fake.calls[0]["offset"] == 0
    assert fake.calls[1]["offset"] == 1000
    assert fake.calls[2]["offset"] == 2000
    assert pd.api.types.is_datetime64_any_dtype(df["trade_date"])


def test_pull_margin_detail_single_page(monkeypatch):
    """不足一页时只调一次，正常返回。"""
    from flow_dashboard.data import tushare_providers

    class _FakePro:
        def margin_detail(self, trade_date, limit=None, offset=None):
            return pd.DataFrame({
                "trade_date": ["20261009"] * 5,
                "ts_code": [f"60000{i}.SH" for i in range(5)],
                "rzye": [1e8] * 5, "rqye": [0.0] * 5,
                "rzmre": [1e7] * 5, "rqyl": [0.0] * 5,
            })

    monkeypatch.setattr(
        tushare_providers, "get_pro_api", lambda: _FakePro()
    )
    df = tushare_providers.pull_margin_detail("20261009")
    assert len(df) == 5


def test_pull_margin_detail_empty(monkeypatch):
    """无数据日（周末/节假日）返回空 df，不抛错。"""
    from flow_dashboard.data import tushare_providers

    class _FakePro:
        def margin_detail(self, trade_date, limit=None, offset=None):
            return pd.DataFrame()

    monkeypatch.setattr(
        tushare_providers, "get_pro_api", lambda: _FakePro()
    )
    df = tushare_providers.pull_margin_detail("20261010")
    assert df.empty
