"""早报 09:15 补跑条件。"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from flow_dashboard.config import TIMEZONE


def should_retry_finalize(output_dir: Path | str, data_date: str, as_of: pd.Timestamp) -> bool:
    """当日 08:00 后没有完整报告时，09:15 补跑。"""
    manifest_dir = Path(output_dir) / "manifest"
    current_day = pd.Timestamp(as_of)
    if current_day.tzinfo is not None:
        current_day = current_day.tz_convert(TIMEZONE)
    candidates = sorted(manifest_dir.glob(f"{data_date}_v*.json"), reverse=True)
    for path in candidates:
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
            run_at = pd.Timestamp(manifest["run_at"])
            if run_at.tzinfo is not None:
                run_at = run_at.tz_convert(TIMEZONE)
            if run_at.date() == current_day.date() and run_at.hour >= 8:
                return manifest.get("panel_status", {}).get("is_partial") is not False
        except (OSError, ValueError, KeyError, TypeError):
            continue
    return True
