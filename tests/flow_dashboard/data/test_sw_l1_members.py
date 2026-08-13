# tests/flow_dashboard/data/test_sw_l1_members.py
"""申万一级成分股 PIT loader 测试。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from flow_dashboard.data.sw_l1_members import (
    SW_L1_INDUSTRIES,
    load_sw_l1_members,
    pivot_to_daily_membership,
)


def _fake_index_member(index_code: str) -> pd.DataFrame:
    """模拟 pro.index_member 返回。"""
    return pd.DataFrame([
        {"index_code": index_code, "con_code": "000001.SZ",
         "in_date": "20100101", "out_date": "", "is_new": "Y"},
        {"index_code": index_code, "con_code": "600000.SH",
         "in_date": "20100101", "out_date": "20200101", "is_new": "N"},
    ])


def test_sw_l1_industries_has_28_codes():
    assert len(SW_L1_INDUSTRIES) == 28
    codes = [c for c, _ in SW_L1_INDUSTRIES]
    assert "801010" in codes and "801970" in codes


def test_load_sw_l1_members_calls_28_index_codes(tmp_path):
    """loader 应该对 28 个 index_code 各调一次 pull_index_member。"""
    cache_dir = tmp_path / "cache"
    with patch(
        "flow_dashboard.data.sw_l1_members.pull_index_member",
        side_effect=_fake_index_member,
    ) as mock:
        df = load_sw_l1_members(cache_dir=cache_dir, use_cache=False)
    assert mock.call_count == 28
    # 28 行业 × 2 成分股 = 56 行
    assert len(df) == 56


def test_load_sw_l1_members_writes_parquet_cache(tmp_path):
    cache_dir = tmp_path / "cache"
    with patch(
        "flow_dashboard.data.sw_l1_members.pull_index_member",
        side_effect=_fake_index_member,
    ):
        load_sw_l1_members(cache_dir=cache_dir, use_cache=False)
    cache_path = cache_dir / "sw_l1_members.parquet"
    assert cache_path.exists()


def test_load_sw_l1_members_uses_cache_on_second_call(tmp_path):
    cache_dir = tmp_path / "cache"
    with patch(
        "flow_dashboard.data.sw_l1_members.pull_index_member",
        side_effect=_fake_index_member,
    ) as mock:
        load_sw_l1_members(cache_dir=cache_dir, use_cache=False)
        # 第二次：默认 use_cache=True，不应该再调 API
        load_sw_l1_members(cache_dir=cache_dir)
    assert mock.call_count == 28  # 仍是 28，不是 56


def test_load_sw_l1_members_has_audit_columns(tmp_path):
    with patch(
        "flow_dashboard.data.sw_l1_members.pull_index_member",
        side_effect=_fake_index_member,
    ):
        df = load_sw_l1_members(cache_dir=tmp_path, use_cache=False)
    from flow_dashboard.data.schema import AUDIT_COLUMNS
    for col in AUDIT_COLUMNS:
        assert col in df.columns, f"missing audit column: {col}"


def test_pivot_to_daily_membership_pit_correct():
    """PIT 关键测试：2020-01-02 时，已退出成分（out_date=2020-01-01）不应在册。"""
    members = pd.DataFrame([
        {"index_code": "801010.SI", "industry_code": "801010", "industry_name": "农林牧渔",
         "con_code": "000001.SZ", "in_date": "20100101", "out_date": "", "is_new": "Y"},
        {"index_code": "801010.SI", "industry_code": "801010", "industry_name": "农林牧渔",
         "con_code": "600000.SH", "in_date": "20100101", "out_date": "20200101", "is_new": "N"},
    ])
    daily = pivot_to_daily_membership(
        members,
        start=pd.Timestamp("2020-01-02"),
        end=pd.Timestamp("2020-01-03"),
    )
    # 2020-01-02: 000001.SZ 在册，600000.SH 已退出
    rows_0102 = daily[daily["trade_date"] == "2020-01-02"]
    assert (rows_0102["con_code"] == "000001.SZ").any()
    assert (rows_0102["con_code"] == "600000.SH").sum() == 0
