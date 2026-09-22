"""港股数据源真实抓取冒烟测试（@live，--run-live 开启）。

行数基准来自 docs/港股沽空/source-validation.md（2026-09-18 实测）：
EM 单日 ~745 行；HKEX dayquot ~843 行；SFC 单期数百行；f84(00700)=9,095,085,993。
"""

import pandas as pd
import pytest

from flow_dashboard.config import HK_INDEX_SECIDS
from flow_dashboard.data.hk_short import em_client, hkex_client, sfc_client
from flow_dashboard.data.hk_short.hk_calendar import (
    latest_trading_day_on_or_before,
    recent_sfc_position_dates,
)

pytestmark = pytest.mark.live


def _now():
    return pd.Timestamp.now(tz="Asia/Shanghai")


def _last_trading_day():
    return latest_trading_day_on_or_before(
        _now().tz_localize(None) - pd.Timedelta(days=1)
    )


def test_live_em_sellshort_day():
    d = _last_trading_day()
    df = em_client.fetch_sellshort_day(d)
    assert len(df) > 600, f"EM 单日行数异常: {len(df)} @ {d.date()}"
    assert df["short_amount"].sum() > 1e10  # >100 亿港元量级


def test_live_hkex_dayquot_rows():
    d = _last_trading_day()
    df = hkex_client.fetch_dayquot(d)
    assert df is not None and len(df) > 0
    codes = df["code"].nunique()
    assert 700 <= codes <= 950, f"dayquot 证券数异常: {codes} @ {d.date()}"


def test_live_sfc_latest_week():
    pos = recent_sfc_position_dates(_now().tz_localize(None), n=1)[0]
    df = sfc_client.fetch_sfc_week(pos, fetched_at=_now())
    if df is not None:  # 假日周允许 None
        assert len(df) > 100
        assert df["published_at"].notna().all()


def test_live_kline_and_total_shares():
    d = _last_trading_day()
    k = em_client.fetch_kline(
        HK_INDEX_SECIDS["HSI"], d - pd.Timedelta(days=30), d, now=_now()
    )
    assert not k.empty and k["trade_date"].max() <= d
    assert em_client.fetch_total_shares("00700") == 9095085993


def test_live_list_of_securities():
    los, eff = hkex_client.fetch_list_of_securities()
    assert len(los) > 5000
    assert eff  # 生效日期非空（"Updated as at ..."）
    assert len(hkex_client.etf_set(los)) > 350  # ETP ~411
