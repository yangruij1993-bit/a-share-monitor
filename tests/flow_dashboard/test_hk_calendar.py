"""香港交易日历：周末/假日、宽限期、SFC position_date 枚举。"""
import pandas as pd

from flow_dashboard.data.hk_short import hk_calendar as cal


def test_weekend_and_holiday():
    assert not cal.is_hk_trading_day("2026-09-19")  # 周六
    assert not cal.is_hk_trading_day("2026-09-20")  # 周日
    assert not cal.is_hk_trading_day("2026-10-01")  # 国庆（HK 假日）
    assert not cal.is_hk_trading_day("2026-02-18")  # 农历新年
    assert cal.is_hk_trading_day("2026-09-18")      # 周五
    assert cal.is_hk_trading_day("2026-02-16")      # 新年假期前的周一


def test_latest_trading_day_on_or_before():
    # 周一 -> 上周五；假日 -> 前一交易日
    assert cal.latest_trading_day_on_or_before("2026-09-21") == pd.Timestamp("2026-09-18")
    assert cal.latest_trading_day_on_or_before("2026-10-01") == pd.Timestamp("2026-09-30")


def test_prev_trading_day():
    assert cal.prev_trading_day("2026-09-18") == pd.Timestamp("2026-09-17")
    assert cal.prev_trading_day("2026-02-17") == pd.Timestamp("2026-02-16")  # 跨农历假期


def test_next_trading_days_for_grace_period():
    # position_date=2026-09-11(周五) -> 后 5 个交易日 = 14,15,16,17,18
    days = cal.next_trk_days("2026-09-11", 5)
    assert [d.strftime("%m-%d") for d in days] == ["09-14", "09-15", "09-16", "09-17", "09-18"]


def test_grace_deadline_is_eod_of_5th_trading_day():
    d = cal.sfc_grace_deadline("2026-09-11")
    assert d == pd.Timestamp("2026-09-18 23:59:59")


def test_recent_sfc_position_dates():
    # 2026-09-21(周一) -> 最近一个已完成交易周的最后一个交易日是 09-18
    out = cal.recent_sfc_position_dates("2026-09-21", n=3)
    assert out[0] == pd.Timestamp("2026-09-18")
    assert out[1] == pd.Timestamp("2026-09-11")
    assert len(out) == 3
    # 周三 -> 本周五还没到，只能取上周五
    out2 = cal.recent_sfc_position_dates("2026-09-16", n=1)
    assert out2[0] == pd.Timestamp("2026-09-11")
