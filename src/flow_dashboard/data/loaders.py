"""统一 loader 契约。

per spec §3.2.1:
    load(start, end, as_of, universe=None, use_cache=True) -> DataFrame
所有 loader 必须：
- 返回的 DataFrame 含 schema.AUDIT_COLUMNS
- 执行 available_at <= as_of 过滤
- 命中缓存时不调网络；use_cache=False 时强制刷新
- 单位统一（份额=份，金额=元）

available_at 由 provider 标注数据的实际可得时间，不等于 trade_date。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from flow_dashboard.config import CACHE_DIR, TIMEZONE
from flow_dashboard.data.schema import AUDIT_COLUMNS
from flow_dashboard.data.tushare_providers import (
    pull_etf_share_size,
    pull_margin,
    pull_margin_detail,
    pull_fut_daily,
    pull_index_daily,
    pull_fund_nav,
)


# ============ Helper Functions ============

def _empty_with_audit() -> pd.DataFrame:
    """创建含审计列的空 DataFrame。"""
    cols = list(AUDIT_COLUMNS)
    return pd.DataFrame(columns=cols)


def _filter_range(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """按 trade_date 过滤时间范围。"""
    if df.empty or "trade_date" not in df.columns:
        return df
    mask = (df["trade_date"] >= pd.Timestamp(start)) & (df["trade_date"] <= pd.Timestamp(end))
    return df[mask].reset_index(drop=True)


# ============ ETF 份额（spec §1.3 主源） ============

def load_etf_share(
    *,
    codes: list[str],
    start: pd.Timestamp,
    end: pd.Timestamp,
    as_of: pd.Timestamp,
    cache_dir: Path | str | None = None,
    use_cache: bool = True,
) -> pd.DataFrame:
    """加载 ETF 份额，落盘 parquet 增量缓存，PIT 过滤。

    Stale 检测：cache 命中后比对每个 code 的最新 trade_date 与 PIT 可得阈值
    min(end, as_of 时已可得的最新 trade_date)。数据 T 日 19:00 后可得，
    早上定稿（T+1）时缺 T 日数据即重拉；晚间 preview 时阈值自然回落到 T-1。
    """
    cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "etf_share.parquet"

    fetched_at = pd.Timestamp.now(tz=TIMEZONE)

    if use_cache and cache_path.exists():
        cached = pd.read_parquet(cache_path)
        cached = cached[cached["available_at"] <= pd.Timestamp(as_of)]
        cached_codes = set(cached["ts_code"].unique()) if not cached.empty else set()
        missing_codes = [c for c in codes if c not in cached_codes]
        stale_codes = _stale_codes(cached, codes, end, as_of)
        codes_to_refresh = missing_codes + stale_codes
        if not codes_to_refresh:
            return _filter_range(cached, start, end)

        fresh = _pull_etf_share_for_load(codes_to_refresh, start, end)
        fresh = _annotate_etf_share(fresh, fetched_at)
        # Apply PIT filter to fresh data
        fresh = fresh[fresh["available_at"] <= pd.Timestamp(as_of)]
        combined = pd.concat([cached, fresh], ignore_index=True)
        combined = combined.drop_duplicates(
            subset=["ts_code", "trade_date", "source_date"], keep="last"
        )
        combined.to_parquet(cache_path, index=False)
        return _filter_range(combined, start, end)

    fresh = _pull_etf_share_for_load(codes, start, end)
    fresh = _annotate_etf_share(fresh, fetched_at)
    # Apply PIT filter: only keep rows where available_at <= as_of
    fresh = fresh[fresh["available_at"] <= pd.Timestamp(as_of)]
    # Apply time range filter
    fresh = _filter_range(fresh, start, end)
    if use_cache:
        fresh.to_parquet(cache_path, index=False)
    return fresh


def _latest_available_date(as_of: pd.Timestamp) -> pd.Timestamp:
    """Tushare 日频数据 available_at = trade_date 当日 19:00（TIMEZONE）。

    返回 as_of 时刻已可得的最新 trade_date（naive 日期）：19:00 前算前一日。
    """
    ts = pd.Timestamp(as_of)
    if ts.tzinfo is not None:
        ts = ts.tz_convert(TIMEZONE).tz_localize(None)
    day = ts.normalize()
    return day if ts.hour >= 19 else day - pd.Timedelta(days=1)


def _stale_threshold(end: pd.Timestamp, as_of: pd.Timestamp) -> pd.Timestamp:
    """stale 判定阈值 = min(end, as_of 时已可得的最新 trade_date)。

    早上定稿（T+1 09:15, end=T）时 T 数据已发布 → 阈值=T，cache 缺 T 即重拉；
    晚间 preview（T 19:30, end=T）时 T 数据尚未发布 → 阈值回落到 PIT 可得日。
    """
    return min(pd.Timestamp(end).normalize(), _latest_available_date(as_of))


def _stale_codes(
    cached: pd.DataFrame,
    codes: list[str],
    end: pd.Timestamp,
    as_of: pd.Timestamp,
    date_col: str = "trade_date",
) -> list[str]:
    """识别 cached 中 date_col 落后于 PIT 可得阈值的 code（需重拉）。

    用于多 code 共享 cache 的 loader（etf_share / fund_nav）。
    """
    if cached.empty or "ts_code" not in cached.columns or date_col not in cached.columns:
        return []
    threshold = _stale_threshold(end, as_of)
    stale = []
    for c in codes:
        sub = cached[cached["ts_code"] == c]
        if sub.empty:
            continue
        code_max = sub[date_col].max()
        if pd.isna(code_max) or pd.Timestamp(code_max).normalize() < threshold:
            stale.append(c)
    return stale


def _stale_single(
    cached: pd.DataFrame,
    end: pd.Timestamp,
    as_of: pd.Timestamp,
    date_col: str = "trade_date",
) -> bool:
    """单 code per file loader 用（fut_daily / index_daily）。

    返回 True 表示 cache 落后，需重拉。
    """
    if cached.empty or date_col not in cached.columns:
        return True
    threshold = _stale_threshold(end, as_of)
    cached_max = pd.Timestamp(cached[date_col].max()).normalize()
    return cached_max < threshold


def _pull_etf_share_for_load(
    codes: list[str], start: pd.Timestamp, end: pd.Timestamp
) -> pd.DataFrame:
    """Thin wrapper around provider for monkeypatch in tests."""
    return pull_etf_share_size(
        codes=codes,
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
    )


def _annotate_etf_share(
    df: pd.DataFrame, fetched_at: pd.Timestamp
) -> pd.DataFrame:
    """添加审计列到 ETF 份额数据。

    available_at 设为 trade_date 当日 19:00:00（Tushare 日频数据可得时间）。
    """
    if df.empty:
        return _empty_with_audit()
    df = df.copy()
    if "share_in_shares" not in df.columns:
        # provider 已标准化，但保险
        df["share_in_shares"] = df["total_share"] * 10000
    df["total_size_cny"] = df["total_size"] * 10000  # 万元 → 元
    df["source_date"] = df["trade_date"]
    df["first_observed_at"] = fetched_at
    # 设每个 trade_date 的 available_at 为当日 19:00（Tushare 日频数据可得时间）
    df["available_at"] = df["trade_date"].apply(
        lambda d: pd.Timestamp(
            year=d.year, month=d.month, day=d.day,
            hour=19, minute=0, second=0, tz=TIMEZONE
        )
    )
    df["fetched_at"] = fetched_at
    df["source"] = "tushare"
    df["source_version"] = "etf_share_size_v1"
    df["is_stale"] = False
    df["quality_flags"] = ""
    return df


# ============ Margin（spec §1.3 SSE/SZSE/BSE 三所） ============

MARGIN_EXCHANGES = ("SSE", "SZSE", "BSE")


def _margin_latest_day_complete(cached: pd.DataFrame) -> bool:
    """缓存内最新交易日三所是否齐全。

    交易所两融数据发布有先后（深市常晚数小时），T+1 早间拉取可能只拿到
    部分交易所；此时不能短路，需重拉补齐，否则缺所日会长期留在缓存里。
    """
    if cached.empty:
        return False
    latest = cached["trade_date"].max()
    present = set(
        cached.loc[cached["trade_date"] == latest, "exchange_id"].astype(str)
    )
    return set(MARGIN_EXCHANGES).issubset(present)


def load_margin(
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    as_of: pd.Timestamp,
    cache_dir: Path | str | None = None,
    use_cache: bool = True,
) -> pd.DataFrame:
    """加载融资融券汇总数据，落盘 parquet 增量缓存，PIT 过滤。"""
    cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "margin.parquet"

    fetched_at = pd.Timestamp.now(tz=TIMEZONE)
    if use_cache and cache_path.exists():
        cached = pd.read_parquet(cache_path)
        cached = cached[cached["available_at"] <= pd.Timestamp(as_of)]
        if not cached.empty:
            cached_start = cached["trade_date"].min()
            cached_end = cached["trade_date"].max()
            if (
                cached_start <= start
                and cached_end >= end
                and _margin_latest_day_complete(cached)
            ):
                return _filter_range(cached, start, end)
        fresh = _pull_margin_for_load(start, end)
        fresh = _annotate_margin(fresh, fetched_at)
        # Apply PIT filter to fresh data
        fresh = fresh[fresh["available_at"] <= pd.Timestamp(as_of)]
        combined = pd.concat([cached, fresh], ignore_index=True).drop_duplicates(
            subset=["trade_date", "exchange_id"], keep="last"
        )
        combined.to_parquet(cache_path, index=False)
        return _filter_range(combined, start, end)

    fresh = _pull_margin_for_load(start, end)
    fresh = _annotate_margin(fresh, fetched_at)
    # Apply PIT filter to fresh data
    fresh = fresh[fresh["available_at"] <= pd.Timestamp(as_of)]
    # Apply time range filter
    fresh = _filter_range(fresh, start, end)
    if use_cache:
        fresh.to_parquet(cache_path, index=False)
    return fresh


def _pull_margin_for_load(
    start: pd.Timestamp, end: pd.Timestamp
) -> pd.DataFrame:
    """Thin wrapper around provider for monkeypatch in tests."""
    return pull_margin(
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
    )


def _annotate_margin(
    df: pd.DataFrame, fetched_at: pd.Timestamp
) -> pd.DataFrame:
    """添加审计列到融资融券数据。

    available_at 设为 trade_date 当日 19:00:00（Tushare 日频数据可得时间）。
    """
    if df.empty:
        return _empty_with_audit()
    df = df.copy()
    df["source_date"] = df["trade_date"]
    df["first_observed_at"] = fetched_at
    # 设每个 trade_date 的 available_at 为当日 19:00（Tushare 日频数据可得时间）
    df["available_at"] = df["trade_date"].apply(
        lambda d: pd.Timestamp(
            year=d.year, month=d.month, day=d.day,
            hour=19, minute=0, second=0, tz=TIMEZONE
        )
    )
    df["fetched_at"] = fetched_at
    df["source"] = "tushare"
    df["source_version"] = "margin_v1"
    df["is_stale"] = False
    df["quality_flags"] = ""
    return df


# ============ Fut daily（CFFEX IC/IM 期货日行情） ============

def load_fut_daily(
    *,
    ts_code: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    as_of: pd.Timestamp,
    cache_dir: Path | str | None = None,
    use_cache: bool = True,
) -> pd.DataFrame:
    """加载期货日线数据，落盘 parquet 增量缓存，PIT 过滤。"""
    cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"fut_daily_{ts_code.replace('.', '_')}.parquet"

    fetched_at = pd.Timestamp.now(tz=TIMEZONE)
    if use_cache and cache_path.exists():
        cached = pd.read_parquet(cache_path)
        cached = cached[cached["available_at"] <= pd.Timestamp(as_of)]
        if not cached.empty and "ts_code" in cached.columns:
            cached_codes = set(cached["ts_code"].unique())
            if ts_code in cached_codes and not _stale_single(cached, end, as_of):
                return _filter_range(cached, start, end)

    fresh = pull_fut_daily(
        ts_code=ts_code,
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
    )
    fresh = _annotate_fut_daily(fresh, fetched_at)
    # Apply PIT filter to fresh data
    fresh = fresh[fresh["available_at"] <= pd.Timestamp(as_of)]
    # Apply time range filter
    fresh = _filter_range(fresh, start, end)
    if use_cache:
        fresh.to_parquet(cache_path, index=False)
    return fresh


def _annotate_fut_daily(
    df: pd.DataFrame, fetched_at: pd.Timestamp
) -> pd.DataFrame:
    """添加审计列到期货日线数据。

    available_at 设为 trade_date 当日 19:00:00（Tushare 日频数据可得时间）。
    """
    if df.empty:
        return _empty_with_audit()
    df = df.copy()
    df["source_date"] = df["trade_date"]
    df["first_observed_at"] = fetched_at
    # 设每个 trade_date 的 available_at 为当日 19:00（Tushare 日频数据可得时间）
    df["available_at"] = df["trade_date"].apply(
        lambda d: pd.Timestamp(
            year=d.year, month=d.month, day=d.day,
            hour=19, minute=0, second=0, tz=TIMEZONE
        )
    )
    df["fetched_at"] = fetched_at
    df["source"] = "tushare"
    df["source_version"] = "fut_daily_v1"
    df["is_stale"] = False
    df["quality_flags"] = ""
    return df


# ============ Index daily（CSI500/CSI1000 现货指数日行情） ============

def load_index_daily(
    *,
    ts_code: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
    as_of: pd.Timestamp,
    cache_dir: Path | str | None = None,
    use_cache: bool = True,
) -> pd.DataFrame:
    """加载指数日线数据，落盘 parquet 增量缓存，PIT 过滤。"""
    cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"index_daily_{ts_code.replace('.', '_')}.parquet"

    fetched_at = pd.Timestamp.now(tz=TIMEZONE)
    if use_cache and cache_path.exists():
        cached = pd.read_parquet(cache_path)
        cached = cached[cached["available_at"] <= pd.Timestamp(as_of)]
        if not cached.empty and "ts_code" in cached.columns:
            cached_codes = set(cached["ts_code"].unique())
            if ts_code in cached_codes and not _stale_single(cached, end, as_of):
                return _filter_range(cached, start, end)

    fresh = pull_index_daily(
        ts_code=ts_code,
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
    )
    fresh = _annotate_index_daily(fresh, fetched_at)
    # Apply PIT filter to fresh data
    fresh = fresh[fresh["available_at"] <= pd.Timestamp(as_of)]
    # Apply time range filter
    fresh = _filter_range(fresh, start, end)
    if use_cache:
        fresh.to_parquet(cache_path, index=False)
    return fresh


def _annotate_index_daily(
    df: pd.DataFrame, fetched_at: pd.Timestamp
) -> pd.DataFrame:
    """添加审计列到指数日线数据。

    available_at 设为 trade_date 当日 19:00:00（Tushare 日频数据可得时间）。
    """
    if df.empty:
        return _empty_with_audit()
    df = df.copy()
    df["source_date"] = df["trade_date"]
    df["first_observed_at"] = fetched_at
    # 设每个 trade_date 的 available_at 为当日 19:00（Tushare 日频数据可得时间）
    df["available_at"] = df["trade_date"].apply(
        lambda d: pd.Timestamp(
            year=d.year, month=d.month, day=d.day,
            hour=19, minute=0, second=0, tz=TIMEZONE
        )
    )
    df["fetched_at"] = fetched_at
    df["source"] = "tushare"
    df["source_version"] = "index_daily_v1"
    df["is_stale"] = False
    df["quality_flags"] = ""
    return df


# ============ Fund nav（ETF 单位净值，用于 s1 ETF flow） ============

def load_fund_nav(
    *,
    codes: list[str],
    start: pd.Timestamp,
    end: pd.Timestamp,
    as_of: pd.Timestamp,
    cache_dir: Path | str | None = None,
    use_cache: bool = True,
) -> pd.DataFrame:
    """加载基金净值数据，落盘 parquet 增量缓存，PIT 过滤。"""
    cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "fund_nav.parquet"

    fetched_at = pd.Timestamp.now(tz=TIMEZONE)
    if use_cache and cache_path.exists():
        cached = pd.read_parquet(cache_path)
        cached = cached[cached["available_at"] <= pd.Timestamp(as_of)]
        cached_codes = set(cached["ts_code"].unique()) if not cached.empty else set()
        missing_codes = [c for c in codes if c not in cached_codes]
        stale_codes = _stale_codes(cached, codes, end, as_of, date_col="nav_date")
        codes_to_refresh = missing_codes + stale_codes
        if not codes_to_refresh:
            return _filter_range(cached, start, end)
        fresh = pull_fund_nav(
            codes=codes_to_refresh,
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
        )
        fresh = _annotate_fund_nav(fresh, fetched_at)
        # Apply PIT filter to fresh data
        fresh = fresh[fresh["available_at"] <= pd.Timestamp(as_of)]
        combined = pd.concat([cached, fresh], ignore_index=True).drop_duplicates(
            subset=["ts_code", "nav_date"], keep="last"
        )
        combined.to_parquet(cache_path, index=False)
        return _filter_range(combined, start, end)

    fresh = pull_fund_nav(
        codes=codes,
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
    )
    fresh = _annotate_fund_nav(fresh, fetched_at)
    # Apply PIT filter to fresh data
    fresh = fresh[fresh["available_at"] <= pd.Timestamp(as_of)]
    # Apply time range filter
    fresh = _filter_range(fresh, start, end)
    if use_cache:
        fresh.to_parquet(cache_path, index=False)
    return fresh


def _annotate_fund_nav(
    df: pd.DataFrame, fetched_at: pd.Timestamp
) -> pd.DataFrame:
    """添加审计列到基金净值数据。

    available_at 设为 nav_date 当日 19:00:00（Tushare 日频数据可得时间）。
    """
    if df.empty:
        return _empty_with_audit()
    df = df.copy()
    df["source_date"] = df["nav_date"]
    df["first_observed_at"] = fetched_at
    # 设每个 nav_date 的 available_at 为当日 19:00（Tushare 日频数据可得时间）
    df["available_at"] = df["nav_date"].apply(
        lambda d: pd.Timestamp(
            year=d.year, month=d.month, day=d.day,
            hour=19, minute=0, second=0, tz=TIMEZONE
        )
    )
    df["fetched_at"] = fetched_at
    df["source"] = "tushare"
    df["source_version"] = "fund_nav_v1"
    df["is_stale"] = False
    df["quality_flags"] = ""
    return df


# ============ 个股两融明细（Phase C：行业热力图源数据） ============

MARGIN_DETAIL_SUFFIXES = (".SH", ".SZ", ".BJ")


def _margin_detail_day_complete(cached: pd.DataFrame) -> bool:
    """个股明细当日缓存是否沪深北三市齐全。

    交易所明细发布有先后（深市常滞后数小时），T+1 早间拉取可能只拿到
    部分市场；缺市文件若"存在即跳过"，创业板线（300/301 全在深市）
    会断流。历史完整交易日均为三市齐全。
    """
    if cached.empty or "ts_code" not in cached.columns:
        return False
    suffixes = set(cached["ts_code"].astype(str).str[-3:])
    return set(MARGIN_DETAIL_SUFFIXES).issubset(suffixes)


def load_margin_detail(
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    as_of: pd.Timestamp,
    cache_dir: Path | str | None = None,
    use_cache: bool = True,
) -> pd.DataFrame:
    """加载个股两融明细，按 trade_date 增量缓存，PIT 过滤。

    每个交易日单独缓存一个 parquet（`margin_detail_YYYYMMDD.parquet`），
    失败一天不影响其他日。空数据日（周末/节假日）落空哨兵文件，
    后续长窗口运行不再重探（否则趋势面板 2 年窗口每次多打数百次 API）。
    缺市的部分缓存（交易所发布滞后所致）在近期重试窗口内重拉补齐，
    超窗则保留事实数据不再重试。
    """
    cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)

    fetched_at = pd.Timestamp.now(tz=TIMEZONE)
    out_frames: list[pd.DataFrame] = []

    # 遍历日历日；margin_detail 接口按 trade_date 拉单日数据，
    # 周末/节假日 Tushare 返回空 df，loader 自然过滤
    for d in pd.date_range(start=pd.Timestamp(start), end=pd.Timestamp(end)):
        cache_path = cache_dir / f"margin_detail_{d.strftime('%Y%m%d')}.parquet"
        if use_cache and cache_path.exists():
            cached = pd.read_parquet(cache_path)
            cached = cached[cached["available_at"] <= as_of]
            if not cached.empty and _margin_detail_day_complete(cached):
                out_frames.append(cached)
                continue
            # 最近交易日的空/缺市结果可能只是上游延迟；近期仍需重试。
            as_of_day = pd.Timestamp(as_of)
            if as_of_day.tzinfo is not None:
                as_of_day = as_of_day.tz_convert(TIMEZONE).tz_localize(None)
            if d.weekday() >= 5 or d < as_of_day.normalize() - pd.Timedelta(days=7):
                # 超窗的部分数据保留事实（缺市日聚合层自会跳过 ALL 行）
                if not cached.empty:
                    out_frames.append(cached)
                continue

        fresh = _pull_margin_detail_for_load(d.strftime("%Y%m%d"))
        if fresh.empty:
            # 该日 19:00 发布时点已过 → 真非交易日，落哨兵防止长窗口反复探测；
            # 未到 19:00 的空结果是"尚未发布"，不落哨兵（否则文件存在即跳过，
            # 当晚 eod_preview 的补拉会被永久阻断）
            day_publish = pd.Timestamp(d.strftime("%Y-%m-%d")) + pd.Timedelta(hours=19)
            as_of_ts = pd.Timestamp(as_of)
            if as_of_ts.tzinfo is not None:
                as_of_ts = as_of_ts.tz_convert(TIMEZONE).tz_localize(None)
            if use_cache and as_of_ts >= day_publish:
                _empty_with_audit().to_parquet(cache_path)
            continue
        fresh = _annotate_margin_detail(fresh, fetched_at)
        fresh = fresh[fresh["available_at"] <= as_of]
        if use_cache:
            fresh.to_parquet(cache_path, index=False)
        if not fresh.empty:
            out_frames.append(fresh)

    if not out_frames:
        return _empty_with_audit()
    return pd.concat(out_frames, ignore_index=True)


def _pull_margin_detail_for_load(trade_date: str) -> pd.DataFrame:
    """Thin wrapper around provider for monkeypatch in tests."""
    return pull_margin_detail(trade_date=trade_date)


def _annotate_margin_detail(
    df: pd.DataFrame, fetched_at: pd.Timestamp
) -> pd.DataFrame:
    """添加审计列。available_at = trade_date 当日 19:00。"""
    if df.empty:
        return _empty_with_audit()
    df = df.copy()
    df["source_date"] = df["trade_date"].dt.strftime("%Y-%m-%d")
    df["first_observed_at"] = fetched_at
    df["available_at"] = df["trade_date"].apply(
        lambda d: pd.Timestamp(
            year=d.year, month=d.month, day=d.day,
            hour=19, minute=0, second=0, tz=TIMEZONE
        )
    )
    df["fetched_at"] = fetched_at
    df["source"] = "tushare"
    df["source_version"] = "margin_detail_v1"
    df["is_stale"] = False
    df["quality_flags"] = ""
    return df
