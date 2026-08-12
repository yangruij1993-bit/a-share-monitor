"""schema 模块契约测试。"""
from __future__ import annotations

import pandas as pd
import pytest

from flow_dashboard.data.schema import (
    AUDIT_COLUMNS,
    QUALITY_FLAGS,
    validate_audit_columns,
)


def test_audit_columns_complete():
    expected = {
        "source_date", "first_observed_at", "available_at",
        "fetched_at", "source", "source_version", "is_stale", "quality_flags",
    }
    assert set(AUDIT_COLUMNS) == expected


def test_quality_flags_includes_known_markers():
    must_have = {
        "source_switch_break",
        "quote_time_unverified",
        "reconstructed_history",
        "restated",
        "stale",
        "partial",
    }
    assert must_have.issubset(set(QUALITY_FLAGS))


def test_validate_audit_columns_adds_missing():
    df = pd.DataFrame({"ts_code": ["510050.SH"]})
    report = validate_audit_columns(df)
    assert not report.ok
    assert set(report.missing) == set(AUDIT_COLUMNS)


def test_validate_audit_columns_passes_when_all_present():
    df = pd.DataFrame([{c: None for c in AUDIT_COLUMNS}])
    report = validate_audit_columns(df)
    assert report.ok
    assert not report.missing
