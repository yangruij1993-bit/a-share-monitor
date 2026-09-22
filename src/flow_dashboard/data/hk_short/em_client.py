"""东方财富港股客户端：逐证券卖空（股票口径）、K线、总股本。

源验证 §1（sellshort HTML）与 §5（push2his kline / push2 f84）。
口径冻结：sellshort 只含主板+GEM 股票（含 RMB 柜台），不含 ETF/ETP/REIT/L&I。
"""

from __future__ import annotations

import logging
import re

import pandas as pd

from flow_dashboard.config import HK_EM_HEADERS
from flow_dashboard.data.hk_short import http_client

log = logging.getLogger(__name__)

BASE = "https://hk.eastmoney.com"

# 源验证 §1 实测行结构：序号|代码锚点|名称td(被行内通配跳过再单独抓)|最新价|沽空数量|沽空均价|沽空金额|总成交金额|SSR%|日期
# 行内通配用 (?:(?!</tr>).)*? 收紧：格式漂移时不允许回溯跨过 </tr> 拼接相邻行（质量评审加固）
SELLSHORT_ROW_RE = re.compile(
    r"<tr>\s*<td><span>\d+</span></td>\s*<td>\s*<a[^>]*>(\d{5})</a>\s*</td>(?:(?!</tr>).)*?"
    r"<td><span>([\d.]+)</span></td>\s*"  # 最新价（丢弃）
    r"<td><span>([\d,.]+)\s*</span></td>\s*"  # 沽空数量
    r"<td><span>([\d.]+)</span></td>\s*"  # 沽空平均价
    r"<td><span>([\d.万亿]+)</span></td>\s*"  # 沽空金额
    r"<td><span>([\d.万亿]+)</span></td>\s*"  # 总成交金额
    r"<td><span>([\d.]+)%</span></td>\s*"  # SSR
    r"<td><span>(\d{4}-\d{2}-\d{2})</span></td>",  # 日期
    re.DOTALL,
)
NAME_RE = re.compile(r"</a>\s*</td>\s*<td[^>]*>\s*<a[^>]*>([^<]+)</a>", re.DOTALL)


def parse_amount(text: str) -> float:
    t = text.strip().replace(",", "")
    if t.endswith("亿"):
        return float(t[:-1]) * 1e8
    if t.endswith("万"):
        return float(t[:-1]) * 1e4
    return float(t)


def parse_sellshort_html(html_text: str) -> pd.DataFrame:
    rows = []
    for m in SELLSHORT_ROW_RE.finditer(html_text):
        code, _last_price, shares, avg_px, amt, tov, ssr, d = m.groups()
        nm = NAME_RE.search(m.group(0))
        rows.append(
            {
                "code": code,
                "name": nm.group(1).strip() if nm else "",
                "short_shares": float(shares.replace(",", "")),
                "short_avg_price": float(avg_px),
                "short_amount": parse_amount(amt),
                "turnover": parse_amount(tov),
                "ssr_pct": float(ssr),
                "source_date": d,
            }
        )
    return pd.DataFrame(rows)


def _max_page(html_text: str) -> int:
    pages = [int(p) for p in re.findall(r"sellshort_(\d+)\.html", html_text)]
    return max(pages) if pages else 1


def _fetch_page_text(page: int, params: dict) -> str:
    url = f"{BASE}/sellshort.html" if page == 1 else f"{BASE}/sellshort_{page}.html"
    return http_client.fetch_text(url, params=params, headers=HK_EM_HEADERS)


def _collect_pages(params: dict) -> pd.DataFrame:
    """第 1 页解析 pagerbox 得总页数后逐页抓取（`&page=` 参数无效，源验证 §1）。"""
    p1 = _fetch_page_text(1, params)
    frames = [parse_sellshort_html(p1)]
    for p in range(2, _max_page(p1) + 1):
        frames.append(parse_sellshort_html(_fetch_page_text(p, params)))
    non_empty = [f for f in frames if not f.empty]
    if not non_empty:
        return pd.DataFrame()
    return pd.concat(non_empty, ignore_index=True)


def fetch_sellshort_day(date_str: str) -> pd.DataFrame:
    """单日全市场（股票口径）卖空。非交易日返回空 DataFrame，不抛错。"""
    ds = pd.Timestamp(date_str).strftime("%Y-%m-%d")
    out = _collect_pages({"code": "", "sdate": ds, "edate": ds})
    if not out.empty:
        out = out[out["source_date"] == ds].reset_index(drop=True)
    if not out.empty:
        out["trade_date"] = pd.Timestamp(date_str)
    return out


def fetch_sellshort_stock(code: str, start, end) -> pd.DataFrame:
    """单只股票区间历史：一次区间查询跨日翻页（行内自带日期列，每页 50 行）。"""
    out = _collect_pages(
        {
            "code": code,
            "sdate": pd.Timestamp(start).strftime("%Y-%m-%d"),
            "edate": pd.Timestamp(end).strftime("%Y-%m-%d"),
        }
    )
    if not out.empty:
        out["trade_date"] = pd.to_datetime(out["source_date"])
    return out


def fetch_kline(
    secid: str, beg, end, *, now: pd.Timestamp | None = None
) -> pd.DataFrame:
    """日 K（不复权）。丢弃未完成当日 K 线（16:10 HKT 前，源验证 §5）。"""
    j = http_client.fetch_json(
        "https://push2his.eastmoney.com/api/qt/stock/kline/get",
        params={
            "secid": secid,
            "fields1": "f1,f2,f3",
            "fields2": "f51,f52,f53,f54,f55,f56,f57",
            "klt": "101",
            "fqt": "0",
            "beg": pd.Timestamp(beg).strftime("%Y%m%d"),
            "end": pd.Timestamp(end).strftime("%Y%m%d"),
        },
        headers=HK_EM_HEADERS,
        validate=lambda j: bool(j.get("data") and j["data"].get("klines")),
    )
    rows = []
    for line in j["data"]["klines"]:
        d, o, c, h, low, v, a = line.split(",")
        rows.append(
            {
                "secid": secid,
                "trade_date": pd.Timestamp(d),
                "open": float(o),
                "close": float(c),
                "high": float(h),
                "low": float(low),
                "volume": float(v),
                "amount": float(a),
            }
        )
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    ts_now = now if now is not None else pd.Timestamp.now(tz="Asia/Shanghai")
    ts_now = (
        ts_now.tz_convert("Asia/Shanghai").tz_localize(None)
        if ts_now.tzinfo
        else ts_now
    )
    last = df.iloc[-1]
    if (
        last["trade_date"] == ts_now.normalize()
        and ts_now.hour * 60 + ts_now.minute < 16 * 60 + 10
    ):
        df = df.iloc[:-1]
    return df.reset_index(drop=True)


def fetch_total_shares(code: str) -> int:
    """总股本（f84，当前快照值；PIT 语义见 loaders.load_total_shares）。"""
    j = http_client.fetch_json(
        "https://push2.eastmoney.com/api/qt/stock/get",
        params={"secid": f"116.{code}", "fields": "f84", "fltt": "2", "invt": "2"},
        headers=HK_EM_HEADERS,
        validate=lambda j: j.get("data") and j["data"].get("f84") is not None,
    )
    return int(j["data"]["f84"])
