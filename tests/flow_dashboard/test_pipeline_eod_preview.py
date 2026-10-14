"""run_eod_preview 测试。"""
from __future__ import annotations

import pandas as pd

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
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_margin_detail_for_pipeline",
        lambda start, end, as_of: pd.DataFrame(),
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
        "flow_dashboard.pipeline._load_margin_detail_for_pipeline",
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
        "flow_dashboard.pipeline._load_margin_detail_for_pipeline",
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


def test_run_eod_preview_includes_industry_heatmap_panel(tmp_path, monkeypatch):
    """eod_preview 生成的 HTML 应含 panel-margin-industry-heatmap。"""
    # 复用既有的 mock 模式（positional lambda 参数）
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_etf_share_for_pipeline",
        lambda codes, start, end, as_of: pd.DataFrame([
            {"ts_code": "510050.SH", "trade_date": pd.Timestamp("2026-08-11"),
             "share_in_shares": 100e8, "unit_nav": 3.0, "total_size_cny": 300e8,
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
    # 新增 Phase C mock：margin_detail loader + sw_l1 members + pivot
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_margin_detail_for_pipeline",
        lambda start, end, as_of: pd.DataFrame([
            {"trade_date": pd.Timestamp("2026-08-11"), "ts_code": "000001.SZ",
             "rzye": 1e9, "rqye": 1e8},
        ]),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_sw_l1_members",
        lambda: pd.DataFrame([
            {"index_code": "801770.SI", "con_code": "000001.SZ",
             "in_date": "20100101", "out_date": "", "is_new": "Y",
             "industry_code": "801770", "industry_name": "银行"},
        ]),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._pivot_sw_l1_to_daily",
        lambda members, start, end: pd.DataFrame([
            {"trade_date": "2026-08-11", "con_code": "000001.SZ",
             "industry_code": "801770", "industry_name": "银行"},
        ]),
    )

    output_dir = tmp_path / "x"
    path = run_eod_preview(
        data_date="2026-08-12",
        as_of=pd.Timestamp("2026-08-12 19:30", tz="Asia/Shanghai"),
        output_dir=output_dir,
        lock_path=output_dir / "runners.lock",
    )
    html = path.read_text()
    assert 'id="panel-margin-industry-heatmap"' in html


def test_report_excludes_nontrading_share_rows_without_nav_from_daily_charts(tmp_path, monkeypatch):
    """休市日份额记录没有净值，不能在日度图上留下空日期。"""
    days = [pd.Timestamp(d) for d in (
        "2026-09-30", "2026-10-01", "2026-10-08", "2026-10-09", "2026-10-10"
    )]
    shares = pd.DataFrame({
        "ts_code": ["159915.SZ"] * len(days),
        "trade_date": days,
        "share_in_shares": [100e8, 100e8, 105e8, 110e8, 110e8],
        "total_size_cny": [300e8] * len(days),
        "quality_flags": [""] * len(days),
    })
    nav = pd.DataFrame({
        "ts_code": ["159915.SZ"] * 3,
        "nav_date": [days[0], days[2], days[3]],
        "unit_nav": [3.0, 3.0, 3.0],
    })
    monkeypatch.setattr("flow_dashboard.pipeline._load_etf_share_for_pipeline",
                        lambda codes, start, end, as_of: shares)
    monkeypatch.setattr("flow_dashboard.pipeline._load_fund_nav_for_pipeline",
                        lambda codes, start, end, as_of: nav)
    monkeypatch.setattr("flow_dashboard.pipeline._load_margin_for_pipeline",
                        lambda start, end, as_of: pd.DataFrame())
    monkeypatch.setattr("flow_dashboard.pipeline._load_margin_detail_for_pipeline",
                        lambda start, end, as_of: pd.DataFrame())
    monkeypatch.setattr("flow_dashboard.pipeline._load_fut_daily_for_pipeline",
                        lambda ts_code, start, end, as_of: pd.DataFrame())
    monkeypatch.setattr("flow_dashboard.pipeline._load_index_daily_for_pipeline",
                        lambda ts_code, start, end, as_of: pd.DataFrame())
    seen = {}

    def capture_total_market(df, **kwargs):
        seen["dates"] = set(df["trade_date"])
        return '<div id="panel-total-market-daily"></div>'

    monkeypatch.setattr("flow_dashboard.render.panels_daily.render_total_market_daily",
                        capture_total_market)
    output_dir = tmp_path / "reports"
    run_eod_preview(
        data_date="2026-10-10",
        as_of=pd.Timestamp("2026-10-11 09:00", tz="Asia/Shanghai"),
        output_dir=output_dir,
        lock_path=output_dir / "runners.lock",
        universe=["159915.SZ"],
    )
    assert pd.Timestamp("2026-10-09") in seen["dates"]
    assert pd.Timestamp("2026-10-01") not in seen["dates"]
    assert pd.Timestamp("2026-10-10") not in seen["dates"]
