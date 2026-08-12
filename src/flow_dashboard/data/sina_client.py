"""新浪行情 HTTP client。

职责：仅负责原始 HTTP 取数与最小解析；不做基差计算、不写 quality_flags。
- CFFEX 期货：用 VIP PHP API（hq.sinajs.cn 不支持 CFFEX）
- 现货指数：用 hq.sinajs.cn/list=

per spec §1.4: 盘中快照必须原样保存 provider_code、原始报价时间、系统接收时间、解析版本。
本 client 只产出 pandas DataFrame；上层 provider 负责加 received_at 等审计列。
"""
from __future__ import annotations

import json
import re
from typing import Iterable

import pandas as pd
import requests

# 新浪 CFFEX 期货 node mark（已通过 akshare futures_symbol_mark 验证）
FUTURES_NODE_MARK: dict[str, str] = {
    "IF": "qz_qh",       # 沪深300指数期货
    "IH": "szgz_qh",     # 上证50指数期货
    "IC": "zzgz_qh",     # 中证500指数期货
    "IM": "im_qh",       # 中证1000股指期货
}

_FUTURES_URL = (
    "https://vip.stock.finance.sina.com.cn/quotes_service/api/"
    "json_v2.php/Market_Center.getHQFuturesData"
)
_SPOT_URL = "https://hq.sinajs.cn/list={codes}"
_HEADERS = {
    "Referer": "https://finance.sina.com.cn",
    "User-Agent": "Mozilla/5.0 (compatible; ashare-flow-dashboard/0.1)",
}
PARSE_VERSION = "sina_v1"


def fetch_futures_node(variety: str, timeout: float = 8.0) -> pd.DataFrame:
    """拉取一个 CFFEX 品种（IF/IH/IC/IM）的全部活跃合约快照。"""
    node = FUTURES_NODE_MARK.get(variety)
    if not node:
        raise ValueError(f"unknown variety: {variety}; expected one of {list(FUTURES_NODE_MARK)}")
    params = {
        "page": "1", "sort": "position", "asc": "0",
        "node": node, "base": "futures",
    }
    resp = requests.get(_FUTURES_URL, params=params, headers=_HEADERS, timeout=timeout)
    resp.encoding = "utf-8"
    body = resp.text
    if not body or body == "[]":
        return pd.DataFrame(columns=[
            "symbol", "name", "trade", "settlement", "presettlement",
            "open", "high", "low", "close", "volume", "position",
            "ticktime", "tradedate", "prevsettlement",
        ])
    data = json.loads(body)
    df = pd.DataFrame(data)
    for col in ("trade", "settlement", "presettlement", "open", "high",
                "low", "close", "volume", "position", "prevsettlement"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def fetch_spot_indices(provider_codes: Iterable[str], timeout: float = 5.0) -> pd.DataFrame:
    """拉取现货指数（sh000905=CSI500, sh000852=CSI1000 等）。

    新浪 hq.sinajs.cn 返回 GBK 编码的 var 赋值字符串；解析为 DataFrame。
    """
    codes = list(provider_codes)
    url = _SPOT_URL.format(codes=",".join(codes))
    resp = requests.get(url, headers=_HEADERS, timeout=timeout)
    resp.encoding = "gbk"
    body = resp.text
    rows = []
    pattern = re.compile(r'var hq_str_(?P<code>[^=]+)="(?P<payload>[^"]*)";')
    for m in pattern.finditer(body):
        code = m.group("code")
        payload = m.group("payload")
        parts = payload.split(",")
        if len(parts) < 32:
            continue

        def _f(idx):
            try:
                return float(parts[idx])
            except (ValueError, IndexError):
                return None

        rows.append({
            "provider_code": code,
            "name": parts[0],
            "pre_close": _f(1),
            "open": _f(2),
            "last": _f(3),
            "high": _f(4),
            "low": _f(5),
            "date": parts[30] if len(parts) > 30 else None,
            "time": parts[31] if len(parts) > 31 else None,
        })
    return pd.DataFrame(rows)

