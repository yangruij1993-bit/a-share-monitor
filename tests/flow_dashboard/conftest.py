"""pytest 共享 fixtures。

live marker：标记需要真实 token/网络的测试。CI 缺 token 时整体跳过。
"""
from __future__ import annotations

import os

import pytest

from flow_dashboard.config import get_tushare_token, SetupError


def pytest_collection_modifyitems(config, items):
    """缺 token 时跳过所有 live 测试。"""
    try:
        get_tushare_token()
        token_available = True
    except SetupError:
        token_available = False

    skip_no_token = pytest.mark.skip(reason="ASHARE_FLOW_TUSHARE_TOKEN 未设置")
    for item in items:
        if "live" in item.keywords and not token_available:
            item.add_marker(skip_no_token)


@pytest.fixture(scope="session")
def tushare_token() -> str:
    return get_tushare_token()


@pytest.fixture
def evidence_dir(tmp_path):
    """用 tmp_path 替代真实 EVIDENCE_DIR，避免污染 git。"""
    d = tmp_path / "phase_a_evidence"
    d.mkdir()
    return d
