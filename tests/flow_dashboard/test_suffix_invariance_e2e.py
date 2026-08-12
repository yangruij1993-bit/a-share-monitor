"""Red Line 1 端到端守护：追加未来行后，已归档的 v01 报告字节不变。

spec §3.5 共通验收 + Red Line 1：
"向输入末尾追加任意未来数据，已归档日报的历史值必须逐元素不变。"

正确守护方式：v01 归档文件在 v02 发布前后必须字节一致。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import pytest

from flow_dashboard.pipeline import run_eod_preview


_BASE_DATA = [
    {"ts_code": "510050.SH", "trade_date": pd.Timestamp("2026-08-06"),
     "share_in_shares": 100e8, "unit_nav": 3.0, "total_size_cny": 100e8 * 3,
     "etf_estimated_flow_cny": 1e9, "quality_flags": "",
     "label": "huijin", "dimension": "ownership",
     "available_at": pd.Timestamp("2026-08-12 19:30", tz="Asia/Shanghai"),
     "source_date": pd.Timestamp("2026-08-06"),
     "first_observed_at": pd.Timestamp("2026-08-12 19:30", tz="Asia/Shanghai"),
     "fetched_at": pd.Timestamp("2026-08-12 19:30", tz="Asia/Shanghai"),
     "source": "tushare", "source_version": "v1", "is_stale": False},
    {"ts_code": "510050.SH", "trade_date": pd.Timestamp("2026-08-07"),
     "share_in_shares": 110e8, "unit_nav": 3.0, "total_size_cny": 110e8 * 3,
     "etf_estimated_flow_cny": 3e9, "quality_flags": "",
     "label": "huijin", "dimension": "ownership",
     "available_at": pd.Timestamp("2026-08-12 19:30", tz="Asia/Shanghai"),
     "source_date": pd.Timestamp("2026-08-07"),
     "first_observed_at": pd.Timestamp("2026-08-12 19:30", tz="Asia/Shanghai"),
     "fetched_at": pd.Timestamp("2026-08-12 19:30", tz="Asia/Shanghai"),
     "source": "tushare", "source_version": "v1", "is_stale": False},
]


def test_suffix_invariance_e2e(tmp_path, monkeypatch):
    """追加 8-12 行后，v01 归档 HTML 与 manifest 必须字节不变；v02 是新版本。"""

    state = {"data": list(_BASE_DATA)}

    def mock_load(codes, start, end, as_of):
        return pd.DataFrame(state["data"])

    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_etf_share_for_pipeline", mock_load
    )
    for m in ("_load_margin_for_pipeline", "_load_fut_daily_for_pipeline",
              "_load_index_daily_for_pipeline", "_load_fund_nav_for_pipeline"):
        monkeypatch.setattr(
            f"flow_dashboard.pipeline.{m}",
            lambda *a, **kw: pd.DataFrame(),
        )

    output_dir = tmp_path / "ashare_flow_daily"

    # v01
    v01_path = run_eod_preview(
        data_date="2026-08-07",
        as_of=pd.Timestamp("2026-08-07 19:30", tz="Asia/Shanghai"),
        output_dir=output_dir, lock_path=output_dir / "runners.lock",
    )
    v01_html_hash = hashlib.sha256(v01_path.read_bytes()).hexdigest()
    v01_manifest_path = output_dir / "manifest" / "2026-08-07_v01.json"
    v01_manifest_hash = hashlib.sha256(v01_manifest_path.read_bytes()).hexdigest()

    # 追加 8-12 行（未来数据）
    state["data"].extend([
        {"ts_code": "510050.SH", "trade_date": pd.Timestamp("2026-08-12"),
         "share_in_shares": 120e8, "unit_nav": 3.1, "total_size_cny": 120e8 * 3.1,
         "etf_estimated_flow_cny": 2e9, "quality_flags": "",
         "label": "huijin", "dimension": "ownership",
         "available_at": pd.Timestamp("2026-08-13 09:30", tz="Asia/Shanghai"),
         "source_date": pd.Timestamp("2026-08-12"),
         "first_observed_at": pd.Timestamp("2026-08-13 09:30", tz="Asia/Shanghai"),
         "fetched_at": pd.Timestamp("2026-08-13 09:30", tz="Asia/Shanghai"),
         "source": "tushare", "source_version": "v1", "is_stale": False},
    ])

    # 再发一版（同 data_date → v02）
    v02_path = run_eod_preview(
        data_date="2026-08-07",
        as_of=pd.Timestamp("2026-08-13 09:30", tz="Asia/Shanghai"),
        output_dir=output_dir, lock_path=output_dir / "runners.lock",
    )

    # Red Line 1: v01 归档字节不变
    assert v01_path.exists(), "v01 归档被删除"
    assert hashlib.sha256(v01_path.read_bytes()).hexdigest() == v01_html_hash, (
        "Red Line 1 violation: v01 归档 HTML 在 v02 发布后被修改"
    )
    assert hashlib.sha256(v01_manifest_path.read_bytes()).hexdigest() == v01_manifest_hash, (
        "Red Line 1 violation: v01 manifest 在 v02 发布后被修改"
    )

    # v02 是新版本，不是 v01 的覆盖
    assert v02_path.name == "report_2026-08-07_v02.html", f"v02 命名错误: {v02_path.name}"
    assert v02_path != v01_path
