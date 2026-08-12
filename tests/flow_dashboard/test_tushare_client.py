"""tushare_client 契约测试。

get_pro_api():
- 返回 tushare.pro_api 实例
- 缺 token 时抛 SetupError（已在 conftest 处理 skip）
"""
from __future__ import annotations

import pytest

from flow_dashboard.config import SetupError
from flow_dashboard.data.tushare_client import get_pro_api


@pytest.mark.live
def test_get_pro_api_returns_callable(tushare_token):
    pro = get_pro_api()
    # DataApi 不是 callable，但有 fund_basic 等方法属性
    assert hasattr(pro, "fund_basic")
    # 实际调用一次，确认 token 有效
    df = pro.fund_basic(market="E", limit=1)
    assert len(df) == 1
    assert "ts_code" in df.columns


def test_get_pro_api_missing_token(monkeypatch):
    monkeypatch.delenv("ASHARE_FLOW_TUSHARE_TOKEN", raising=False)
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    with pytest.raises(SetupError):
        get_pro_api()
