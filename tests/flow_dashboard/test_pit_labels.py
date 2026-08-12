"""PIT 标签表契约测试。"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from flow_dashboard.data.pit_labels import (
    load_pit_labels,
    filter_effective,
    PIT_LABEL_COLUMNS,
)


def test_columns_contract():
    expected = {
        "ts_code", "dimension", "label",
        "effective_from", "effective_to",
        "evidence_source", "confirmed_at",
    }
    assert set(PIT_LABEL_COLUMNS) == expected


def test_load_seed_seed_has_known_broad_etfs(tmp_path):
    seed_path = tmp_path / "etf_pit_labels.csv"
    seed_path.write_text(
        "ts_code,dimension,label,effective_from,effective_to,evidence_source,confirmed_at\n"
        "510050.SH,ownership,huijin,2015-07-01,,中央汇金公告,2026-08-12T00:00:00+08:00\n"
        "510300.SH,ownership,huijin,2015-07-01,,中央汇金公告,2026-08-12T00:00:00+08:00\n"
        "510050.SH,asset_scope,broad,2015-02-16,,基金合同,2026-08-12T00:00:00+08:00\n"
    )
    df = load_pit_labels(seed_path)
    assert len(df) == 3
    assert pd.api.types.is_datetime64_any_dtype(df["effective_from"])
    assert pd.api.types.is_datetime64tz_dtype(df["confirmed_at"])


def test_filter_effective_returns_only_active_at_t(tmp_path):
    seed_path = tmp_path / "etf_pit_labels.csv"
    seed_path.write_text(
        "ts_code,dimension,label,effective_from,effective_to,evidence_source,confirmed_at\n"
        "510050.SH,ownership,huijin,2015-07-01,,src,2026-08-12T00:00:00+08:00\n"
        "159915.SZ,asset_scope,growth,2011-09-20,2020-01-01,src,2026-08-12T00:00:00+08:00\n"
    )
    df = load_pit_labels(seed_path)
    active = filter_effective(
        df, ts_code="159915.SZ", dimension="asset_scope",
        at=pd.Timestamp("2019-06-01", tz="Asia/Shanghai"),
    )
    assert len(active) == 1
    assert active.iloc[0]["label"] == "growth"

    inactive = filter_effective(
        df, ts_code="159915.SZ", dimension="asset_scope",
        at=pd.Timestamp("2021-01-01", tz="Asia/Shanghai"),
    )
    assert len(inactive) == 0
