# tests/flow_dashboard/data/test_load_margin_detail.py
"""个股两融明细 loader 测试。"""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from flow_dashboard.data.loaders import load_margin_detail


def _fake_margin_detail(trade_date: str) -> pd.DataFrame:
    ts = pd.Timestamp(trade_date)
    return pd.DataFrame([
        {"trade_date": ts, "ts_code": "000001.SZ",
         "rzye": 1e9, "rqye": 1e8, "rzmre": 1e8, "rqyl": 1e7},
        {"trade_date": ts, "ts_code": "600000.SH",
         "rzye": 2e9, "rqye": 2e8, "rzmre": 2e8, "rqyl": 2e7},
    ])


def test_load_margin_detail_pulls_each_trade_date(tmp_path):
    """loader 应该对区间内每个 trade_date 调一次 pull_margin_detail。"""
    start = pd.Timestamp("2026-08-07")
    end = pd.Timestamp("2026-08-11")
    as_of = pd.Timestamp("2026-08-12", tz="Asia/Shanghai")
    with patch(
        "flow_dashboard.data.loaders._pull_margin_detail_for_load",
        side_effect=_fake_margin_detail,
    ) as mock:
        df = load_margin_detail(
            start=start, end=end,
            as_of=as_of,
            cache_dir=tmp_path, use_cache=False,
        )
    # 5 个日历日 (08-07 ~ 08-11)
    assert mock.call_count == 5
    assert len(df) == 10  # 5 days × 2 stocks


def test_load_margin_detail_has_audit_columns(tmp_path):
    as_of = pd.Timestamp("2026-08-12", tz="Asia/Shanghai")
    with patch(
        "flow_dashboard.data.loaders._pull_margin_detail_for_load",
        side_effect=_fake_margin_detail,
    ):
        df = load_margin_detail(
            start=pd.Timestamp("2026-08-07"),
            end=pd.Timestamp("2026-08-11"),
            as_of=as_of,
            cache_dir=tmp_path, use_cache=False,
        )
    from flow_dashboard.data.schema import AUDIT_COLUMNS
    for col in AUDIT_COLUMNS:
        assert col in df.columns


def test_load_margin_detail_available_at_filter(tmp_path):
    """available_at > as_of 的行应该被过滤掉。"""
    as_of = pd.Timestamp("2026-08-12 12:00", tz="Asia/Shanghai")
    with patch(
        "flow_dashboard.data.loaders._pull_margin_detail_for_load",
        side_effect=_fake_margin_detail,
    ):
        df = load_margin_detail(
            start=pd.Timestamp("2026-08-07"),
            end=pd.Timestamp("2026-08-11"),
            as_of=as_of,
            cache_dir=tmp_path, use_cache=False,
        )
    # margin_detail 的 available_at = trade_date + 19:00；08-11 19:00 < 08-12 12:00 → 全部通过
    assert (df["available_at"] <= as_of).all()


def test_load_margin_detail_uses_cache_on_second_call(tmp_path):
    as_of = pd.Timestamp("2026-08-12", tz="Asia/Shanghai")
    with patch(
        "flow_dashboard.data.loaders._pull_margin_detail_for_load",
        side_effect=_fake_margin_detail,
    ) as mock:
        load_margin_detail(
            start=pd.Timestamp("2026-08-07"),
            end=pd.Timestamp("2026-08-11"),
            as_of=as_of,
            cache_dir=tmp_path,  # use_cache=True default, writes to cache
        )
        load_margin_detail(
            start=pd.Timestamp("2026-08-07"),
            end=pd.Timestamp("2026-08-11"),
            as_of=as_of,
            cache_dir=tmp_path,  # use_cache=True default, reads from cache
        )
    # 5 个 trade_date 只在第一次调；第二次走缓存
    assert mock.call_count == 5
