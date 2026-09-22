"""hk_short loaders：parquet 缓存 → 增量 → merge → PIT 过滤。

遵循 data/loaders.py 契约。available_at 规则（源验证 §8 冻结，一律 tz-aware
Asia/Shanghai）：
- 东财日频（卖空/K线）：trade_date + 16:10
- HKEX dayquot：公布文件日 + 17:30（restated 修正行 = 修正公布日 + 17:30）
- SFC 周报：published_at（Last-Modified），退化 first_observed_at
- f84 总股本 / LOS 主表：当前快照，available_at = fetched_at
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path

import pandas as pd

from flow_dashboard.config import HK_SHORT_CACHE_DIR
from flow_dashboard.data.hk_short import em_client, hkex_client, sfc_client
from flow_dashboard.data.hk_short import hk_calendar as cal

log = logging.getLogger(__name__)

TZ = "Asia/Shanghai"
EM_AVAILABLE = pd.Timedelta(hours=16, minutes=10)
HKEX_AVAILABLE = pd.Timedelta(hours=17, minutes=30)

EM_FILE = "em_sellshort_daily.parquet"
DAYS_FILE = "em_days_covered.parquet"
HKEX_FILE = "hkex_dayquot_daily.parquet"
SFC_FILE = "sfc_weekly.parquet"
SFC_NONE_FILE = "sfc_no_report.parquet"
KLINE_FILE = "hk_kline.parquet"
SHARES_FILE = "hk_shares.parquet"
LOS_FILE = "los_master.parquet"


def _as_of_ts(as_of) -> pd.Timestamp:
    ts = pd.Timestamp(as_of)
    return ts.tz_localize(TZ) if ts.tzinfo is None else ts.tz_convert(TZ)


def _naive_sh(as_of) -> pd.Timestamp:
    return _as_of_ts(as_of).tz_localize(None)


def _em_avail(trade_date) -> pd.Timestamp:
    return pd.Timestamp(trade_date).tz_localize(TZ) + EM_AVAILABLE


def _hkex_avail(pub_date) -> pd.Timestamp:
    return pd.Timestamp(pub_date).tz_localize(TZ) + HKEX_AVAILABLE


def _code5(code: str) -> str:
    return str(code).split(".")[0].zfill(5)


def _read(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path) if path.exists() else pd.DataFrame()


def _write(df: pd.DataFrame, path: Path) -> None:
    """原子写：先落临时文件再 os.replace，避免崩溃留下截断 parquet 毁掉后续读取。"""
    if df.empty:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def _pit(df: pd.DataFrame, as_of) -> pd.DataFrame:
    if df.empty or "available_at" not in df.columns:
        return df
    avail = pd.to_datetime(df["available_at"], utc=True)
    ts = _as_of_ts(as_of).tz_convert("utc")
    return df[avail <= ts].reset_index(drop=True)


def _merge(old: pd.DataFrame, new: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """new 覆盖 old 同 keys 行；first_observed_at 保留最早；available_at 晚者胜。"""
    if old.empty:
        return new.copy()
    if new.empty:
        return old.copy()
    if "first_observed_at" in old.columns:
        prior = (
            old[keys + ["first_observed_at"]]
            .drop_duplicates(subset=keys)
            .rename(columns={"first_observed_at": "_first_obs"})
        )
        new = new.merge(prior, on=keys, how="left")
        if "first_observed_at" in new.columns:
            new["first_observed_at"] = new["_first_obs"].fillna(
                new["first_observed_at"]
            )
        else:
            new["first_observed_at"] = new["_first_obs"]
        new = new.drop(columns=["_first_obs"])
    out = pd.concat([old, new], ignore_index=True)
    if "available_at" in out.columns:
        out = out.sort_values("available_at", kind="stable")
    return out.drop_duplicates(subset=keys, keep="last", ignore_index=True)


def _merge_days(old: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """full 优先于 partial（partial 日不能进市场聚合的 full 集合）。"""
    if old.empty:
        return new.copy()
    out = pd.concat([old, new], ignore_index=True)
    out["_p"] = out["coverage"].map({"full": 0, "partial": 1}).fillna(2)
    out = out.sort_values(["trade_date", "_p"], kind="stable")
    return out.drop_duplicates(
        subset="trade_date", keep="first", ignore_index=True
    ).drop(columns="_p")


def _annotate(
    df: pd.DataFrame,
    *,
    source: str,
    version: str,
    available_at,
    fetched_at,
    quality_flags=None,
) -> pd.DataFrame:
    out = df.copy()
    out["source"] = source
    out["source_version"] = version
    out["fetched_at"] = fetched_at
    out["available_at"] = (
        list(available_at)
        if isinstance(available_at, (list, pd.Series))
        else available_at
    )
    if "first_observed_at" not in out.columns:
        out["first_observed_at"] = fetched_at
    if quality_flags is None:
        out["quality_flags"] = ""
    elif isinstance(quality_flags, (list, pd.Series)):
        out["quality_flags"] = list(quality_flags)
    else:
        out["quality_flags"] = quality_flags
    return out


def _trading_days_between(start, end) -> list[pd.Timestamp]:
    out, ts = [], pd.Timestamp(start).normalize()
    end_n = pd.Timestamp(end).normalize()
    while ts <= end_n:
        if cal.is_hk_trading_day(ts):
            out.append(ts)
        ts += pd.Timedelta(days=1)
    return out


def _expected_latest(as_of, offset: pd.Timedelta):
    """满足 available_at = D + offset <= as_of 的最大香港交易日（naive）。"""
    ts = _naive_sh(as_of)
    d = ts.normalize()
    for _ in range(400):
        if cal.is_hk_trading_day(d) and d + offset <= ts:
            return d
        d -= pd.Timedelta(days=1)
    return None


def load_em_sellshort(
    *, as_of, start=None, end=None, codes=None, allow_fetch=True, cache_dir=None
) -> pd.DataFrame:
    """codes=None：全市场逐日增量（标 full）；codes 指定：个股区间补历史（标 partial）。"""
    cdir = Path(cache_dir) if cache_dir else HK_SHORT_CACHE_DIR
    as_of_ts = _as_of_ts(as_of)
    path, days_path = cdir / EM_FILE, cdir / DAYS_FILE
    cached, days_df = _read(path), _read(days_path)
    expected = _expected_latest(as_of_ts, EM_AVAILABLE)

    if codes is None:
        full = (
            set(
                pd.to_datetime(days_df.loc[days_df["coverage"] == "full", "trade_date"])
            )
            if not days_df.empty
            else set()
        )
        lo = (
            pd.Timestamp(start).normalize()
            if start
            else (expected - pd.Timedelta(days=14) if expected else None)
        )
        hi = pd.Timestamp(end).normalize() if end else expected
        targets = (
            [d for d in _trading_days_between(lo, hi) if d not in full]
            if lo is not None and hi is not None
            else []
        )
        frames = []
        for d in targets:
            if not allow_fetch:
                break
            try:
                day = em_client.fetch_sellshort_day(d)
            except Exception as e:  # noqa: BLE001 — 单日失败不阻塞其余增量
                log.warning("em sellshort %s failed: %s", d.date(), e)
                continue
            if day is None or day.empty:
                log.warning("em sellshort empty on %s", d.date())
                continue
            day = _annotate(
                day,
                source="eastmoney",
                version="em_sellshort_html_v1",
                available_at=_em_avail(d),
                fetched_at=as_of_ts,
            )
            day["trade_date"] = pd.Timestamp(d)
            day["source_date"] = pd.Timestamp(d)
            frames.append(day)
        if frames:
            cached = _merge(
                cached,
                pd.concat(frames, ignore_index=True),
                keys=["code", "trade_date"],
            )
            _write(cached, path)
            new_days = pd.DataFrame(
                {
                    "trade_date": [f["trade_date"].iloc[0] for f in frames],
                    "coverage": ["full"] * len(frames),
                }
            )
            days_df = _merge_days(days_df, new_days)
            _write(days_df, days_path)
    else:
        hi = pd.Timestamp(end).normalize() if end else expected
        frames = []
        for c in codes:
            code5 = _code5(c)
            prev = cached[cached["code"] == code5] if not cached.empty else cached
            if start is not None:
                lo = pd.Timestamp(start).normalize()
            elif not prev.empty:
                lo = pd.Timestamp(prev["trade_date"].max()).normalize() + pd.Timedelta(
                    days=1
                )
            else:
                lo = (hi - pd.Timedelta(days=120)) if hi is not None else None
            if lo is None or hi is None or lo > hi:
                continue
            if not allow_fetch:
                break
            try:
                rng = em_client.fetch_sellshort_stock(code5, lo, hi)
            except Exception as e:  # noqa: BLE001
                log.warning("em sellshort %s failed: %s", code5, e)
                continue
            if rng is None or rng.empty:
                continue
            rng = rng[rng["code"] == code5]
            rng = _annotate(
                rng,
                source="eastmoney",
                version="em_sellshort_html_v1",
                available_at=[_em_avail(t) for t in rng["trade_date"]],
                fetched_at=as_of_ts,
            )
            rng["source_date"] = pd.to_datetime(rng["source_date"])
            frames.append(rng)
        if frames:
            all_new = pd.concat(frames, ignore_index=True)
            cached = _merge(cached, all_new, keys=["code", "trade_date"])
            _write(cached, path)
            touched = sorted(set(pd.to_datetime(all_new["trade_date"])))
            new_days = pd.DataFrame(
                {"trade_date": touched, "coverage": ["partial"] * len(touched)}
            )
            days_df = _merge_days(days_df, new_days)
            _write(days_df, days_path)
    return _pit(cached, as_of_ts)


def load_em_days_covered(*, as_of, cache_dir=None) -> list[pd.Timestamp]:
    """已确认 full 覆盖的交易日（升序）——市场聚合只允许用这些天。"""
    cdir = Path(cache_dir) if cache_dir else HK_SHORT_CACHE_DIR
    days_df = _read(cdir / DAYS_FILE)
    if days_df.empty:
        return []
    return sorted(
        pd.to_datetime(days_df.loc[days_df["coverage"] == "full", "trade_date"])
    )


def load_hkex_dayquot(
    *, as_of, start=None, end=None, allow_fetch=True, cache_dir=None
) -> pd.DataFrame:
    cdir = Path(cache_dir) if cache_dir else HK_SHORT_CACHE_DIR
    as_of_ts = _as_of_ts(as_of)
    path = cdir / HKEX_FILE
    cached = _read(path)
    expected = _expected_latest(as_of_ts, HKEX_AVAILABLE)
    have = (
        set(pd.to_datetime(cached["source_date"]).unique())
        if not cached.empty
        else set()
    )
    lo = (
        pd.Timestamp(start).normalize()
        if start
        else (expected - pd.Timedelta(days=10) if expected else None)
    )
    hi = pd.Timestamp(end).normalize() if end else expected
    targets = (
        [d for d in _trading_days_between(lo, hi) if d not in have]
        if lo is not None and hi is not None
        else []
    )
    frames = []
    for d in targets:
        if not allow_fetch:
            break
        try:
            df_d = hkex_client.fetch_dayquot(d)
            if (df_d is None or df_d.empty) and d == expected:
                df_d = hkex_client.fetch_ashtmain(d)  # 归档未生成时的当日文件兜底
        except Exception as e:  # noqa: BLE001
            log.warning("hkex dayquot %s failed: %s", d.date(), e)
            df_d = None
        if df_d is None or df_d.empty:
            continue
        flags = ["" if t == pd.Timestamp(d) else "restated" for t in df_d["trade_date"]]
        df_d = _annotate(
            df_d,
            source="hkex",
            version="hkex_dayquot_v1",
            available_at=_hkex_avail(d),
            fetched_at=as_of_ts,
            quality_flags=flags,
        )
        df_d["source_date"] = pd.Timestamp(d)
        frames.append(df_d)
    if frames:
        cached = _merge(
            cached, pd.concat(frames, ignore_index=True), keys=["code", "trade_date"]
        )
        _write(cached, path)
    return _pit(cached, as_of_ts)


def load_sfc_weekly(
    *, as_of, weeks=8, allow_fetch=True, cache_dir=None
) -> pd.DataFrame:
    cdir = Path(cache_dir) if cache_dir else HK_SHORT_CACHE_DIR
    as_of_ts = _as_of_ts(as_of)
    path, none_path = cdir / SFC_FILE, cdir / SFC_NONE_FILE
    cached, none_df = _read(path), _read(none_path)
    have = (
        set(pd.to_datetime(cached["position_date"]).unique())
        if not cached.empty
        else set()
    )
    none_map = (
        {
            pd.Timestamp(r.position_date): pd.Timestamp(r.checked_at)
            for r in none_df.itertuples()
        }
        if not none_df.empty
        else {}
    )
    now_naive = _naive_sh(as_of)
    frames, new_none = [], []
    for pos in cal.recent_sfc_position_dates(as_of_ts, n=weeks):
        if pos in have:
            continue
        last = none_map.get(pos)
        if last is not None and (now_naive - last).days < 14:
            continue
        if not allow_fetch:
            continue
        try:
            df_w = sfc_client.fetch_sfc_week(pos, fetched_at=as_of_ts)
        except Exception as e:  # noqa: BLE001
            log.warning("sfc %s failed: %s", pos.date(), e)
            continue
        if df_w is None:
            new_none.append(
                {"position_date": pos, "checked_at": as_of_ts.tz_localize(None)}
            )
            continue
        df_w["quality_flags"] = ""  # 客户端自注解帧缺此列，统一缓存 schema
        frames.append(df_w)
    if frames:
        cached = _merge(
            cached, pd.concat(frames, ignore_index=True), keys=["code", "position_date"]
        )
        _write(cached, path)
    if new_none:
        none_df = _merge(none_df, pd.DataFrame(new_none), keys=["position_date"])
        _write(none_df, none_path)
    return _pit(cached, as_of_ts)


def load_hk_kline(
    *, as_of, secids, start=None, end=None, allow_fetch=True, cache_dir=None
) -> pd.DataFrame:
    cdir = Path(cache_dir) if cache_dir else HK_SHORT_CACHE_DIR
    as_of_ts = _as_of_ts(as_of)
    path = cdir / KLINE_FILE
    cached = _read(path)
    expected = _expected_latest(as_of_ts, EM_AVAILABLE)
    hi = pd.Timestamp(end).normalize() if end else expected
    frames = []
    for s in secids:
        prev = cached[cached["secid"] == s] if not cached.empty else cached
        if start is not None:
            lo = pd.Timestamp(start).normalize()
        elif not prev.empty:
            lo = pd.Timestamp(prev["trade_date"].max()).normalize() + pd.Timedelta(
                days=1
            )
        else:
            lo = (hi - pd.Timedelta(days=200)) if hi is not None else None
        if lo is None or hi is None or lo > hi:
            continue
        if not allow_fetch:
            continue
        try:
            k = em_client.fetch_kline(s, lo, hi, now=as_of_ts)
        except Exception as e:  # noqa: BLE001
            log.warning("kline %s failed: %s", s, e)
            continue
        if k is None or k.empty:
            continue
        k = _annotate(
            k,
            source="eastmoney",
            version="em_kline_v1",
            available_at=[_em_avail(t) for t in k["trade_date"]],
            fetched_at=as_of_ts,
        )
        k["source_date"] = pd.to_datetime(k["trade_date"]).dt.normalize()
        frames.append(k)
    if frames:
        cached = _merge(
            cached, pd.concat(frames, ignore_index=True), keys=["secid", "trade_date"]
        )
        _write(cached, path)
    return _pit(cached, as_of_ts)


def load_total_shares(
    *, as_of, codes, refresh=False, allow_fetch=True, cache_dir=None
) -> pd.DataFrame:
    """f84 当前快照（available_at = fetched_at，快照语义）。每 code 保留多期快照，返回每 code 最新一期。"""
    cdir = Path(cache_dir) if cache_dir else HK_SHORT_CACHE_DIR
    as_of_ts = _as_of_ts(as_of)
    path = cdir / SHARES_FILE
    cached = _read(path)
    have = set(cached["code"]) if not cached.empty else set()
    frames = []
    for c in [_code5(x) for x in codes]:
        if not refresh and c in have:
            continue
        if not allow_fetch:
            break
        try:
            n = em_client.fetch_total_shares(c)
        except Exception as e:  # noqa: BLE001
            log.warning("f84 %s failed: %s", c, e)
            continue
        snap = pd.DataFrame([{"code": c, "total_shares": float(n)}])
        snap = _annotate(
            snap,
            source="eastmoney",
            version="em_f84_v1",
            available_at=as_of_ts,
            fetched_at=as_of_ts,
        )
        snap["source_date"] = _naive_sh(as_of_ts).normalize()
        frames.append(snap)
    if frames:
        cached = _merge(
            cached, pd.concat(frames, ignore_index=True), keys=["code", "source_date"]
        )
        _write(cached, path)
    if cached.empty:
        return cached
    latest = cached.sort_values("available_at", kind="stable").drop_duplicates(
        subset=["code"], keep="last", ignore_index=True
    )
    return _pit(latest, as_of_ts)


def _parse_eff(eff_str: str):
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", eff_str or "")
    return (
        pd.Timestamp(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else pd.NaT
    )


def load_etf_master(
    *, as_of, allow_fetch=True, cache_dir=None
) -> tuple[pd.DataFrame, pd.Timestamp]:
    """LOS 主表（>7 天刷新；失败退回缓存）。返回 (los_df, effective_date)。"""
    cdir = Path(cache_dir) if cache_dir else HK_SHORT_CACHE_DIR
    as_of_ts = _as_of_ts(as_of)
    path = cdir / LOS_FILE
    cached = _read(path)
    stale = True
    if not cached.empty:
        last = pd.to_datetime(cached["fetched_at"], utc=True).max()
        stale = (as_of_ts.tz_convert("utc") - last) > pd.Timedelta(days=7)
    if stale and allow_fetch:
        try:
            los, eff = hkex_client.fetch_list_of_securities()
        except Exception as e:  # noqa: BLE001 — 主表失败退回缓存
            log.warning("LOS fetch failed: %s", e)
            los, eff = pd.DataFrame(), ""
        if not los.empty:
            los = _annotate(
                los,
                source="hkex",
                version="hkex_los_v1",
                available_at=as_of_ts,
                fetched_at=as_of_ts,
            )
            los["source_date"] = _naive_sh(as_of_ts).normalize()
            eff_ts = _parse_eff(eff)
            los["effective_date"] = eff_ts
            _write(los, path)
            return _pit(los, as_of_ts), eff_ts
    eff = pd.Timestamp(cached["effective_date"].iloc[0]) if not cached.empty else pd.NaT
    return _pit(cached, as_of_ts), eff
