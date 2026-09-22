"""sfc_client：候选 URL 探测、Last-Modified→published_at、CSV 解析。"""
import pandas as pd

from flow_dashboard.data.hk_short import sfc_client

CSV_BODY = (
    "Date,Stock Code,Stock Name,Aggregated Reportable Short Positions (Shares),"
    "Aggregated Reportable Short Positions (HK$)\n"
    "11/09/2026,1,CKH HOLDINGS,48162045,3315956798\n"
    "11/09/2026,700,TENCENT,91234567,28738234567\n"
)


class _Resp:
    def __init__(self, content, last_modified=None):
        self.status_code = 200
        self.content = content
        self.headers = {"Last-Modified": last_modified} if last_modified else {}


def test_candidate_pub_dates_centered_on_plus7():
    cands = sfc_client.candidate_pub_dates(pd.Timestamp("2026-09-11"))
    assert cands[0] == pd.Timestamp("2026-09-18")  # 正常周五公布
    assert all(c.weekday() == 4 for c in cands[:1])
    assert len(cands) >= 6                          # 假日周漂移余量


def test_fetch_sfc_week_parses_and_stamps(monkeypatch):
    state = {"n": 0}

    def fake_try_get(url, headers=None, **k):
        state["n"] += 1
        if "2026/09/18" in url:  # 首个候选命中
            return _Resp(CSV_BODY.encode(), "Fri, 18 Sep 2026 07:41:00 GMT")
        return None

    monkeypatch.setattr(sfc_client.http_client, "try_get", fake_try_get)
    df = sfc_client.fetch_sfc_week(
        pd.Timestamp("2026-09-11"),
        fetched_at=pd.Timestamp("2026-09-18 18:45", tz="Asia/Shanghai"))
    assert state["n"] == 1
    assert len(df) == 2
    r = df[df["code"] == "00700"].iloc[0]
    assert r["short_shares"] == 91234567
    assert r["short_amount_hkd"] == 28738234567.0
    assert r["position_date"] == pd.Timestamp("2026-09-11")
    assert r["name"] == "TENCENT"
    # published_at 来自 Last-Modified（UTC → tz-aware）
    assert r["published_at"] == pd.Timestamp("2026-09-18 15:41:00", tz="Asia/Shanghai")
    assert r["available_at"] == r["published_at"]


def test_fetch_sfc_week_returns_none_when_all_404(monkeypatch):
    monkeypatch.setattr(sfc_client.http_client, "try_get",
                        lambda url, headers=None, **k: None)
    out = sfc_client.fetch_sfc_week(
        pd.Timestamp("2026-12-25"),
        fetched_at=pd.Timestamp("2027-01-02 18:45", tz="Asia/Shanghai"))
    assert out is None  # 假日周无报告（源验证 §4）


def test_fetch_sfc_week_missing_last_modified_falls_back(monkeypatch):
    """无 Last-Modified 头 → published_at=NaT（tz-aware 列）、available_at 退化为 fetched_at。"""
    monkeypatch.setattr(
        sfc_client.http_client, "try_get",
        lambda url, headers=None, **k: _Resp(CSV_BODY.encode()))
    fetched = pd.Timestamp("2026-09-21 18:45", tz="Asia/Shanghai")
    df = sfc_client.fetch_sfc_week(pd.Timestamp("2026-09-11"), fetched_at=fetched)
    assert str(df["published_at"].dtype) == "datetime64[ns, Asia/Shanghai]"
    assert df["published_at"].isna().all()
    assert (df["available_at"] == fetched).all()
