"""sina_client 契约测试。

- node="zzgz_qh" 返回 IC 全部活跃合约
- 每条记录含 symbol/trade/settlement/ticktime/tradedate
- 缺字段时显式 None，不静默丢列
"""
from __future__ import annotations

import pytest

from flow_dashboard.data.sina_client import fetch_futures_node, FUTURES_NODE_MARK


def test_node_mark_contract():
    assert FUTURES_NODE_MARK["IC"] == "zzgz_qh"
    assert FUTURES_NODE_MARK["IM"] == "im_qh"


@pytest.mark.live
def test_fetch_futures_node_ic_returns_contracts(tushare_token):
    """live 标记仅用于需要网络的测试；token 与新浪无关但用作整体环境就绪代理。"""
    df = fetch_futures_node("IC")
    assert len(df) > 0
    for col in ("symbol", "trade", "settlement", "ticktime", "tradedate", "name"):
        assert col in df.columns, f"missing: {col}"
    assert df["symbol"].str.startswith("IC").all()


@pytest.mark.live
def test_fetch_spot_indices_quotes(tushare_token):
    """新浪 hq.sinajs.cn/list=sh000905,sh000852 现货指数。"""
    from flow_dashboard.data.sina_client import fetch_spot_indices
    df = fetch_spot_indices(["sh000905", "sh000852"])
    assert len(df) == 2
    for col in ("provider_code", "name", "last", "time", "date"):
        assert col in df.columns
    assert df["last"].dtype.kind == "f"
