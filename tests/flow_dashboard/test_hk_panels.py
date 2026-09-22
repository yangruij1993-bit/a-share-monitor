"""panels_hk_short：空缓存横幅、结论卡、11 列明细、稀疏 OI、TOP20、ETF 回退。"""

import pandas as pd

from flow_dashboard.data.hk_short import loaders
from flow_dashboard.render.panels_hk_short import render_hk_short_body

AS_OF = pd.Timestamp("2026-09-18 19:00", tz="Asia/Shanghai")
AVAIL_EM = pd.Timestamp("2026-09-18 16:10", tz="Asia/Shanghai")


def _audit(df, avail=AVAIL_EM):
    df = df.copy()
    df["source_date"] = (
        pd.to_datetime(df["trade_date"])
        if "trade_date" in df
        else AS_OF.tz_localize(None)
    )
    df["first_observed_at"] = AS_OF
    df["available_at"] = avail
    df["fetched_at"] = AS_OF
    df["source"] = "test"
    df["source_version"] = "v1"
    df["quality_flags"] = ""
    return df


def _build_cache(tmp_path):
    days = [
        pd.Timestamp(d)
        for d in ("2026-09-11", "2026-09-16", "2026-09-17", "2026-09-18")
    ]
    em_rows = []
    for d in days:
        em_rows.append(
            {
                "code": "00700",
                "name": "腾讯控股",
                "trade_date": d,
                "short_shares": 1e6,
                "short_avg_price": 300.0,
                "short_amount": 3e8,
                "turnover": 3e9,
                "ssr_pct": 10.0,
            }
        )
        em_rows.append(
            {
                "code": "09988",
                "name": "阿里巴巴-W",
                "trade_date": d,
                "short_shares": 1e6,
                "short_avg_price": 100.0,
                "short_amount": 1e8,
                "turnover": 1e9,
                "ssr_pct": 10.0,
            }
        )
    loaders._write(_audit(pd.DataFrame(em_rows)), tmp_path / loaders.EM_FILE)
    loaders._write(
        pd.DataFrame({"trade_date": days, "coverage": ["full"] * 4}),
        tmp_path / loaders.DAYS_FILE,
    )

    kl = []
    for secid, closes in (
        ("100.HSI", [100, 101, 102, 103, 104, 105]),
        ("124.HSTECH", [100, 100, 100, 100, 100, 100]),
        ("116.00700", [300, 301, 302, 303, 304, 305]),
    ):
        for i, c in enumerate(closes):
            kl.append(
                {
                    "secid": secid,
                    "trade_date": pd.Timestamp("2026-09-09") + pd.Timedelta(days=i + 1),
                    "open": c,
                    "close": c,
                    "high": c,
                    "low": c,
                    "volume": 1e6,
                    "amount": 1e8,
                }
            )
    loaders._write(_audit(pd.DataFrame(kl)), tmp_path / loaders.KLINE_FILE)

    hq = []
    for d in days[1:]:
        hq.append(
            {
                "code": "02800",
                "name": "盈富基金",
                "trade_date": d,
                "short_shares": 3e5,
                "short_amount": 3e9,
                "total_shares_traded": 1e7,
                "turnover": 2e10,
            }
        )
    hq.append(
        {
            "code": "00700",
            "name": "腾讯控股",
            "trade_date": pd.Timestamp("2026-09-18"),
            "short_shares": 1e6,
            "short_amount": 6e9,
            "total_shares_traded": 1e7,
            "turnover": 3e9,
        }
    )
    loaders._write(_audit(pd.DataFrame(hq)), tmp_path / loaders.HKEX_FILE)

    los = pd.DataFrame(
        {
            "code": ["02800"],
            "name": ["盈富基金"],
            "category": ["Exchange Traded Products"],
            "sub_category": ["ETF"],
        }
    )
    los = los.assign(effective_date=pd.Timestamp("2026-09-18"))
    loaders._write(_audit(los), tmp_path / loaders.LOS_FILE)

    sh = pd.DataFrame({"code": ["00700", "02800"], "total_shares": [9.095e9, 1.0e10]})
    loaders._write(_audit(sh), tmp_path / loaders.SHARES_FILE)

    sfc_rows = []
    for pos, pub in (
        (
            pd.Timestamp("2026-09-04"),
            pd.Timestamp("2026-09-11 15:41", tz="Asia/Shanghai"),
        ),
        (
            pd.Timestamp("2026-09-11"),
            pd.Timestamp("2026-09-18 15:41", tz="Asia/Shanghai"),
        ),
    ):
        sfc_rows.append(
            {
                "code": "00001",
                "name": "CKH",
                "position_date": pos,
                "short_shares": 1e6,
                "short_amount_hkd": 1e8,
                "published_at": pub,
                "first_observed_at": AS_OF,
                "available_at": pub,
                "source_date": pos,
                "fetched_at": AS_OF,
                "source": "sfc",
                "source_version": "v1",
            }
        )
        # 00700 淡仓 0.001 → 0.002 of 9.095e9 = +10bp；金额按同比例放大，
        # 隐含价（金额/股数）保持 16.49 不变，避免误触公司行动嫌疑过滤
        sfc_rows.append(
            {
                "code": "00700",
                "name": "TENCENT",
                "position_date": pos,
                "short_shares": (9.095e9 * 0.001)
                if pos == pd.Timestamp("2026-09-04")
                else (9.095e9 * 0.002),
                "short_amount_hkd": (1.5e8)
                if pos == pd.Timestamp("2026-09-04")
                else (3e8),
                "published_at": pub,
                "first_observed_at": AS_OF,
                "available_at": pub,
                "source_date": pos,
                "fetched_at": AS_OF,
                "source": "sfc",
                "source_version": "v1",
            }
        )
    loaders._write(pd.DataFrame(sfc_rows), tmp_path / loaders.SFC_FILE)


def test_empty_cache_returns_banner_and_none_date(tmp_path):
    html, hk_date = render_hk_short_body(as_of=AS_OF, cache_dir=tmp_path)
    assert hk_date is None
    assert "数据待更新" in html


def test_render_smoke_full_cache(tmp_path):
    _build_cache(tmp_path)
    html, hk_date = render_hk_short_body(as_of=AS_OF, cache_dir=tmp_path)
    assert hk_date == "2026-09-18"
    # 结论卡 + 指数对冲注（ETF 3e9/9e9 = 33% >= 30%）
    assert "市场结论" in html
    assert "暂时无法确认" in html  # SFC 市场可比集合不足 100 → oi unavailable
    assert "指数对冲" in html
    assert "·SFC待确认" not in html  # 宽限期内不加后缀
    # 市场总览图 + KPI 副指标标注股票口径
    assert "股票口径" in html


def test_watch_table_11_cols_sparse_oi_and_etf_fallback(tmp_path):
    _build_cache(tmp_path)
    html, _ = render_hk_short_body(as_of=AS_OF, cache_dir=tmp_path)
    # 11 列表头
    assert "未平仓卖空期末值·股数" in html
    assert "期末未平仓/总股本%" in html
    # 00700：SFC 09-11 有 OI（0.002*9.095e9 = 18,190,000），且只出现一次
    assert html.count("18,190,000") == 1
    # 00700 状态标签：oi=up（+10bp）+ 价涨 → 多空分歧扩大
    assert "多空分歧扩大" in html
    # ETF 2800 走 HKEX 回退，表格照常渲染
    assert "盈富基金" in html


def test_top20_renders_with_insufficient_sample(tmp_path):
    _build_cache(tmp_path)
    html, _ = render_hk_short_body(as_of=AS_OF, cache_dir=tmp_path)
    assert "TOP20" in html
    assert "样本不足" in html  # 历史仅 4 日 < 20 → 不伪造分位
    assert "腾讯控股" in html
