"""Red Line 1 端到端守护：追加未来行不改变历史值。

spec §3.5 共通验收 + Red Line 1。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import pytest

from flow_dashboard.pipeline import run_eod_preview


_BASE_DATA = [
    {"ts_code": "510050.SH", "trade_date": pd.Timestamp("2026-08-07"),
     "share_in_shares": 100e8, "unit_nav": 3.0, "total_size_cny": 100e8 * 3,
     "etf_estimated_flow_cny": 1e9, "quality_flags": "",
     "label": "huijin", "dimension": "ownership",
     "available_at": pd.Timestamp("2026-08-12 19:30", tz="Asia/Shanghai"),
     "source_date": pd.Timestamp("2026-08-07"),
     "first_observed_at": pd.Timestamp("2026-08-12 19:30", tz="Asia/Shanghai"),
     "fetched_at": pd.Timestamp("2026-08-12 19:30", tz="Asia/Shanghai"),
     "source": "tushare", "source_version": "v1", "is_stale": False},
]


def test_suffix_invariance_e2e(tmp_path, monkeypatch):
    """追加 8-13 行后，8-7 行对应数据点的流量值在 v01 和 v02 中必须相等。"""

    state = {"data": list(_BASE_DATA)}

    def mock_load(codes, start, end, as_of):
        return pd.DataFrame(state["data"])

    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_etf_share_for_pipeline", mock_load
    )
    for m in ("_load_margin_for_pipeline", "_load_fut_daily_for_pipeline",
              "_load_index_daily_for_pipeline", "_load_fund_nav_for_pipeline"):
        monkeypatch.setattr(
            f"flow_dashboard.pipeline.{m}",
            lambda *a, **kw: pd.DataFrame(),
        )

    output_dir = tmp_path / "ashare_flow_daily"

    # v01
    v01_path = run_eod_preview(
        data_date="2026-08-07",
        as_of=pd.Timestamp("2026-08-07 19:30", tz="Asia/Shanghai"),
        output_dir=output_dir, lock_path=output_dir / "runners.lock",
    )
    v01_html = v01_path.read_text()
    v01_data_points = _extract_data_points(v01_html)

    # 追加 8-12 行
    state["data"].extend([
        {"ts_code": "510050.SH", "trade_date": pd.Timestamp("2026-08-12"),
         "share_in_shares": 110e8, "unit_nav": 3.1, "total_size_cny": 110e8 * 3.1,
         "etf_estimated_flow_cny": 2e9, "quality_flags": "",
         "label": "huijin", "dimension": "ownership",
         "available_at": pd.Timestamp("2026-08-13 09:30", tz="Asia/Shanghai"),
         "source_date": pd.Timestamp("2026-08-12"),
         "first_observed_at": pd.Timestamp("2026-08-13 09:30", tz="Asia/Shanghai"),
         "fetched_at": pd.Timestamp("2026-08-13 09:30", tz="Asia/Shanghai"),
         "source": "tushare", "source_version": "v1", "is_stale": False},
    ])

    # 注意：data_date=2026-08-07 → next_version_number 在 output_dir 中已有 v01 → 生成 v02
    v02_path = run_eod_preview(
        data_date="2026-08-07",
        as_of=pd.Timestamp("2026-08-13 09:30", tz="Asia/Shanghai"),
        output_dir=output_dir, lock_path=output_dir / "runners.lock",
    )
    v02_html = v02_path.read_text()
    v02_data_points = _extract_data_points(v02_html)

    # 断言：v01 与 v02 的 data_date=2026-08-07 数据点子集相等
    # （v02 多了 8-12 行，但 8-7 行的 y 值应一致）
    for date_key, y_val in v01_data_points.items():
        assert date_key in v02_data_points, f"{date_key} 在 v02 中消失"
        assert v02_data_points[date_key] == pytest.approx(y_val, abs=1e6), (
            f"Red Line 1 violation: {date_key} v01={y_val} vs v02={v02_data_points[date_key]}"
        )


def _extract_data_points(html: str) -> dict:
    """从 Plotly HTML 中解析 trade_date → y 值。

    Plotly 嵌入 JSON；用 regex 提取 x/y 数组。
    """
    points: dict[str, float] = {}
    # 简单提取 "x":["2026-08-07"], "y":[1e9]
    pattern = re.compile(r'"x":\[([^\]]+)\],"y":\[([^\]]+)\]')
    for match in pattern.finditer(html):
        xs = match.group(1).split(",")
        ys = match.group(2).split(",")
        for x, y in zip(xs, ys):
            x = x.strip().strip('"')
            try:
                y_val = float(y.strip())
            except ValueError:
                continue
            points[x] = y_val
    return points
