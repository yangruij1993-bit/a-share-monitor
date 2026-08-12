"""api_capabilities.yaml 生成器契约测试。"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from flow_dashboard.phase_a.api_capabilities import build_capabilities


def test_build_capabilities_returns_dict_with_required_keys():
    caps = build_capabilities()
    for key in ("tushare", "sina"):
        assert key in caps
    tushare = caps["tushare"]
    for endpoint in ("fund_basic", "etf_share_size", "fund_nav", "fund_daily",
                     "margin", "fut_basic", "fut_daily", "index_daily"):
        assert endpoint in tushare, f"missing endpoint: {endpoint}"
        entry = tushare[endpoint]
        assert "observed_columns" in entry
        assert "units" in entry
        assert "notes" in entry


def test_sina_caps_include_node_mark():
    caps = build_capabilities()
    sina = caps["sina"]
    assert "futures_node_mark" in sina
    assert sina["futures_node_mark"]["IC"] == "zzgz_qh"
    assert sina["futures_node_mark"]["IM"] == "im_qh"


def test_caps_yaml_round_trip(tmp_path):
    caps = build_capabilities()
    target = tmp_path / "api_capabilities.yaml"
    target.write_text(yaml.safe_dump(caps, allow_unicode=True, sort_keys=False))
    reloaded = yaml.safe_load(target.read_text())
    assert reloaded["tushare"]["fund_basic"]["observed_columns"][0] == caps["tushare"]["fund_basic"]["observed_columns"][0]
