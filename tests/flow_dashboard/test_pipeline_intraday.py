"""Pipeline intraday 入口测试。"""
from __future__ import annotations

import pandas as pd
import pytest

from flow_dashboard.pipeline import run_intraday


def test_run_intraday_writes_intraday_latest_html_only(monkeypatch, tmp_path):
    """spec §3.3: intraday 只写 intraday_latest.html，不写归档。"""
    # mock sina providers
    def mock_futures_snapshot(variety, observed_at, timeout=8.0):
        from flow_dashboard.data.sina_providers import QuoteBatch
        return QuoteBatch(
            provider="sina", observed_at=observed_at,
            received_at=pd.Timestamp.now(tz="Asia/Shanghai"),
            parse_version="sina_v1",
            quotes=[{"provider_code": f"sina_fut_{variety}2608",
                     "quote_time": observed_at, "last_price": 5400.0,
                     "pre_close": 5380.0, "settlement": 5400.0,
                     "status": "ok", "data_mode": "intraday_preview", "raw": {}}],
            failures=[],
        )

    def mock_spot(provider_codes, observed_at, timeout=6.0):
        from flow_dashboard.data.sina_providers import QuoteBatch
        return QuoteBatch(
            provider="sina", observed_at=observed_at,
            received_at=pd.Timestamp.now(tz="Asia/Shanghai"),
            parse_version="sina_v1",
            quotes=[{"provider_code": c, "quote_time": observed_at,
                     "last_price": 5500.0, "pre_close": 5480.0,
                     "status": "ok", "data_mode": "intraday_preview", "raw": {}}
                    for c in provider_codes],
            failures=[],
        )

    monkeypatch.setattr("flow_dashboard.pipeline.fetch_futures_snapshot", mock_futures_snapshot)
    monkeypatch.setattr("flow_dashboard.pipeline.fetch_snapshot", mock_spot)

    output_dir = tmp_path / "ashare_flow_daily"
    output_dir.mkdir()
    intraday_path = run_intraday(
        as_of=pd.Timestamp("2026-08-12 14:30", tz="Asia/Shanghai"),
        output_dir=output_dir,
        lock_path=output_dir / "runners.lock",
    )
    assert intraday_path.exists()
    assert intraday_path.name == "intraday_latest.html"
    # 没有归档文件
    assert not list(output_dir.glob("report_*.html"))


def test_run_intraday_marks_stale_on_network_failure(monkeypatch, tmp_path):
    """spec §7.4: 新浪失败时不计算基差，标 stale。"""
    def mock_futures_fail(variety, observed_at, timeout=8.0):
        from flow_dashboard.data.sina_providers import QuoteBatch
        return QuoteBatch(
            provider="sina", observed_at=observed_at,
            received_at=pd.Timestamp.now(tz="Asia/Shanghai"),
            parse_version="sina_v1", quotes=[],
            failures=[{"kind": "network_error", "error": "test"}],
        )

    def mock_spot_fail(provider_codes, observed_at, timeout=6.0):
        from flow_dashboard.data.sina_providers import QuoteBatch
        return QuoteBatch(
            provider="sina", observed_at=observed_at,
            received_at=pd.Timestamp.now(tz="Asia/Shanghai"),
            parse_version="sina_v1", quotes=[],
            failures=[{"kind": "network_error", "error": "test"}],
        )

    monkeypatch.setattr("flow_dashboard.pipeline.fetch_futures_snapshot", mock_futures_fail)
    monkeypatch.setattr("flow_dashboard.pipeline.fetch_snapshot", mock_spot_fail)

    output_dir = tmp_path / "x"
    output_dir.mkdir()
    intraday_path = run_intraday(
        as_of=pd.Timestamp("2026-08-12 14:30", tz="Asia/Shanghai"),
        output_dir=output_dir,
        lock_path=output_dir / "runners.lock",
    )
    html = intraday_path.read_text()
    assert "stale" in html.lower() or "数据不可得" in html
    # 不应有基差计算结果
    assert "basis_points" not in html
