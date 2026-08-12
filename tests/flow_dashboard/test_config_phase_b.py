"""Phase B config 添加项测试。"""
from __future__ import annotations

from pathlib import Path

from flow_dashboard.config import (
    OUTPUT_DIR, MANIFEST_DIR, INTRADAY_OUTPUT,
    RUNNERS_LOCK, STAGING_DIR,
)


def test_output_dir_under_project():
    assert OUTPUT_DIR.name == "ashare_flow_daily"
    assert "output" in str(OUTPUT_DIR)

def test_manifest_dir_under_output():
    assert MANIFEST_DIR.parent == OUTPUT_DIR
    assert MANIFEST_DIR.name == "manifest"

def test_intraday_output_distinct_from_archive():
    """spec §3.3: intraday 只更新 intraday_latest.html，不写归档。"""
    assert INTRADAY_OUTPUT.name == "intraday_latest.html"
    assert INTRADAY_OUTPUT.parent == OUTPUT_DIR

def test_runners_lock_path():
    assert RUNNERS_LOCK.name == "runners.lock"
    assert RUNNERS_LOCK.parent == OUTPUT_DIR

def test_staging_dir_under_output():
    assert STAGING_DIR.parent == OUTPUT_DIR
    assert STAGING_DIR.name == "staging"
