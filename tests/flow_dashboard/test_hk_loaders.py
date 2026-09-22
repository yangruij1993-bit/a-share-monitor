"""hk_short loaders：增量合并、PIT 过滤、restated 覆盖、SFC 负缓存。"""
import pandas as pd

from flow_dashboard.data.hk_short import loaders
from flow_dashboard.data.hk_short.loaders import (
    load_em_sellshort, load_em_days_covered, load_hkex_dayquot,
    load_sfc_weekly, load_hk_kline, load_total_shares,
)

FETCHED = pd.Timestamp("2026-09-18 19:00:00", tz="Asia/Shanghai")


def _em_day(d, n=2):
    return pd.DataFrame({
        "code": ["00700", "09988"][:n],
        "name": ["腾讯控股", "阿里巴巴-W"][:n],
        "trade_date": pd.Timestamp(d),
        "short_shares": [100.0, 200.0][:n],
        "short_avg_price": [300.0, 100.0][:n],
        "short_amount": [3e7, 2e7][:n],
        "turnover": [3e9, 2e9][:n],
        "ssr_pct": [1.0, 1.0][:n],
        "source_date": [pd.Timestamp(d)] * n,
    })


def test_em_full_day_fetch_marks_full_and_pit(tmp_path, monkeypatch):
    calls = []

    def fake_day(d):
        calls.append(str(pd.Timestamp(d).date()))
        return _em_day(d)

    monkeypatch.setattr(loaders.em_client, "fetch_sellshort_day", fake_day)
    out = load_em_sellshort(as_of=FETCHED, start="2026-09-16", cache_dir=tmp_path)
    assert calls == ["2026-09-16", "2026-09-17", "2026-09-18"]  # 全是交易日
    days = load_em_days_covered(as_of=FETCHED, cache_dir=tmp_path)
    assert [str(d.date()) for d in days] == ["2026-09-16", "2026-09-17", "2026-09-18"]
    assert out["trade_date"].max() == pd.Timestamp("2026-09-18")  # 19:00 > 16:10 可见
    early = load_em_sellshort(
        as_of=pd.Timestamp("2026-09-18 10:00", tz="Asia/Shanghai"),
        allow_fetch=False, cache_dir=tmp_path)
    assert early["trade_date"].max() == pd.Timestamp("2026-09-17")  # PIT 截断当日


def test_em_no_refetch_when_fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(loaders.em_client, "fetch_sellshort_day", lambda d: _em_day(d))
    # 先把默认窗口（expected-14d = 09-04）补满 full
    load_em_sellshort(as_of=FETCHED, start="2026-09-04", cache_dir=tmp_path)

    def boom(d):
        raise AssertionError("covered full day must not be refetched")

    monkeypatch.setattr(loaders.em_client, "fetch_sellshort_day", boom)
    out = load_em_sellshort(as_of=FETCHED, cache_dir=tmp_path)  # 窗口内全部 full → 零抓取
    assert (out["trade_date"] == pd.Timestamp("2026-09-18")).any()


def test_em_stock_range_marks_partial(tmp_path, monkeypatch):
    monkeypatch.setattr(loaders.em_client, "fetch_sellshort_day",
                        lambda d: _em_day(d, n=1))
    load_em_sellshort(as_of=FETCHED, start="2026-09-18", cache_dir=tmp_path)  # 18 日 full

    got = {}

    def fake_stock(code, s, e):
        got["code"] = code
        df = _em_day("2026-09-17", n=1)
        df["code"] = code
        return df

    monkeypatch.setattr(loaders.em_client, "fetch_sellshort_stock", fake_stock)
    load_em_sellshort(as_of=FETCHED, codes=["0700.HK"],
                      start="2026-09-10", cache_dir=tmp_path)
    assert got["code"] == "00700"  # '0700.HK' → 5 位数字代码
    days = load_em_days_covered(as_of=FETCHED, cache_dir=tmp_path)
    assert [str(d.date()) for d in days] == ["2026-09-18"]  # partial 日绝不入 full 集合
    cached = load_em_sellshort(as_of=FETCHED, allow_fetch=False, cache_dir=tmp_path)
    assert ((cached["code"] == "00700")
            & (cached["trade_date"] == pd.Timestamp("2026-09-17"))).any()


def test_hkex_restated_override(tmp_path, monkeypatch):
    def fake_dayquot(d):
        daily = pd.DataFrame({
            "code": ["00001"], "name": ["CKH"],
            "trade_date": [pd.Timestamp("2026-09-18")],
            "short_shares": [1090000.0], "short_amount": [74273675.0],
            "total_shares_traded": [8613270.0], "turnover": [640508607.0],
        })
        adjusted = daily.copy()
        adjusted["trade_date"] = pd.Timestamp("2026-09-17")
        adjusted["short_shares"] = [1100000.0]  # T-1 修正值
        return pd.concat([daily, adjusted], ignore_index=True)

    monkeypatch.setattr(loaders.hkex_client, "fetch_dayquot", fake_dayquot)
    out = load_hkex_dayquot(as_of=FETCHED, start="2026-09-18", cache_dir=tmp_path)
    r18 = out[(out["code"] == "00001")
              & (out["trade_date"] == pd.Timestamp("2026-09-18"))].iloc[0]
    r17 = out[(out["code"] == "00001")
              & (out["trade_date"] == pd.Timestamp("2026-09-17"))].iloc[0]
    assert r18["quality_flags"] == ""
    assert r17["quality_flags"] == "restated"
    # restated 行 available_at = 公布日 17:30（非数据日）——17 日 18:00 还看不到修正
    assert r17["available_at"] == pd.Timestamp("2026-09-18 17:30", tz="Asia/Shanghai")
    early = load_hkex_dayquot(
        as_of=pd.Timestamp("2026-09-17 18:00", tz="Asia/Shanghai"),
        allow_fetch=False, cache_dir=tmp_path)
    assert early.empty


def _sfc_one_week():
    pos = pd.Timestamp("2026-09-11")
    pub = pd.Timestamp("2026-09-18 15:41", tz="Asia/Shanghai")
    return pd.DataFrame({
        "code": ["00700"], "name": ["TENCENT"], "position_date": [pos],
        "short_shares": [9.1e7], "short_amount_hkd": [2.87e10],
        "published_at": [pub], "first_observed_at": [FETCHED],
        "available_at": [pub], "source_date": [pos], "fetched_at": [FETCHED],
        "source": ["sfc"], "source_version": ["sfc_spr_csv_v1"],
    })


def test_sfc_skip_cached_and_negative_cache(tmp_path, monkeypatch):
    loaders._write(_sfc_one_week(), tmp_path / loaders.SFC_FILE)
    probed = []

    def fake_fetch(pos_date, fetched_at=None):
        probed.append(pd.Timestamp(pos_date))
        return None  # 全候选 404：假日周/未公布

    monkeypatch.setattr(loaders.sfc_client, "fetch_sfc_week", fake_fetch)
    as_of = pd.Timestamp("2026-09-21 19:00", tz="Asia/Shanghai")
    out = load_sfc_weekly(as_of=as_of, weeks=3, cache_dir=tmp_path)
    # 09-21(周一) 的最近已完成周：09-18、09-11、09-04；09-11 已缓存不重抓
    assert set(probed) == {pd.Timestamp("2026-09-18"), pd.Timestamp("2026-09-04")}
    assert (out["position_date"] == pd.Timestamp("2026-09-11")).any()
    probed.clear()
    load_sfc_weekly(as_of=as_of, weeks=3, cache_dir=tmp_path)
    assert probed == []  # 负缓存 14 天内不重试


def test_sfc_pit_visibility(tmp_path):
    loaders._write(_sfc_one_week(), tmp_path / loaders.SFC_FILE)
    before = load_sfc_weekly(
        as_of=pd.Timestamp("2026-09-18 15:00", tz="Asia/Shanghai"),
        allow_fetch=False, cache_dir=tmp_path)
    after = load_sfc_weekly(
        as_of=pd.Timestamp("2026-09-18 16:00", tz="Asia/Shanghai"),
        allow_fetch=False, cache_dir=tmp_path)
    assert before.empty and not after.empty  # published_at 是 PIT 唯一依据


def test_kline_incremental(tmp_path, monkeypatch):
    cached = pd.DataFrame({
        "secid": ["100.HSI"], "trade_date": [pd.Timestamp("2026-09-17")],
        "open": [1.0], "close": [1.0], "high": [1.0], "low": [1.0],
        "volume": [1.0], "amount": [1.0],
        "source_date": [pd.Timestamp("2026-09-17")],
        "first_observed_at": [FETCHED],
        "available_at": [pd.Timestamp("2026-09-17 16:10", tz="Asia/Shanghai")],
        "fetched_at": [FETCHED], "source": ["eastmoney"],
        "source_version": ["em_kline_v1"], "quality_flags": [""],
    })
    loaders._write(cached, tmp_path / loaders.KLINE_FILE)
    calls = []

    def fake_kline(secid, beg, end, now=None):
        calls.append((str(pd.Timestamp(beg).date()), str(pd.Timestamp(end).date())))
        return pd.DataFrame({
            "secid": [secid], "trade_date": [pd.Timestamp("2026-09-18")],
            "open": [2.0], "close": [2.0], "high": [2.0], "low": [2.0],
            "volume": [2.0], "amount": [2.0],
        })

    monkeypatch.setattr(loaders.em_client, "fetch_kline", fake_kline)
    out = load_hk_kline(as_of=FETCHED, secids=["100.HSI"], cache_dir=tmp_path)
    assert calls == [("2026-09-18", "2026-09-18")]  # 只补增量
    assert set(out["trade_date"]) == {pd.Timestamp("2026-09-17"),
                                      pd.Timestamp("2026-09-18")}


def test_total_shares_snapshot_no_refetch(tmp_path, monkeypatch):
    calls = {"n": 0}

    def fake_f84(c):
        calls["n"] += 1
        return 9095085993

    monkeypatch.setattr(loaders.em_client, "fetch_total_shares", fake_f84)
    out = load_total_shares(as_of=FETCHED, codes=["0700.HK"], cache_dir=tmp_path)
    assert len(out) == 1 and out.iloc[0]["total_shares"] == 9095085993.0
    load_total_shares(as_of=FETCHED, codes=["0700.HK"], cache_dir=tmp_path)
    assert calls["n"] == 1  # 已有快照不重抓（refresh=True 才刷新）


def test_etf_master_weekly_refresh(tmp_path, monkeypatch):
    los = pd.DataFrame({
        "code": ["02800"], "name": ["TRACKER FUND"],
        "category": ["Exchange Traded Products"], "sub_category": ["ETF"],
    })
    calls = {"n": 0}

    def fake_los():
        calls["n"] += 1
        return los.copy(), "Updated as at 21/09/2026"

    monkeypatch.setattr(loaders.hkex_client, "fetch_list_of_securities", fake_los)
    df, eff = loaders.load_etf_master(as_of=FETCHED, cache_dir=tmp_path)
    assert calls["n"] == 1 and eff == pd.Timestamp("2026-09-21")
    assert set(df["code"]) == {"02800"}
    loaders.load_etf_master(as_of=FETCHED, cache_dir=tmp_path)
    assert calls["n"] == 1  # 7 天内不重抓
