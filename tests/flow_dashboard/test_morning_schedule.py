"""08:00 首次发布、09:15 按完整度补跑。"""
import json
import plistlib
from pathlib import Path

import pandas as pd

from flow_dashboard.schedule import should_retry_finalize


def test_retry_when_morning_manifest_absent(tmp_path):
    assert should_retry_finalize(tmp_path, "2026-10-13", pd.Timestamp("2026-10-14 09:15", tz="Asia/Shanghai"))


def test_retry_when_morning_report_partial(tmp_path):
    d = tmp_path / "manifest"
    d.mkdir()
    (d / "2026-10-13_v01.json").write_text(json.dumps({
        "run_at": "2026-10-14T08:00:10+08:00", "panel_status": {"is_partial": True}
    }))
    assert should_retry_finalize(tmp_path, "2026-10-13", pd.Timestamp("2026-10-14 09:15", tz="Asia/Shanghai"))


def test_skip_when_morning_report_complete(tmp_path):
    d = tmp_path / "manifest"
    d.mkdir()
    (d / "2026-10-13_v01.json").write_text(json.dumps({
        "run_at": "2026-10-14T08:00:10+08:00", "panel_status": {"is_partial": False}
    }))
    assert not should_retry_finalize(tmp_path, "2026-10-13", pd.Timestamp("2026-10-14 09:15", tz="Asia/Shanghai"))


def test_previous_evening_report_does_not_suppress_morning_retry(tmp_path):
    d = tmp_path / "manifest"
    d.mkdir()
    (d / "2026-10-13_v01.json").write_text(json.dumps({
        "run_at": "2026-10-13T18:45:00+08:00", "panel_status": {"is_partial": False}
    }))
    assert should_retry_finalize(tmp_path, "2026-10-13", pd.Timestamp("2026-10-14 09:15", tz="Asia/Shanghai"))


def test_installed_job_definitions_use_two_morning_times_and_fetch_only_hk():
    root = Path(__file__).resolve().parents[2] / "scripts" / "launchd"

    def read(name):
        return plistlib.loads((root / name).read_bytes())

    first = read("com.ygr.ashare-flow.morning-first.plist")
    retry = read("com.ygr.ashare-flow.daily-finalize.plist")
    hk = read("com.ygr.hk-short.eod.plist")
    assert first["StartCalendarInterval"] == {"Hour": 8, "Minute": 0}
    assert retry["StartCalendarInterval"] == {"Hour": 9, "Minute": 15}
    assert "--retry-if-partial" in retry["ProgramArguments"][-1]
    assert "--fetch-only" in hk["ProgramArguments"][-1]
