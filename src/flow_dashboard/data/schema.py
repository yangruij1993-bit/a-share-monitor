"""Schema 契约：落盘表必填审计列与质量标记枚举。

Per spec §1.3:
- 每个落盘表必须保留 source_date, first_observed_at, available_at, fetched_at,
  source, source_version, is_stale, quality_flags。
- quality_flags 是已知标记的字符串集合（用 ";" 分隔多值）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

AUDIT_COLUMNS: tuple[str, ...] = (
    "source_date",
    "first_observed_at",
    "available_at",
    "fetched_at",
    "source",
    "source_version",
    "is_stale",
    "quality_flags",
)

QUALITY_FLAGS: frozenset[str] = frozenset({
    "source_switch_break",
    "quote_time_unverified",
    "reconstructed_history",
    "restated",
    "stale",
    "partial",
    "unsynchronized",
    "missing_nav",
    "out_of_tolerance",
})


@dataclass(frozen=True)
class SchemaReport:
    ok: bool
    missing: tuple[str, ...]


def validate_audit_columns(df, columns: Iterable[str] = AUDIT_COLUMNS) -> SchemaReport:
    """检查 df 是否含全部审计列；返回缺失列表。"""
    required = tuple(columns)
    missing = tuple(c for c in required if c not in df.columns)
    return SchemaReport(ok=not missing, missing=missing)
