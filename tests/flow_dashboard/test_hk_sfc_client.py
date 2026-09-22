"""sfc_client：新 URL 规则、HTML 404 防御、Last-Modified→published_at、CSV 解析。

2026-09 SFC 网站改版：CSV 路径按报告期（position_date）组织，不再按公布日；
未公布/缺失文件的请求 302 → HTML 404 页（requests 跟随后最终 200 text/html）。
"""

import pandas as pd

from flow_dashboard.data.hk_short import sfc_client

CSV_BODY = (
    "Date,Stock Code,Stock Name,Aggregated Reportable Short Positions (Shares),"
    "Aggregated Reportable Short Positions (HK$)\n"
    "11/09/2026,1,CKH HOLDINGS,48162045,3315956798\n"
    "11/09/2026,700,TENCENT,91234567,28738234567\n"
)

HTML_404_BODY = b"<!DOCTYPE html>\n<html><head><title>404 | SFC</title></head></html>"


class _Resp:
    def __init__(self, content, last_modified=None, content_type="text/plain"):
        self.status_code = 200
        self.content = content
        self.headers = {"Content-Type": content_type}
        if last_modified:
            self.headers["Last-Modified"] = last_modified


def test_sfc_url_uses_position_date_path():
    # 改版后路径 = 报告期本身（旧规则为公布日 = 报告期+7 天的周五）
    assert sfc_client.sfc_url_for(pd.Timestamp("2026-09-11")) == (
        "https://www.sfc.hk/-/media/EN/pdf/spr/2026/09/11/"
        "Short_Position_Reporting_Aggregated_Data_20260911.csv"
    )


def test_fetch_sfc_week_parses_and_stamps(monkeypatch):
    seen = {}

    def fake_try_get(url, headers=None, **k):
        seen["url"] = url
        return _Resp(CSV_BODY.encode(), "Fri, 18 Sep 2026 07:41:00 GMT")

    monkeypatch.setattr(sfc_client.http_client, "try_get", fake_try_get)
    df = sfc_client.fetch_sfc_week(
        pd.Timestamp("2026-09-11"),
        fetched_at=pd.Timestamp("2026-09-18 18:45", tz="Asia/Shanghai"),
    )
    assert "2026/09/11" in seen["url"]  # 单一确定性 URL，无需候选探测
    assert len(df) == 2
    r = df[df["code"] == "00700"].iloc[0]
    assert r["short_shares"] == 91234567
    assert r["short_amount_hkd"] == 28738234567.0
    assert r["position_date"] == pd.Timestamp("2026-09-11")
    assert r["name"] == "TENCENT"
    # published_at 来自 Last-Modified（UTC → tz-aware）
    assert r["published_at"] == pd.Timestamp("2026-09-18 15:41:00", tz="Asia/Shanghai")
    assert r["available_at"] == r["published_at"]


def test_fetch_sfc_week_returns_none_when_404(monkeypatch):
    monkeypatch.setattr(
        sfc_client.http_client, "try_get", lambda url, headers=None, **k: None
    )
    out = sfc_client.fetch_sfc_week(
        pd.Timestamp("2026-12-25"),
        fetched_at=pd.Timestamp("2027-01-02 18:45", tz="Asia/Shanghai"),
    )
    assert out is None  # 假日周无报告（源验证 §4）


def test_fetch_sfc_week_html_404_returns_none(monkeypatch):
    """改版后未公布文件 → 302 跟随到 200 text/html 的 404 页：必须判 None，不得进入解析。"""
    monkeypatch.setattr(
        sfc_client.http_client,
        "try_get",
        lambda url, headers=None, **k: _Resp(HTML_404_BODY, content_type="text/html"),
    )
    out = sfc_client.fetch_sfc_week(
        pd.Timestamp("2026-09-18"),  # 报告期 09-18 应于 09-25 公布，尚未存在
        fetched_at=pd.Timestamp("2026-09-22 18:45", tz="Asia/Shanghai"),
    )
    assert out is None


def test_fetch_sfc_week_missing_last_modified_falls_back(monkeypatch):
    """无 Last-Modified 头 → published_at=NaT（tz-aware 列）、available_at 退化为 fetched_at。"""
    monkeypatch.setattr(
        sfc_client.http_client,
        "try_get",
        lambda url, headers=None, **k: _Resp(CSV_BODY.encode()),
    )
    fetched = pd.Timestamp("2026-09-21 18:45", tz="Asia/Shanghai")
    df = sfc_client.fetch_sfc_week(pd.Timestamp("2026-09-11"), fetched_at=fetched)
    assert str(df["published_at"].dtype) == "datetime64[ns, Asia/Shanghai]"
    assert df["published_at"].isna().all()
    assert (df["available_at"] == fetched).all()
