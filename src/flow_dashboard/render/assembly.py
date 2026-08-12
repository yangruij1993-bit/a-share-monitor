"""Assembly：原子发布 + manifest + symlink + 文件锁。

per spec §3.3:
- staging 文件 → 完整性检查 → 原子 replace
- latest.html 用 symlink 原子替换
- intraday 只更新 intraday_latest.html
- 4 runner 共用文件锁
- 同日补跑 → _vNN
- manifest 保存输入 hash/size/mtime + run_at + 板块状态
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime
from pathlib import Path

import pandas as pd

from flow_dashboard.config import TIMEZONE


class RunnerLockError(RuntimeError):
    """无法获取 runner 锁。"""


@contextlib.contextmanager
def acquire_runner_lock(lock_path: Path | str, *, timeout: float = 0.0):
    """fcntl 文件锁；timeout=0 立即失败。"""
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "w")
    try:
        if timeout == 0:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise RunnerLockError(f"无法在 {timeout}s 内获取锁: {lock_path}")
                    time.sleep(0.05)
        yield
    finally:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


def next_version_number(output_dir: Path | str, data_date: str) -> int:
    """扫描已有 report_<data_date>_vNN.html，返回 max+1。"""
    output_dir = Path(output_dir)
    pattern = re.compile(rf"report_{re.escape(data_date)}_v(\d+)\.html$")
    max_v = 0
    if output_dir.exists():
        for p in output_dir.iterdir():
            m = pattern.match(p.name)
            if m:
                max_v = max(max_v, int(m.group(1)))
    return max_v + 1


def publish_archive(
    *,
    output_dir: Path | str,
    data_date: str,
    html_body: str,
    manifest_payload: dict,
    full_html: str,
) -> tuple[Path, Path, Path, Path]:
    """发布归档版本：写 staging → 完整性检查 → 原子 rename → 更新 latest symlink。

    Returns:
        (staging_path, archive_path, symlink_path, manifest_path)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    staging_dir = output_dir / "staging"
    staging_dir.mkdir(exist_ok=True)
    manifest_dir = output_dir / "manifest"
    manifest_dir.mkdir(exist_ok=True)

    version = next_version_number(output_dir, data_date)
    archive_name = f"report_{data_date}_v{version:02d}.html"
    archive_path = output_dir / archive_name
    manifest_name = f"{data_date}_v{version:02d}.json"
    manifest_path = manifest_dir / manifest_name

    # staging 写入
    staging_path = staging_dir / f"{archive_name}.{uuid.uuid4().hex}.tmp"
    staging_path.write_text(full_html, encoding="utf-8")

    # 完整性检查
    if "<html" not in full_html.lower() or "</html>" not in full_html.lower():
        staging_path.unlink(missing_ok=True)
        raise ValueError("HTML 完整性检查失败：缺少 <html>/</html>")

    # 原子 rename
    staging_path.rename(archive_path)

    # manifest
    payload = {
        "data_date": data_date,
        "version": version,
        "archive_name": archive_name,
        "run_at": datetime.now(tz=pd.Timestamp.now(tz=TIMEZONE).tz).isoformat(),
        "panels": manifest_payload.get("panels", []),
        "source_versions": manifest_payload.get("source_versions", {}),
        "input_files": manifest_payload.get("input_files", []),
        "panel_status": manifest_payload.get("panel_status", {}),
    }
    manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    # latest symlink 原子替换
    symlink_path = output_dir / "latest.html"
    tmp_sym = output_dir / "latest.html.tmp"
    if tmp_sym.exists() or tmp_sym.is_symlink():
        tmp_sym.unlink()
    os.symlink(archive_path.name, tmp_sym)
    os.replace(tmp_sym, symlink_path)

    return staging_path, archive_path, symlink_path, manifest_path


def publish_intraday(
    *,
    output_dir: Path | str,
    full_html: str,
) -> Path:
    """intraday runner 专用：原子更新 intraday_latest.html，不写归档。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    staging_dir = output_dir / "staging"
    staging_dir.mkdir(exist_ok=True)

    staging_path = staging_dir / f"intraday_latest.{uuid.uuid4().hex}.tmp"
    staging_path.write_text(full_html, encoding="utf-8")
    if "<html" not in full_html.lower():
        staging_path.unlink(missing_ok=True)
        raise ValueError("HTML 完整性检查失败")

    target = output_dir / "intraday_latest.html"
    os.replace(staging_path, target)
    return target


def compute_file_meta(path: Path) -> dict:
    """计算文件 hash/size/mtime；用于 manifest.input_files。"""
    if not path.exists():
        return {"path": str(path), "exists": False}
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return {
        "path": str(path),
        "exists": True,
        "size": path.stat().st_size,
        "mtime": path.stat().st_mtime,
        "sha256": h.hexdigest(),
    }
