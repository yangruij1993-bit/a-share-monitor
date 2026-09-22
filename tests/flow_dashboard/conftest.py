"""pytest 共享 fixtures。

live marker：标记需要真实 token/网络的测试。默认整体跳过，--run-live 显式开启。
"""

from __future__ import annotations

import pytest

from flow_dashboard.config import SetupError, get_tushare_token


def pytest_addoption(parser):
    parser.addoption(
        "--run-live",
        action="store_true",
        default=False,
        help="运行 @live 标记的真实网络测试（默认跳过）",
    )


def pytest_collection_modifyitems(config, items):
    """live 测试默认跳过；--run-live 开启后仍需 token 可用。"""
    run_live = config.getoption("--run-live")
    try:
        get_tushare_token()
        token_available = True
    except SetupError:
        token_available = False

    skip_no_token = pytest.mark.skip(reason="ASHARE_FLOW_TUSHARE_TOKEN 未设置")
    skip_not_opted_in = pytest.mark.skip(
        reason="live 测试默认跳过；--run-live 显式开启"
    )
    for item in items:
        if "live" in item.keywords:
            if not run_live:
                item.add_marker(skip_not_opted_in)
            elif not token_available:
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
