"""s4_basis 契约测试。"""
from __future__ import annotations

import pandas as pd
import pytest

from flow_dashboard.indicators.basis import compute_basis


def _sample():
    """IC2608.CFX 现货 5500，期货 settle 5400，delist 2026-08-21。"""
    return pd.DataFrame([
        {"ts_code": "IC2608.CFX", "trade_date": pd.Timestamp("2026-08-07"),
         "settle": 5400.0, "close": 5395.0, "pre_settle": 5380.0,
         "delist_date": pd.Timestamp("2026-08-21")},
        {"ts_code": "IC2608.CFX", "trade_date": pd.Timestamp("2026-08-08"),
         "settle": 5450.0, "close": 5445.0, "pre_settle": 5400.0,
         "delist_date": pd.Timestamp("2026-08-21")},
    ])


def _spot():
    return pd.DataFrame([
        {"ts_code": "000905.SH", "trade_date": pd.Timestamp("2026-08-07"), "close": 5500.0},
        {"ts_code": "000905.SH", "trade_date": pd.Timestamp("2026-08-08"), "close": 5550.0},
    ])


def test_compute_basis_per_contract():
    out = compute_basis(_sample(), _spot(), spot_map={"IC": "000905.SH"})
    assert len(out) == 2
    # 2026-08-07: (5500 - 5400) / 5500 = 0.01818
    d1 = out[out["trade_date"] == pd.Timestamp("2026-08-07")].iloc[0]
    assert d1["discount_rate"] == pytest.approx(100 / 5500, rel=1e-4)
    assert d1["basis_points"] == pytest.approx(100 / 5500 * 10000, rel=1e-4)
    # 年化：days_to_delist = 14 天
    assert d1["days_to_delist"] == 14
    assert d1["annualized_discount_rate"] == pytest.approx(
        (100 / 5500) * (365 / 14), rel=1e-3
    )


def test_compute_basis_per_contract_does_not_roll():
    """spec §3.5.2 红线：不拼接当季连续；多合约分段。"""
    fut = pd.DataFrame([
        {"ts_code": "IC2608.CFX", "trade_date": pd.Timestamp("2026-08-07"),
         "settle": 5400.0, "close": 5395.0, "pre_settle": 5380.0,
         "delist_date": pd.Timestamp("2026-08-21")},
        {"ts_code": "IC2609.CFX", "trade_date": pd.Timestamp("2026-08-07"),
         "settle": 5350.0, "close": 5345.0, "pre_settle": 5330.0,
         "delist_date": pd.Timestamp("2026-09-18")},
    ])
    spot = _spot()
    out = compute_basis(fut, spot, spot_map={"IC": "000905.SH"})
    assert set(out["ts_code"].unique()) == {"IC2608.CFX", "IC2609.CFX"}
    # 不存在 "continuous" 合成行
    assert "IC_CONT" not in set(out["ts_code"].unique())


def test_compute_basis_intraday_layer_separate():
    """盘中新浪预览与日终 Tushare 分层；本函数不混算（spec §4.2）。

    此测试验证 compute_basis 接受 layer 参数；不同 layer 不混合。
    """
    eod = _sample()
    eod["layer"] = "eod"
    out = compute_basis(
        eod, _spot(), spot_map={"IC": "000905.SH"}, layer_col="layer"
    )
    assert (out["layer"] == "eod").all()


def test_compute_basis_quote_time_unverified_flag_when_no_skew_check():
    """max_quote_skew_seconds=None 时，标记 quote_time_unverified。"""
    out = compute_basis(
        _sample(), _spot(), spot_map={"IC": "000905.SH"},
        max_quote_skew_seconds=None,
    )
    assert (out["quality_flags"].str.contains("quote_time_unverified", na=False)).all()


def test_compute_basis_missing_spot_close():
    """spot 缺当日 close 时，对应日期 basis 行标 missing_spot 并置 NaN。"""
    fut = _sample()
    spot = pd.DataFrame([
        {"ts_code": "000905.SH", "trade_date": pd.Timestamp("2026-08-07"), "close": 5500.0},
        # 缺 8-8
    ])
    out = compute_basis(fut, spot, spot_map={"IC": "000905.SH"})
    d2 = out[out["trade_date"] == pd.Timestamp("2026-08-08")].iloc[0]
    assert pd.isna(d2["discount_rate"])
    assert "missing_spot" in d2["quality_flags"]
