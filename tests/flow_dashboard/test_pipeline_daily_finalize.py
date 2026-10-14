"""run_daily_finalize 测试。"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from flow_dashboard.pipeline import run_daily_finalize, run_eod_preview


def test_daily_finalize_increments_version(tmp_path, monkeypatch):
    """同日已有 v01 → finalize 生成 v02。"""
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
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_margin_detail_for_pipeline",
        lambda start, end, as_of: pd.DataFrame(),
    )

    output_dir = tmp_path / "x"
    as_of_eod = pd.Timestamp("2026-08-12 19:30", tz="Asia/Shanghai")
    as_of_final = pd.Timestamp("2026-08-13 09:30", tz="Asia/Shanghai")

    run_eod_preview(data_date="2026-08-12", as_of=as_of_eod,
                    output_dir=output_dir, lock_path=output_dir / "runners.lock")
    path2 = run_daily_finalize(data_date="2026-08-12", as_of=as_of_final,
                               output_dir=output_dir, lock_path=output_dir / "runners.lock")
    assert path2.name == "report_2026-08-12_v02.html"
    # 旧版仍在
    assert (output_dir / "report_2026-08-12_v01.html").exists()


def test_daily_finalize_marks_partial_when_only_one_etf_share_arrives(monkeypatch, tmp_path):
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
    for m in ("_load_margin_for_pipeline", "_load_margin_detail_for_pipeline",
              "_load_fut_daily_for_pipeline",
              "_load_index_daily_for_pipeline", "_load_fund_nav_for_pipeline"):
        monkeypatch.setattr(
            f"flow_dashboard.pipeline.{m}",
            lambda *a, **kw: pd.DataFrame(),
        )
    output_dir = tmp_path / "x"
    path = run_daily_finalize(
        data_date="2026-08-12",
        as_of=pd.Timestamp("2026-08-13 09:30", tz="Asia/Shanghai"),
        output_dir=output_dir, lock_path=output_dir / "runners.lock",
    )
    html = path.read_text()
    assert "(partial)" in html
