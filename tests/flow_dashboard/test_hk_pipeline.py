"""pipeline 集成港股 tab：tabs 结构、双日期 manifest、report_date 归档名。"""

import json

import pandas as pd

from flow_dashboard.pipeline import _run_eod_preview_inner, run_eod_preview


def _mock_ashare_empty(monkeypatch):
    """A股 loaders 全部空表（复用 test_pipeline_eod_preview.py 的 mock 模式）。"""
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_etf_share_for_pipeline",
        lambda codes, start, end, as_of: pd.DataFrame(),
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


def test_eod_preview_renders_both_tabs_and_dual_dates(tmp_path, monkeypatch):
    _mock_ashare_empty(monkeypatch)
    monkeypatch.setattr(
        "flow_dashboard.pipeline._render_hk_tab_for_pipeline",
        lambda as_of: ('<div id="hk-x">港股内容</div>', "2026-09-18"),
    )
    output_dir = tmp_path / "x"
    path = run_eod_preview(
        data_date="2026-08-12",
        as_of=pd.Timestamp("2026-08-12 19:30", tz="Asia/Shanghai"),
        output_dir=output_dir,
        lock_path=output_dir / "runners.lock",
    )
    assert "report_2026-08-12_v01.html" in path.name  # A股触发 → report_date=data_date
    html = path.read_text()
    assert 'class="tab-bar"' in html
    assert 'data-tab="ashare"' in html and 'data-tab="hk-short"' in html
    assert 'id="tab-ashare" class="tab-panel active"' in html  # 服务端默认激活 A股
    assert "港股内容" in html
    assert "市场流动性日报 — 2026-08-12" in html
    manifest = json.loads((output_dir / "manifest" / "2026-08-12_v01.json").read_text())
    assert manifest["panel_status"]["ashare_data_date"] == "2026-08-12"
    assert manifest["panel_status"]["hk_data_date"] == "2026-09-18"
    assert "panel-hk-conclusion" in manifest["panels"]
    assert manifest["source_versions"]["hk_short"] == "hk_short_v1"


def test_report_date_controls_archive_and_title(tmp_path, monkeypatch):
    """港股 runner 触发时 report_date != A股 data_date → 归档名/标题用 report_date。"""
    _mock_ashare_empty(monkeypatch)
    monkeypatch.setattr(
        "flow_dashboard.pipeline._render_hk_tab_for_pipeline",
        lambda as_of: ("<div>hk</div>", None),
    )
    output_dir = tmp_path / "y"
    path = _run_eod_preview_inner(
        "2026-08-12",
        pd.Timestamp("2026-08-13 18:45", tz="Asia/Shanghai"),
        output_dir,
        None,
        report_date="2026-08-13",
    )
    assert "report_2026-08-13_v01.html" in path.name
    html = path.read_text()
    assert "市场流动性日报 — 2026-08-13" in html
    manifest = json.loads((output_dir / "manifest" / "2026-08-13_v01.json").read_text())
    assert manifest["panel_status"]["ashare_data_date"] == "2026-08-12"
    assert manifest["panel_status"]["hk_data_date"] is None


def test_hk_tab_helper_delegates_to_panels(tmp_path, monkeypatch):
    """_render_hk_tab_for_pipeline 只读缓存委托 render_hk_short_body。"""
    from flow_dashboard.pipeline import _render_hk_tab_for_pipeline

    monkeypatch.setattr(
        "flow_dashboard.render.panels_hk_short.render_hk_short_body",
        lambda *, as_of, cache_dir=None: ("<b>HK</b>", "2026-09-18"),
    )
    html, d = _render_hk_tab_for_pipeline(
        pd.Timestamp("2026-09-18 19:00", tz="Asia/Shanghai")
    )
    assert html == "<b>HK</b>" and d == "2026-09-18"
