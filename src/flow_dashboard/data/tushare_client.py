"""tushare pro_api 客户端包装。

唯一职责：返回已设置 token 的 tushare pro_api 实例。不在这里做字段规范化或缓存。
"""
from __future__ import annotations

from flow_dashboard.config import get_tushare_token


def get_pro_api():
    """返回 tushare pro_api 实例。token 来自 ASHARE_FLOW_TUSHARE_TOKEN。"""
    token = get_tushare_token()
    import tushare as ts

    ts.set_token(token)
    return ts.pro_api()
