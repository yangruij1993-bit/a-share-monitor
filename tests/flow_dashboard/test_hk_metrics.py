"""hk_short_metrics：强度/分位/方向/聚合，边界=不足观测与除零返回 None。"""

import pandas as pd
import pytest

from flow_dashboard.indicators import hk_short_metrics as mx


def test_daily_intensity_excludes_today():
    s = pd.Series([10.0] * 20 + [50.0])  # 前 20 均值 10，当日 50
    assert mx.daily_intensity(s, window=20) == pytest.approx(5.0)
    assert mx.daily_intensity(pd.Series([1.0, 2.0]), window=20) is None  # 观测不足
    assert (
        mx.daily_intensity(pd.Series([0.0] * 20 + [5.0]), window=20) is None
    )  # 分母 0


def test_weekly_intensity_non_overlapping_windows():
    s = pd.Series(range(1, 71), dtype=float)  # 1..70
    # recent = 66..70 = 340；此前 12 个非重叠窗口 = 6..65，均值 177.5
    assert mx.weekly_intensity(s) == pytest.approx(340.0 / 177.5)
    assert mx.weekly_intensity(pd.Series(range(1, 61), dtype=float)) is None  # <65
    s65 = pd.Series(
        range(1, 66), dtype=float
    )  # len==65 恰好可用：recent 315，先验均值 152.5
    assert mx.weekly_intensity(s65) == pytest.approx(315.0 / 152.5)


def test_percentile_rank_min_obs_and_bounds():
    s = pd.Series(list(range(1, 21)) + [21.0])  # 前 20 个观测 1..20
    assert mx.percentile_rank(s, window=60, min_obs=20) == pytest.approx(100.0)
    s0 = pd.Series(list(range(1, 21)) + [0.5])
    assert mx.percentile_rank(s0, window=60, min_obs=20) == pytest.approx(0.0)
    assert mx.percentile_rank(pd.Series([1.0, 2.0])) is None  # <min_obs+1


def test_percentile_rank_tie_semantics():
    tie_max = pd.Series([1.0] * 20 + [1.0])  # 今日=历史值 → 严格小于计次 → <100%
    assert mx.percentile_rank(tie_max, window=60, min_obs=20) == pytest.approx(0.0)
    tie_mid = pd.Series([1.0] * 10 + [2.0] * 10 + [2.0])  # 一半严格小于 → 50%
    assert mx.percentile_rank(tie_mid, window=60, min_obs=20) == pytest.approx(50.0)


def test_ret_n_and_price_direction():
    close = pd.Series([100.0, 101, 102, 103, 104, 105.0])  # +5%
    assert mx.ret_n(close, n=5) == pytest.approx(0.05)
    assert mx.ret_n(pd.Series([100.0, 101]), n=5) is None
    assert mx.price_direction(0.012, 0.010) == "up"  # 等权 +1.1% >= 1%
    assert mx.price_direction(-0.012, -0.010) == "down"
    assert mx.price_direction(0.005, -0.005) == "neutral"  # 等权 0
    assert mx.price_direction(0.012, -0.005) == "neutral"  # 等权 +0.35% < 1%
    assert mx.price_direction(None, 0.010) == "up"  # 单指数可用即判
    assert mx.price_direction(None, None) == "unavailable"


def test_market_daily_aggregate_full_days_only():
    em = pd.DataFrame(
        {
            "code": ["00700", "09988"] * 2,
            "trade_date": [pd.Timestamp("2026-09-17")] * 2
            + [pd.Timestamp("2026-09-18")] * 2,
            "short_amount": [3e7, 2e7, 6e7, 2e7],
            "turnover": [3e9, 2e9, 4e9, 2e9],
        }
    )
    agg = mx.market_daily_aggregate(em, full_days=[pd.Timestamp("2026-09-17")])
    assert len(agg) == 1  # 09-18 非 full 日被剔除
    r = agg.iloc[0]
    assert r["short_amount"] == pytest.approx(5e7)
    assert r["ssr"] == pytest.approx(5e7 / 5e9)
    assert r["n_secs"] == 2


def test_etf_interference_share():
    hkex = pd.DataFrame(
        {
            "code": ["00700", "02800", "03033"],
            "trade_date": [pd.Timestamp("2026-09-18")] * 3,
            "short_amount": [6.0e9, 3.0e9, 1.0e9],
        }
    )
    out = mx.etf_interference_share(
        hkex, etf_codes={"02800", "03033"}, trade_date="2026-09-18"
    )
    assert out == pytest.approx(4.0e9 / 10.0e9)
    assert mx.etf_interference_share(hkex, {"02800"}, "2026-09-17") is None  # 无当日行


def test_stock_daily_recomputes_ssr():
    em = pd.DataFrame(
        {
            "code": ["00700", "00700"],
            "trade_date": [pd.Timestamp("2026-09-17"), pd.Timestamp("2026-09-18")],
            "short_amount": [1.0e8, 2.0e8],
            "turnover": [2.0e9, 4.0e9],
            "short_shares": [100.0, 200.0],
            "short_avg_price": [100.0, 100.0],
            "ssr_pct": [99.0, 99.0],
            "source_date": ["a", "b"],
            "name": ["腾讯控股", "腾讯控股"],
        }
    )
    df = mx.stock_daily(em, "0700.HK")
    assert list(df["ssr"]) == [0.05, 0.05]  # 金额口径重算，弃用源 ssr_pct
    assert mx.stock_daily(em, "00005.HK").empty


def _sfc_two_weeks():
    return pd.DataFrame(
        {
            "code": ["00001", "00700"] * 2,
            "position_date": [pd.Timestamp("2026-09-04")] * 2
            + [pd.Timestamp("2026-09-11")] * 2,
            "short_shares": [100.0, 50.0, 200.0, 50.0],
            "short_amount_hkd": [1000.0, 1000.0, 2000.0, 1000.0],
        }
    )


def _shares():
    return pd.DataFrame({"code": ["00001", "00700"], "total_shares": [1000.0, 1000.0]})


def test_sfc_stock_metrics_delta_bp():
    out = mx.sfc_stock_metrics(_sfc_two_weeks(), "00001.HK", total_shares=1000.0)
    assert out["available"] is True
    assert out["delta_bp"] == pytest.approx((0.2 - 0.1) * 1e4)  # +100bp → 加仓
    assert out["latest_pd"] == pd.Timestamp("2026-09-11")
    # 00700 淡仓不变 → 0bp
    out2 = mx.sfc_stock_metrics(_sfc_two_weeks(), "0700.HK", total_shares=1000.0)
    assert out2["delta_bp"] == pytest.approx(0.0)
    # 只有一期 → unavailable
    assert (
        mx.sfc_stock_metrics(_sfc_two_weeks().iloc[:2], "00001.HK", 1000.0)["available"]
        is False
    )


def test_sfc_stock_metrics_corp_action_suspect():
    df = _sfc_two_weeks()
    df.loc[df["position_date"] == pd.Timestamp("2026-09-11"), "short_amount_hkd"] = [
        5000.0,
        2500.0,
    ]
    # 00001 隐含价 10 → 25（跳变 150% > 20%）→ 拆股嫌疑，保守 unavailable
    out = mx.sfc_stock_metrics(df, "00001.HK", total_shares=1000.0)
    assert out["available"] is False


def test_sfc_stock_metrics_four_week_delta():
    rows = []
    for i, wk in enumerate(pd.date_range("2026-08-14", periods=5, freq="7D")):
        rows.append(
            {
                "code": "00001",
                "position_date": wk.normalize(),
                "short_shares": 100.0 + i * 10.0,
                "short_amount_hkd": (100.0 + i * 10.0) * 10.0,
            }
        )
    out = mx.sfc_stock_metrics(pd.DataFrame(rows), "00001.HK", total_shares=10000.0)
    assert out["available"] is True
    # 周环比：140 vs 130 → +10bp；4 周斜率（4 周差分）：140 vs 100 → +40bp
    assert out["delta_bp"] == pytest.approx(10.0)
    assert out["delta_4w_bp"] == pytest.approx(40.0)
    # 不足 5 期 → delta_4w_bp 为 None（设计 §6.1 斜率证据 unavailable）
    out2 = mx.sfc_stock_metrics(_sfc_two_weeks(), "00001.HK", total_shares=1000.0)
    assert out2["available"] is True and out2.get("delta_4w_bp") is None


def test_sfc_stock_metrics_nan_total_shares_unavailable():
    out = mx.sfc_stock_metrics(_sfc_two_weeks(), "00001.HK", total_shares=float("nan"))
    assert out["available"] is False


def test_sfc_market_metrics_ratio_and_breadth():
    out = mx.sfc_market_metrics(
        _sfc_two_weeks(), _shares(), min_comparable=2, min_coverage=0.5
    )
    assert out["available"] is True
    # t0: (1000+1000)/(10000+20000)=0.0667; t1: (2000+1000)/30000=0.1 → +333bp
    assert out["delta_bps"] == pytest.approx((0.1 - 2.0 / 30.0) * 1e4)
    assert out["breadth"] == pytest.approx(0.5)  # 00001 增、00700 平（不增）
    assert out["n_comparable"] == 2


def test_sfc_market_metrics_gates():
    # 可比证券不足 → unavailable
    out = mx.sfc_market_metrics(
        _sfc_two_weeks(), _shares(), min_comparable=100, min_coverage=0.5
    )
    assert out["available"] is False and out["n_comparable"] == 2
    # 只有一期 → unavailable
    out2 = mx.sfc_market_metrics(
        _sfc_two_weeks().iloc[:2], _shares(), min_comparable=2, min_coverage=0.5
    )
    assert out2["available"] is False
