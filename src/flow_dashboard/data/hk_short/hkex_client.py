"""HKEX 官方客户端：dayquot/ashtmain 全口径卖空、ListOfSecurities 主表。

源验证 §2：单文件 ~26MB；SHORT SELLING 段被 <pre><font> 切块、含 &amp;、
行首杂散 %；PREVIOUS DAY'S ADJUSTED 段为 T-1 修正（loader 必须覆盖 T-1 缓存）。
"""

from __future__ import annotations

import html
import io
import logging
import re
import zipfile

import pandas as pd

from flow_dashboard.config import HKEX_HEADERS
from flow_dashboard.data.hk_short import http_client
from flow_dashboard.data.hk_short.hk_calendar import prev_trading_day

log = logging.getLogger(__name__)

DAYQUOT_URL = "https://www.hkex.com.hk/eng/stat/smstat/dayquot/d{yymmdd}e.htm"
ASHTMAIN_URL = "https://www.hkex.com.hk/eng/stat/smstat/ssturnover/ncms/ashtmain.htm"
LOS_URL = (
    "https://www.hkex.com.hk/eng/services/trading/securities/"
    "securitieslists/ListOfSecurities.xlsx"
)

_HDR_DAILY = "SHORT SELLING TURNOVER - DAILY REPORT"
_HDR_ADJUSTED = "PREVIOUS DAY'S ADJUSTED SHORT SELLING TURNOVER"

_ROW_RE = re.compile(
    r"^\s*(\d{1,5})\s+(\S.*?)\s{2,}([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s*$",
    re.MULTILINE,
)

_LOS_ROW_RE = re.compile(r"<x:row [^>]*>(.*?)</x:row>", re.DOTALL)
_LOS_CELL_RE = re.compile(
    r'<x:c r="([A-Z]+)\d+"[^>]*?(?: t="(\w+)")?[^>]*>(.*?)</x:c>', re.DOTALL
)


def _clean_section(seg: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", "", seg))
    return re.sub(r"[ \t]*\n[ \t]*%?", "\n", text)


def _section(html_text: str, header: str, end_markers: list[str]) -> str:
    i = html_text.find(header)
    if i < 0:
        return ""
    j = len(html_text)
    for em in end_markers:
        k = html_text.find(em, i + len(header))
        if k > 0:
            j = min(j, k)
    return html_text[i:j]


def _rows_from_section(sec: str) -> pd.DataFrame:
    rows = []
    for m in _ROW_RE.finditer(_clean_section(sec)):
        code, name, short_sh, short_amt, total_sh, total_amt = m.groups()
        rows.append(
            {
                "code": code.zfill(5),
                "name": name.strip(),
                "short_shares": float(short_sh.replace(",", "")),
                "short_amount": float(short_amt.replace(",", "")),
                "total_shares_traded": float(total_sh.replace(",", "")),
                "turnover": float(total_amt.replace(",", "")),
            }
        )
    return pd.DataFrame(rows)


def parse_dayquot(
    html_text: str, *, data_date: str, prev_date: str | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """返回 (当日全口径逐证券, T-1 修正值)。prev_date 缺省用日历推。"""
    if prev_date is None:
        prev_date = prev_trading_day(data_date)
    daily = _rows_from_section(_section(html_text, _HDR_DAILY, [_HDR_ADJUSTED]))
    adjusted = _rows_from_section(
        _section(html_text, _HDR_ADJUSTED, [])
    )  # 段尾无固定边界，靠行正则特异性
    if not daily.empty:
        daily["trade_date"] = pd.Timestamp(data_date)
    if not adjusted.empty:
        adjusted["trade_date"] = pd.Timestamp(prev_date)
    return daily, adjusted


def fetch_dayquot(date_str: str) -> pd.DataFrame | None:
    """归档文件（404=超出滚动窗口或非交易日 → None）。返回合并了 T-1 修正的表。"""
    ts = pd.Timestamp(date_str)
    html_text = http_client.try_get(
        DAYQUOT_URL.format(yymmdd=ts.strftime("%y%m%d")), headers=HKEX_HEADERS
    )
    if html_text is None:
        return None
    daily, adjusted = parse_dayquot(html_text.text, data_date=date_str)
    frames = [f for f in (daily, adjusted) if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fetch_ashtmain(data_date: str) -> pd.DataFrame:
    """当日盘后汇总（归档生成前的当日版本，ncms 仅保留当日）。"""
    resp = http_client.try_get(ASHTMAIN_URL, headers=HKEX_HEADERS)
    if resp is None:
        return pd.DataFrame()
    daily, adjusted = parse_dayquot(resp.text, data_date=data_date)
    frames = [f for f in (daily, adjusted) if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def parse_list_of_securities(xlsx_bytes: bytes) -> tuple[pd.DataFrame, str]:
    """zipfile+re 解析（inline strings，无 sharedStrings，源验证 §6）。"""
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as z:
        xml = z.read("xl/worksheets/sheet1.xml").decode("utf-8", "ignore")
    raw_rows = []
    for rm in _LOS_ROW_RE.finditer(xml):
        cells: dict[str, str] = {}
        for cm in _LOS_CELL_RE.finditer(rm.group(1)):
            col, _t, inner = cm.groups()
            vm = re.search(r"<x:v>(.*?)</x:v>", inner, re.DOTALL)
            if vm:
                cells[col] = html.unescape(vm.group(1)).strip()
        raw_rows.append(cells)
    eff = ""
    if len(raw_rows) >= 2 and "A" in raw_rows[1]:
        eff = raw_rows[1]["A"]
    rows = []
    for r in raw_rows:
        code = r.get("A", "")
        if code.isdigit() and len(code) <= 5:
            rows.append(
                {
                    "code": code.zfill(5),
                    "name": r.get("B", ""),
                    "category": r.get("C", ""),
                    "sub_category": r.get("D", ""),
                }
            )
    return pd.DataFrame(rows), eff


def fetch_list_of_securities() -> tuple[pd.DataFrame, str]:
    resp = http_client.try_get(LOS_URL, headers=HKEX_HEADERS)
    if resp is None:
        return pd.DataFrame(), ""
    return parse_list_of_securities(resp.content)


def etf_set(los_df: pd.DataFrame) -> set[str]:
    """冻结规则：ETF 集合 = Category == 'Exchange Traded Products'（含 L&I）。"""
    if los_df.empty:
        return set()
    return set(los_df.loc[los_df["category"] == "Exchange Traded Products", "code"])


def reit_set(los_df: pd.DataFrame) -> set[str]:
    if los_df.empty:
        return set()
    return set(
        los_df.loc[los_df["category"] == "Real Estate Investment Trusts", "code"]
    )
