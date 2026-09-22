"""SFC 周度须申报淡仓 CSV 客户端（权威独占，源验证 §4）。

PIT 铁律：available_at = published_at（响应 Last-Modified）；header 不可得时
退化为 first_observed_at；绝不按 position_date + 固定天数倒推。
"""
from __future__ import annotations

import email.utils
import io
import logging
from datetime import timedelta

import pandas as pd

from flow_dashboard.config import HKEX_HEADERS
from flow_dashboard.data.hk_short import http_client

log = logging.getLogger(__name__)

URL_TMPL = ("https://www.sfc.hk/-/media/EN/pdf/spr/{y}/{m:02d}/{d:02d}/"
            "Short_Position_Reporting_Aggregated_Data_{pos:%Y%m%d}.csv")

_RENAME = {
    "Date": "report_date",
    "Stock Code": "code_raw",
    "Stock Name": "name",
    "Aggregated Reportable Short Positions (Shares)": "short_shares",
    "Aggregated Reportable Short Positions (HK$)": "short_amount_hkd",
}


def candidate_pub_dates(position_date) -> list[pd.Timestamp]:
    """正常公布日 = position_date+7（周五）；假日周向前后漂移，按可能性排序。"""
    base = pd.Timestamp(position_date) + pd.Timedelta(days=7)
    return [base + timedelta(days=o) for o in (0, 1, -1, 2, 3, -2, 4, 5)]


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


def fetch_sfc_week(position_date, *, fetched_at: pd.Timestamp) -> pd.DataFrame | None:
    """抓取某 position_date 一期报告；所有候选 404 → None（假日周/未公布）。"""
    for pub in candidate_pub_dates(position_date):
        url = URL_TMPL.format(y=pub.year, m=pub.month, d=pub.day,
                              pos=pd.Timestamp(position_date))
        resp = http_client.try_get(url, headers=HKEX_HEADERS, timeout=120)
        if resp is None:
            continue
        df = parse_sfc_csv(resp.content)
        published_at = _parse_last_modified(resp.headers.get("Last-Modified"))
        available_at = published_at if published_at is not None else fetched_at
        df["published_at"] = published_at
        df["first_observed_at"] = fetched_at
        df["available_at"] = available_at
        df["source_date"] = pd.Timestamp(position_date)
        df["fetched_at"] = fetched_at
        df["source"] = "sfc"
        df["source_version"] = "sfc_spr_csv_v1"
        return df
    return None
