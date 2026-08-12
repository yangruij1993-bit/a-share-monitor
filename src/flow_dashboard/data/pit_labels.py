"""ETF 多维 PIT 标签表。

per spec §1.1: 同一 ETF 可在不同维度（ownership/asset_scope/benchmark/strategy/theme）
同时拥有多个标签；标签有 effective_from/effective_to 区间。
所有聚合必须指定 dimension + label，不依赖隐式优先级。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from flow_dashboard.config import TIMEZONE

PIT_LABEL_COLUMNS: tuple[str, ...] = (
    "ts_code", "dimension", "label",
    "effective_from", "effective_to",
    "evidence_source", "confirmed_at",
)

_DIMENSIONS = ("ownership", "asset_scope", "benchmark", "strategy", "theme")


def load_pit_labels(path: Path | str) -> pd.DataFrame:
    """加载 PIT 标签表。强制列类型校验。"""
    df = pd.read_csv(path)
    missing = [c for c in PIT_LABEL_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"PIT 标签表缺列: {missing}")
    df["effective_from"] = pd.to_datetime(df["effective_from"], errors="coerce")
    df["effective_to"] = pd.to_datetime(df["effective_to"], errors="coerce")
    df["confirmed_at"] = pd.to_datetime(df["confirmed_at"], errors="coerce", utc=True)
    if df["confirmed_at"].dt.tz is None:
        df["confirmed_at"] = df["confirmed_at"].dt.tz_convert(TIMEZONE)
    invalid_dims = set(df["dimension"].unique()) - set(_DIMENSIONS)
    if invalid_dims:
        raise ValueError(f"未知 dimension: {invalid_dims}; 允许: {_DIMENSIONS}")
    return df


def filter_effective(
    df: pd.DataFrame,
    ts_code: str | None = None,
    dimension: str | None = None,
    label: str | None = None,
    at: pd.Timestamp | None = None,
) -> pd.DataFrame:
    """按 PIT 区间过滤。区间是左闭右开 [effective_from, effective_to)。

    effective_to 为 NaT 视为尚未失效。
    """
    out = df
    if ts_code is not None:
        out = out[out["ts_code"] == ts_code]
    if dimension is not None:
        out = out[out["dimension"] == dimension]
    if label is not None:
        out = out[out["label"] == label]
    if at is not None:
        at = pd.Timestamp(at)
        if at.tzinfo is None:
            at = at.tz_localize(TIMEZONE)
        else:
            at = at.tz_convert(TIMEZONE)
        ef = out["effective_from"]
        if ef.dt.tz is None:
            ef = ef.dt.tz_localize(TIMEZONE)
        else:
            ef = ef.dt.tz_convert(TIMEZONE)
        from_ok = ef <= at
        to_naive = out["effective_to"].isna()
        et = out["effective_to"]
        if et.dt.tz is None:
            et = et.dt.tz_localize(TIMEZONE)
        else:
            et = et.dt.tz_convert(TIMEZONE)
        to_ok = to_naive | (et > at)
        out = out[from_ok & to_ok]
    return out.reset_index(drop=True)
