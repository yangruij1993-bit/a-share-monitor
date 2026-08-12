"""Assembly 契约测试：原子替换、manifest、symlink。"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from flow_dashboard.render.assembly import (
    publish_archive,
    publish_intraday,
    acquire_runner_lock,
    RunnerLockError,
    next_version_number,
)


def test_next_version_number_increments(tmp_path):
    # 空目录 → v01
    assert next_version_number(tmp_path, "2026-08-12") == 1
    # 已有 v01 → v02
    (tmp_path / "report_2026-08-12_v01.html").write_text("x")
    assert next_version_number(tmp_path, "2026-08-12") == 2


def test_publish_archive_atomic_replace(tmp_path):
    output_dir = tmp_path / "ashare_flow_daily"
    output_dir.mkdir()
    staging, archive_path, symlink_path, manifest_path = publish_archive(
        output_dir=output_dir,
        data_date="2026-08-12",
        html_body="<div>hello</div>",
        manifest_payload={"panels": ["huijin"], "source_versions": {"etf_share": "v1"}},
        full_html="<html>...</html>",
    )
    assert archive_path.exists()
    assert archive_path.read_text() == "<html>...</html>"
    # symlink 指向 archive
    assert symlink_path.is_symlink()
    assert os.readlink(symlink_path) == str(archive_path.name) or str(archive_path) == str(symlink_path.resolve())
    # manifest 落盘
    assert manifest_path.exists()
    payload = json.loads(manifest_path.read_text())
    assert payload["panels"] == ["huijin"]
    assert "run_at" in payload


def test_publish_archive_does_not_overwrite_existing(tmp_path):
    """spec §3.3: 同一报告日补跑生成新版本，不覆盖旧版。"""
    output_dir = tmp_path / "x"
    output_dir.mkdir()
    _, archive1, _, _ = publish_archive(
        output_dir=output_dir, data_date="2026-08-12",
        html_body="", manifest_payload={},
        full_html="<html>v1</html>",
    )
    _, archive2, symlink, _ = publish_archive(
        output_dir=output_dir, data_date="2026-08-12",
        html_body="", manifest_payload={},
        full_html="<html>v2</html>",
    )
    assert archive1.exists()
    assert archive1.read_text() == "<html>v1</html>"
    assert archive2.read_text() == "<html>v2</html>"
    # symlink 指向最新
    assert symlink.resolve() == archive2.resolve()


def test_publish_intraday_does_not_write_archive(tmp_path):
    """spec §3.3: intraday 只更新 intraday_latest.html，不写归档。"""
    output_dir = tmp_path / "x"
    output_dir.mkdir()
    intraday_path = publish_intraday(
        output_dir=output_dir,
        full_html="<html>intraday</html>",
    )
    assert intraday_path.exists()
    assert intraday_path.name == "intraday_latest.html"
    # 不应产生 report_*.html
    assert not list(output_dir.glob("report_*.html"))


def test_acquire_runner_lock_serializes(tmp_path):
    lock_path = tmp_path / "runners.lock"
    # 首次获取应成功
    with acquire_runner_lock(lock_path):
        # 同一进程再次获取应失败（模拟并发）
        with pytest.raises(RunnerLockError):
            with acquire_runner_lock(lock_path, timeout=0.1):
                pass


def test_publish_archive_rejects_truncated_disk_write(tmp_path, monkeypatch):
    """磁盘写入被截断（staging 文件不含 </html>）→ publish_archive 必须报错且清理 staging。"""
    from flow_dashboard.render import assembly

    output_dir = tmp_path / "x"
    output_dir.mkdir()

    # 仿造 write_text 截断：只写前 5 个字符（破坏 </html>），不递归到原 write_text
    original_write_text = Path.write_text

    def _truncate_write(self, content, encoding="utf-8", errors=None, newline=None):
        # 直接用 open() 写入截断内容，绕过 Path.write_text 防止递归
        with open(self, "w", encoding=encoding, errors=errors, newline=newline) as f:
            f.write(content[:5])

    monkeypatch.setattr(Path, "write_text", _truncate_write)

    with pytest.raises(ValueError, match="完整性"):
        assembly.publish_archive(
            output_dir=output_dir, data_date="2026-08-12",
            html_body="", manifest_payload={},
            full_html="<html><body>long body that gets truncated</body></html>",
        )
    # staging 清理
    assert not list((output_dir / "staging").glob("*.tmp"))
    # archive 未生成
    assert not list(output_dir.glob("report_*.html"))
