"""SFC 周度须申报淡仓 CSV 客户端（权威独占，源验证 §4）。

2026-09 SFC 网站改版：CSV 路径按报告期（position_date）组织（旧规则按公布日
= 报告期+7 天的周五，已 302→/404 全部失效）。未公布/缺失文件返回 302 跟随到
200 text/html 的 404 页，必须先验载荷再解析。

PIT 铁律：available_at = published_at（响应 Last-Modified）；header 不可得时
退化为 first_observed_at；绝不按 position_date + 固定天数倒推。
"""

from __future__ import annotations

import email.utils
import io
import logging

import pandas as pd

from flow_dashboard.config import HKEX_HEADERS
from flow_dashboard.data.hk_short import http_client

log = logging.getLogger(__name__)

URL_TMPL = (
    "https://www.sfc.hk/-/media/EN/pdf/spr/{y}/{m:02d}/{d:02d}/"
    "Short_Position_Reporting_Aggregated_Data_{pos:%Y%m%d}.csv"
)

_RENAME = {
    "Date": "report_date",
    "Stock Code": "code_raw",
    "Stock Name": "name",
    "Aggregated Reportable Short Positions (Shares)": "short_shares",
    "Aggregated Reportable Short Positions (HK$)": "short_amount_hkd",
}


def sfc_url_for(position_date) -> str:
    """报告期确定的唯一 URL（改版后路径日期 = position_date 本身）。"""
    pos = pd.Timestamp(position_date)
    return URL_TMPL.format(y=pos.year, m=pos.month, d=pos.day, pos=pos)


def _parse_last_modified(value: str | None) -> pd.Timestamp | None:
    if not value:
        return None
    dt = email.utils.parsedate_to_datetime(value)  # tz-aware (UTC)
    return pd.Timestamp(dt).tz_convert("Asia/Shanghai")


def parse_sfc_csv(content: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(content))
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns=_RENAME)
    df["code"] = df["code_raw"].astype(int).astype(str).str.zfill(5)
    df["position_date"] = pd.to_datetime(df["report_date"], format="%d/%m/%Y")
    return df[["code", "name", "position_date", "short_shares", "short_amount_hkd"]]


def _looks_like_sfc_csv(resp) -> bool:
    """302→HTML 404 页（最终 200 text/html）不是数据：验 Content-Type 与首行。"""
    ctype = (resp.headers.get("Content-Type") or "").lower()
    if "html" in ctype:
        return False
    return resp.content.lstrip().startswith(b"Date")


def fetch_sfc_week(position_date, *, fetched_at: pd.Timestamp) -> pd.DataFrame | None:
    """抓取某 position_date 一期报告；404/未公布（含 HTML 404 页）→ None。"""
    resp = http_client.try_get(sfc_url_for(position_date), headers=HKEX_HEADERS, timeout=120)
    if resp is None or not _looks_like_sfc_csv(resp):
        return None
    df = parse_sfc_csv(resp.content)
    published_at = _parse_last_modified(resp.headers.get("Last-Modified"))
    available_at = published_at if published_at is not None else fetched_at
    df["published_at"] = pd.Series(
        [published_at if published_at is not None else pd.NaT] * len(df),
        dtype="datetime64[ns, Asia/Shanghai]",
    )
    df["first_observed_at"] = fetched_at
    df["available_at"] = available_at
    df["source_date"] = pd.Timestamp(position_date)
    df["fetched_at"] = fetched_at
    df["source"] = "sfc"
    df["source_version"] = "sfc_spr_csv_v2"
    return df
