"""轮询 etf_share_size 可得性，记录 first_observed_at。

逐函数从 行业轮动/scripts/poll_tushare_etf_share_size.py 迁移：
- 保留 poll_once 的契约与日志格式
- 移除 HUATAI_FLOW_ETF_CODES 静态名单依赖（codes 由 caller 提供）
- 移除主项目 output 路径
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pandas as pd

from flow_dashboard.config import TIMEZONE


def poll_once(
    codes: list[str],
    trade_date: str,
    output_dir: str | Path,
    now: pd.Timestamp | None = None,
    pull_func: Callable[..., pd.DataFrame] | None = None,
) -> dict[str, object]:
    """轮询一次 etf_share_size，追加 summary 并保存当次明细。

    pull_func 默认为 pull_etf_share_size；测试可注入 fake。
    """
    if pull_func is None:
        from flow_dashboard.data.tushare_providers import pull_etf_share_size
        pull_func = pull_etf_share_size

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    poll_time = _normalize_now(now)
    target = _fmt_trade_date(trade_date)
    expected = sorted(codes)

    df = pull_func(expected, start_date=target, end_date=target)
    detail = _filter_target(df, target)

    available = sorted(set(detail.get("ts_code", pd.Series(dtype=str)).dropna()))
    missing = sorted(set(expected) - set(available))
    latest = _latest_trade_date(df)
    n_avail = len(available)
    n_expected = len(expected)
    coverage = n_avail / n_expected if n_expected else 0.0
    status = "complete" if n_avail == n_expected else ("missing" if n_avail == 0 else "partial")

    summary = {
        "poll_time": poll_time.isoformat(),
        "trade_date": target,
        "status": status,
        "expected_count": n_expected,
        "available_count": n_avail,
        "coverage_rate": coverage,
        "latest_trade_date": latest,
        "missing_codes": ",".join(missing),
    }
    _append_summary(out_path / "poll_summary.csv", summary)
    detail_path = out_path / f"poll_detail_{target}_{poll_time.strftime('%H%M%S')}.csv"
    detail.to_csv(detail_path, index=False, encoding="utf-8-sig")
    return summary


def _normalize_now(now: pd.Timestamp | None) -> pd.Timestamp:
    if now is None:
        return pd.Timestamp.now(tz=TIMEZONE)
    s = pd.Timestamp(now)
    if s.tzinfo is None:
        return s.tz_localize(TIMEZONE)
    return s.tz_convert(TIMEZONE)


def _fmt_trade_date(value: str) -> str:
    return pd.Timestamp(value).strftime("%Y%m%d")


def _filter_target(df: pd.DataFrame, target: str) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["trade_date", "ts_code"])
    out = df.copy()
    if "trade_date" not in out.columns:
        return pd.DataFrame(columns=out.columns)
    norm = pd.to_datetime(out["trade_date"], errors="coerce").dt.strftime("%Y%m%d")
    return out[norm == target].sort_values("ts_code").reset_index(drop=True)


def _latest_trade_date(df: pd.DataFrame) -> str:
    if df is None or df.empty or "trade_date" not in df.columns:
        return ""
    dates = pd.to_datetime(df["trade_date"], errors="coerce").dropna()
    if dates.empty:
        return ""
    return dates.max().strftime("%Y%m%d")


def _append_summary(path: Path, summary: dict[str, object]) -> None:
    row = pd.DataFrame([summary])
    header = not path.exists()
    row.to_csv(path, mode="a", header=header, index=False, encoding="utf-8-sig")
