"""run_eod_preview 测试。"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from flow_dashboard.pipeline import run_eod_preview


def test_run_eod_preview_writes_archive_with_v01(tmp_path, monkeypatch):
    """生成 report_<data_date>_v01.html + latest symlink。"""
    # mock loaders + indicators
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_etf_share_for_pipeline",
        lambda codes, start, end, as_of: pd.DataFrame([
            {"ts_code": "510050.SH", "trade_date": pd.Timestamp("2026-08-12"),
             "share_in_shares": 100e8, "unit_nav": 3.0, "total_size_cny": 100e8 * 3,
             "etf_estimated_flow_cny": 1e9, "quality_flags": "",
             "label": "huijin", "dimension": "ownership",
             "available_at": as_of, "source_date": pd.Timestamp("2026-08-12"),
             "first_observed_at": as_of, "fetched_at": as_of,
             "source": "tushare", "source_version": "v1", "is_stale": False},
        ]),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_margin_for_pipeline",
        lambda start, end, as_of: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_fut_daily_for_pipeline",
        lambda ts_code, start, end, as_of: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_index_daily_for_pipeline",
        lambda ts_code, start, end, as_of: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_fund_nav_for_pipeline",
        lambda codes, start, end, as_of: pd.DataFrame(),
    )

    output_dir = tmp_path / "ashare_flow_daily"
    path = run_eod_preview(
        data_date="2026-08-12",
        as_of=pd.Timestamp("2026-08-12 19:30", tz="Asia/Shanghai"),
        output_dir=output_dir,
        lock_path=output_dir / "runners.lock",
    )
    assert path.exists()
    assert "report_2026-08-12_v01.html" in path.name
    latest = output_dir / "latest.html"
    assert latest.is_symlink()
    assert latest.resolve() == path.resolve()


def test_run_eod_preview_marks_partial_when_share_missing(tmp_path, monkeypatch):
    """spec §3.1: ETF 份额未入库时标 partial，不将 T-1 标 T。"""
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_etf_share_for_pipeline",
        lambda codes, start, end, as_of: pd.DataFrame(),  # 空：未入库
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_margin_for_pipeline",
        lambda start, end, as_of: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_fut_daily_for_pipeline",
        lambda ts_code, start, end, as_of: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_index_daily_for_pipeline",
        lambda ts_code, start, end, as_of: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_fund_nav_for_pipeline",
        lambda codes, start, end, as_of: pd.DataFrame(),
    )
    output_dir = tmp_path / "x"
    path = run_eod_preview(
        data_date="2026-08-12",
        as_of=pd.Timestamp("2026-08-12 19:30", tz="Asia/Shanghai"),
        output_dir=output_dir,
        lock_path=output_dir / "runners.lock",
    )
    html = path.read_text()
    assert "partial" in html.lower()


def test_run_eod_preview_marks_partial_when_share_dated_before_end(tmp_path, monkeypatch):
    """spec §3.1: ETF 份额有数据但最新日期 < data_date → 仍标 partial。"""
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_etf_share_for_pipeline",
        lambda codes, start, end, as_of: pd.DataFrame([
            {"ts_code": "510050.SH", "trade_date": pd.Timestamp("2026-08-11"),  # T-1
             "share_in_shares": 100e8, "unit_nav": 3.0, "total_size_cny": 100e8 * 3,
             "etf_estimated_flow_cny": 1e9, "quality_flags": "",
             "label": "huijin", "dimension": "ownership",
             "available_at": as_of, "source_date": pd.Timestamp("2026-08-11"),
             "first_observed_at": as_of, "fetched_at": as_of,
             "source": "tushare", "source_version": "v1", "is_stale": False},
        ]),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_margin_for_pipeline",
        lambda start, end, as_of: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_fut_daily_for_pipeline",
        lambda ts_code, start, end, as_of: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_index_daily_for_pipeline",
        lambda ts_code, start, end, as_of: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_fund_nav_for_pipeline",
        lambda codes, start, end, as_of: pd.DataFrame(),
    )
    output_dir = tmp_path / "x"
    path = run_eod_preview(
        data_date="2026-08-12",
        as_of=pd.Timestamp("2026-08-12 19:30", tz="Asia/Shanghai"),
        output_dir=output_dir,
        lock_path=output_dir / "runners.lock",
    )
    html = path.read_text()
    assert "partial" in html.lower()
