# tests/flow_dashboard/data/test_load_margin_detail.py
"""个股两融明细 loader 测试。"""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from flow_dashboard.data.loaders import load_margin_detail


def _fake_margin_detail(trade_date: str) -> pd.DataFrame:
    ts = pd.Timestamp(trade_date)
    return pd.DataFrame([
        {"trade_date": ts, "ts_code": "000001.SZ",
         "rzye": 1e9, "rqye": 1e8, "rzmre": 1e8, "rqyl": 1e7},
        {"trade_date": ts, "ts_code": "600000.SH",
         "rzye": 2e9, "rqye": 2e8, "rzmre": 2e8, "rqyl": 2e7},
        {"trade_date": ts, "ts_code": "430047.BJ",
         "rzye": 3e8, "rqye": 3e7, "rzmre": 3e7, "rqyl": 3e6},
    ])


def test_load_margin_detail_pulls_each_trade_date(tmp_path):
    """loader 应该对区间内每个 trade_date 调一次 pull_margin_detail。"""
    start = pd.Timestamp("2026-08-07")
    end = pd.Timestamp("2026-08-11")
    as_of = pd.Timestamp("2026-08-12", tz="Asia/Shanghai")
    with patch(
        "flow_dashboard.data.loaders._pull_margin_detail_for_load",
        side_effect=_fake_margin_detail,
    ) as mock:
        df = load_margin_detail(
            start=start, end=end,
            as_of=as_of,
            cache_dir=tmp_path, use_cache=False,
        )
    # 5 个日历日 (08-07 ~ 08-11)
    assert mock.call_count == 5
    assert len(df) == 15  # 5 days × 3 stocks（沪深北三市）


def test_load_margin_detail_has_audit_columns(tmp_path):
    as_of = pd.Timestamp("2026-08-12", tz="Asia/Shanghai")
    with patch(
        "flow_dashboard.data.loaders._pull_margin_detail_for_load",
        side_effect=_fake_margin_detail,
    ):
        df = load_margin_detail(
            start=pd.Timestamp("2026-08-07"),
            end=pd.Timestamp("2026-08-11"),
            as_of=as_of,
            cache_dir=tmp_path, use_cache=False,
        )
    from flow_dashboard.data.schema import AUDIT_COLUMNS
    for col in AUDIT_COLUMNS:
        assert col in df.columns


def test_load_margin_detail_available_at_filter(tmp_path):
    """available_at > as_of 的行应该被过滤掉。"""
    as_of = pd.Timestamp("2026-08-12 12:00", tz="Asia/Shanghai")
    with patch(
        "flow_dashboard.data.loaders._pull_margin_detail_for_load",
        side_effect=_fake_margin_detail,
    ):
        df = load_margin_detail(
            start=pd.Timestamp("2026-08-07"),
            end=pd.Timestamp("2026-08-11"),
            as_of=as_of,
            cache_dir=tmp_path, use_cache=False,
        )
    # margin_detail 的 available_at = trade_date + 19:00；08-11 19:00 < 08-12 12:00 → 全部通过
    assert (df["available_at"] <= as_of).all()


def test_load_margin_detail_uses_cache_on_second_call(tmp_path):
    as_of = pd.Timestamp("2026-08-12", tz="Asia/Shanghai")
    with patch(
        "flow_dashboard.data.loaders._pull_margin_detail_for_load",
        side_effect=_fake_margin_detail,
    ) as mock:
        load_margin_detail(
            start=pd.Timestamp("2026-08-07"),
            end=pd.Timestamp("2026-08-11"),
            as_of=as_of,
            cache_dir=tmp_path,  # use_cache=True default, writes to cache
        )
        load_margin_detail(
            start=pd.Timestamp("2026-08-07"),
            end=pd.Timestamp("2026-08-11"),
            as_of=as_of,
            cache_dir=tmp_path,  # use_cache=True default, reads from cache
        )
    # 5 个 trade_date 只在第一次调；第二次走缓存
    assert mock.call_count == 5


def test_load_margin_detail_caches_empty_day_sentinel(tmp_path):
    """空数据日（周末/节假日）落空哨兵文件，后续运行不再重探。

    趋势面板用 2 年长窗口，若每个非交易日都重新探测，单次运行会
    多打数百次无效 API 调用。
    """
    calls = {"n": 0}

    def _fake(trade_date: str) -> pd.DataFrame:
        calls["n"] += 1
        if pd.Timestamp(trade_date).weekday() >= 5:
            return pd.DataFrame()  # 08-08(六)/08-09(日) 无数据
        return _fake_margin_detail(trade_date)

    start = pd.Timestamp("2026-08-07")
    end = pd.Timestamp("2026-08-11")
    as_of = pd.Timestamp("2026-08-12", tz="Asia/Shanghai")
    with patch(
        "flow_dashboard.data.loaders._pull_margin_detail_for_load",
        side_effect=_fake,
    ):
        load_margin_detail(start=start, end=end, as_of=as_of, cache_dir=tmp_path)
        load_margin_detail(start=start, end=end, as_of=as_of, cache_dir=tmp_path)
    # 5 个日历日各拉一次；第二次（含两个空日）全走哨兵/数据缓存
    assert calls["n"] == 5


def test_load_margin_detail_no_sentinel_before_publish_time(tmp_path):
    """当日 19:00 发布时点未到时查到的空结果是"尚未发布"，不落哨兵。

    回归：若落哨兵，当晚 eod_preview 的补拉会被永久阻断（文件存在即跳过），
    该交易日数据从此缺失。
    """
    state = {"published": False}
    calls = {"20260811": 0}

    def _fake(trade_date: str) -> pd.DataFrame:
        if trade_date == "20260811":
            calls["20260811"] += 1
            if not state["published"]:
                return pd.DataFrame()  # 15:00 查询：当日数据尚未发布
        return _fake_margin_detail(trade_date)

    start = end = pd.Timestamp("2026-08-11")
    with patch(
        "flow_dashboard.data.loaders._pull_margin_detail_for_load",
        side_effect=_fake,
    ):
        # 15:00（发布前）：空结果不落哨兵
        load_margin_detail(
            start=start, end=end,
            as_of=pd.Timestamp("2026-08-11 15:00", tz="Asia/Shanghai"),
            cache_dir=tmp_path,
        )
        assert not (tmp_path / "margin_detail_20260811.parquet").exists()

        # 20:00（发布后）：重新拉取，数据入库
        state["published"] = True
        df = load_margin_detail(
            start=start, end=end,
            as_of=pd.Timestamp("2026-08-11 20:00", tz="Asia/Shanghai"),
            cache_dir=tmp_path,
        )
    assert calls["20260811"] == 2  # 发布后确实重拉了
    assert len(df) == 3
    assert (tmp_path / "margin_detail_20260811.parquet").exists()


def test_recent_empty_sentinel_is_retried_next_morning(tmp_path):
    day = pd.Timestamp("2026-10-13")
    path = tmp_path / "margin_detail_20261013.parquet"
    state = {"calls": 0}

    def pull(trade_date):
        state["calls"] += 1
        return pd.DataFrame() if state["calls"] == 1 else _fake_margin_detail(trade_date)

    with patch("flow_dashboard.data.loaders._pull_margin_detail_for_load", side_effect=pull):
        load_margin_detail(start=day, end=day,
                           as_of=pd.Timestamp("2026-10-13 19:30", tz="Asia/Shanghai"),
                           cache_dir=tmp_path)
        assert path.exists() and pd.read_parquet(path).empty
        result = load_margin_detail(start=day, end=day,
                                    as_of=pd.Timestamp("2026-10-14 08:00", tz="Asia/Shanghai"),
                                    cache_dir=tmp_path)
    assert state["calls"] == 2
    assert len(result) == 3
    assert len(pd.read_parquet(path)) == 3


def test_load_margin_detail_repairs_partial_cached_day(tmp_path):
    """回归 2026-10-27+：按日缓存缺市（深市发布滞后）时近期日子须重拉补齐。

    部分数据"文件存在即跳过"会让创业板线（300/301 全在深市）断流。
    """
    full = _fake_margin_detail("2026-11-02")
    partial = full[full["ts_code"] != "000001.SZ"].copy()  # 缺 SZ

    calls = {"n": 0}

    def _fake(trade_date: str) -> pd.DataFrame:
        calls["n"] += 1
        return (partial if calls["n"] == 1 else full).copy()

    kwargs = dict(
        start=pd.Timestamp("2026-11-02"),
        end=pd.Timestamp("2026-11-02"),
        as_of=pd.Timestamp("2026-11-03 10:00", tz="Asia/Shanghai"),
        cache_dir=tmp_path,
    )
    with patch(
        "flow_dashboard.data.loaders._pull_margin_detail_for_load",
        side_effect=_fake,
    ):
        load_margin_detail(**kwargs)  # 第一次：缺 SZ 写盘
        out = load_margin_detail(**kwargs)  # 第二次：应重拉修复
    assert calls["n"] == 2
    assert set(out["ts_code"]) == {"000001.SZ", "600000.SH", "430047.BJ"}


def test_load_margin_detail_keeps_old_partial_day_without_refetch(tmp_path):
    """超过重试窗口的部分数据保留事实、不再重拉（防 API 无限重试）。"""
    full = _fake_margin_detail("2026-10-10")
    partial = full[full["ts_code"] != "000001.SZ"].copy()

    calls = {"n": 0}

    def _fake(trade_date: str) -> pd.DataFrame:
        calls["n"] += 1
        return partial.copy()

    # 首跑写入部分文件（绕过缓存直接造文件更直观：这里用 loader 首跑）
    kwargs = dict(
        start=pd.Timestamp("2026-10-10"),
        end=pd.Timestamp("2026-10-10"),
        as_of=pd.Timestamp("2026-10-11 10:00", tz="Asia/Shanghai"),
        cache_dir=tmp_path,
    )
    with patch(
        "flow_dashboard.data.loaders._pull_margin_detail_for_load",
        side_effect=_fake,
    ):
        load_margin_detail(**kwargs)
        # 一个月后再跑：超出 7 天重试窗口 → 不重拉，保留部分数据
        out = load_margin_detail(
            start=pd.Timestamp("2026-10-10"),
            end=pd.Timestamp("2026-10-10"),
            as_of=pd.Timestamp("2026-11-11 10:00", tz="Asia/Shanghai"),
            cache_dir=tmp_path,
        )
    assert calls["n"] == 1
    assert "000001.SZ" not in set(out["ts_code"])
