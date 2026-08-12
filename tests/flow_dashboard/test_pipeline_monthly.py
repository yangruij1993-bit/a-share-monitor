"""run_monthly 测试 — Phase B 只刷分类表。"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from flow_dashboard.pipeline import run_monthly


def test_run_monthly_refreshes_pit_labels(tmp_path, monkeypatch):
    """Phase B monthly 仅重写 PIT 标签快照（不计算 s6/s7）。"""
    output_dir = tmp_path / "x"
    output_dir.mkdir()
    labels_path = tmp_path / "labels.csv"
    labels_path.write_text(
        "ts_code,dimension,label,effective_from,effective_to,evidence_source\n"
        "510050.SH,ownership,huijin,2015-07-05,2099-12-31,汇金公告\n"
    )
    snapshot_path = run_monthly(
        as_of=pd.Timestamp("2026-08-03 09:00", tz="Asia/Shanghai"),
        output_dir=output_dir,
        labels_path=labels_path,
    )
    assert snapshot_path.exists()
    assert snapshot_path.suffix == ".csv"


def test_run_monthly_preserves_previous_when_unchanged(tmp_path, monkeypatch):
    """标签源无变化时，重写后内容相同（md5 一致）。"""
    labels_path = tmp_path / "labels.csv"
    labels_path.write_text(
        "ts_code,dimension,label,effective_from,effective_to,evidence_source\n"
        "510050.SH,ownership,huijin,2015-07-05,2099-12-31,汇金公告\n"
    )
    output_dir = tmp_path / "x"
    output_dir.mkdir()
    p1 = run_monthly(
        as_of=pd.Timestamp("2026-08-03 09:00", tz="Asia/Shanghai"),
        output_dir=output_dir, labels_path=labels_path,
    )
    p2 = run_monthly(
        as_of=pd.Timestamp("2026-09-01 09:00", tz="Asia/Shanghai"),
        output_dir=output_dir, labels_path=labels_path,
    )
    assert p1.read_text() == p2.read_text()
