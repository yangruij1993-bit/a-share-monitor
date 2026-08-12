"""新浪实时 provider。

per spec §3.2.1 契约:
    fetch_snapshot(provider_codes, observed_at) -> QuoteBatch
    load_snapshots(start_at, end_at, as_of, provider_codes=None) -> DataFrame

fetch_snapshot 不读缓存；只在本次网络响应时返回新快照。
load_snapshots 才读历史快照，仍执行 available_at <= as_of 过滤。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

import pandas as pd

from flow_dashboard.config import TIMEZONE
from flow_dashboard.data.sina_client import (
    fetch_futures_node,
    fetch_spot_indices,
    PARSE_VERSION,
)

QUOTE_FIELDS = (
    "provider_code", "quote_time", "last_price",
    "pre_close", "status", "data_mode", "raw",
)


@dataclass
class QuoteBatch:
    provider: str
    observed_at: pd.Timestamp
    received_at: pd.Timestamp
    parse_version: str
    quotes: list[dict]
    failures: list[dict] = field(default_factory=list)


def fetch_snapshot(
    provider_codes: Sequence[str],
    observed_at: pd.Timestamp,
    timeout: float = 6.0,
) -> QuoteBatch:
    """取现货指数快照。provider_codes 形如 ['sh000905', 'sh000852']。

    futures 与 spot 用不同 endpoint；本函数仅处理 spot（IC/IM 期货快照由
    fetch_futures_snapshot 单独提供，因为参数是 variety 而非 provider_code）。
    """
    observed_at = _normalize_tz(observed_at)
    received_at = pd.Timestamp.now(tz=TIMEZONE)
    try:
        raw_df = fetch_spot_indices(provider_codes, timeout=timeout)
    except Exception as exc:
        return QuoteBatch(
            provider="sina",
            observed_at=observed_at,
            received_at=received_at,
            parse_version=PARSE_VERSION,
            quotes=[],
            failures=[{"kind": "network_error", "error": str(exc)}],
        )
    quotes: list[dict] = []
    for _, row in raw_df.iterrows():
        quotes.append({
            "provider_code": row["provider_code"],
            "quote_time": _build_timestamp(row.get("date"), row.get("time")),
            "last_price": float(row["last"]) if pd.notna(row.get("last")) else None,
            "pre_close": float(row["pre_close"]) if pd.notna(row.get("pre_close")) else None,
            "status": "ok" if pd.notna(row.get("last")) else "missing_last",
            "data_mode": "intraday_preview",
            "raw": row.to_dict(),
        })
    return QuoteBatch(
        provider="sina",
        observed_at=observed_at,
        received_at=received_at,
        parse_version=PARSE_VERSION,
        quotes=quotes,
    )


def fetch_futures_snapshot(
    variety: str,
    observed_at: pd.Timestamp,
    timeout: float = 8.0,
) -> QuoteBatch:
    """取一个 CFFEX 品种的全部活跃合约快照（IC/IM/IF/IH）。"""
    observed_at = _normalize_tz(observed_at)
    received_at = pd.Timestamp.now(tz=TIMEZONE)
    try:
        raw_df = fetch_futures_node(variety, timeout=timeout)
    except Exception as exc:
        return QuoteBatch(
            provider="sina",
            observed_at=observed_at,
            received_at=received_at,
            parse_version=PARSE_VERSION,
            quotes=[],
            failures=[{"kind": "network_error", "error": str(exc)}],
        )
    quotes: list[dict] = []
    for _, row in raw_df.iterrows():
        symbol = row.get("symbol")
        provider_code = f"sina_fut_{symbol}"
        quotes.append({
            "provider_code": provider_code,
            "quote_time": _build_timestamp(row.get("tradedate"), row.get("ticktime")),
            "last_price": float(row["trade"]) if pd.notna(row.get("trade")) else None,
            "pre_close": float(row.get("prevsettlement")) if pd.notna(row.get("prevsettlement")) else None,
            "settlement": float(row["settlement"]) if pd.notna(row.get("settlement")) else None,
            "status": "ok" if pd.notna(row.get("trade")) else "missing_trade",
            "data_mode": "intraday_preview",
            "raw": {k: (v if not pd.isna(v) else None) for k, v in row.to_dict().items()},
        })
    return QuoteBatch(
        provider="sina",
        observed_at=observed_at,
        received_at=received_at,
        parse_version=PARSE_VERSION,
        quotes=quotes,
    )


def load_snapshots(
    start_at: pd.Timestamp,
    end_at: pd.Timestamp,
    as_of: pd.Timestamp,
    provider_codes: Sequence[str] | None = None,
    storage_dir: Path | str | None = None,
) -> pd.DataFrame:
    """从 parquet 读历史快照。文件不存在时返回空 DataFrame（含列）。

    per spec §3.2.1: 仍执行 available_at <= as_of 过滤。
    """
    storage_dir = Path(storage_dir) if storage_dir else Path("data/flow_dashboard/sina_snapshots")
    target = storage_dir / "snapshots.parquet"
    cols = list(QUOTE_FIELDS) + ["available_at", "received_at", "observed_at"]
    if not target.exists():
        return pd.DataFrame(columns=cols)
    df = pd.read_parquet(target)
    if "available_at" in df.columns:
        df = df[df["available_at"] <= pd.Timestamp(as_of)]
    if start_at is not None and "quote_time" in df.columns:
        df = df[df["quote_time"] >= pd.Timestamp(start_at)]
    if end_at is not None and "quote_time" in df.columns:
        df = df[df["quote_time"] <= pd.Timestamp(end_at)]
    if provider_codes and "provider_code" in df.columns:
        df = df[df["provider_code"].isin(provider_codes)]
    return df.reset_index(drop=True)


def _normalize_tz(ts: pd.Timestamp) -> pd.Timestamp:
    if ts.tzinfo is None:
        return ts.tz_localize(TIMEZONE)
    return ts.tz_convert(TIMEZONE)


def _build_timestamp(date_str, time_str) -> pd.Timestamp | None:
    if not date_str or not time_str:
        return None
    try:
        return pd.Timestamp(f"{date_str} {time_str}", tz=TIMEZONE)
    except (ValueError, TypeError):
        return None
