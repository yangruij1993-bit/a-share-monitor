# src/flow_dashboard/data/sw_l1_members.py
"""申万一级 28 个行业成分股 PIT loader。

per spec §3.2.1 loader 契约:
- 返回 DataFrame 含 schema.AUDIT_COLUMNS
- parquet 缓存（成分股一年只更新 1-2 次，可长期缓存）
- 不做 available_at 过滤（成分股的 in_date/out_date 即 PIT 字段，由 pivot 时过滤）

PIT 关键：用 in_date <= trade_date <= (out_date or MAX) 决定某天的成分股，
不能用"今天的归属"回填历史。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from flow_dashboard.config import CACHE_DIR, TIMEZONE
from flow_dashboard.data.schema import AUDIT_COLUMNS
from flow_dashboard.data.tushare_providers import pull_index_member


SW_L1_INDUSTRIES: tuple[tuple[str, str], ...] = (
    ("801010", "农林牧渔"), ("801030", "基础化工"), ("801040", "钢铁"),
    ("801050", "有色金属"), ("801080", "电子"),     ("801110", "家用电器"),
    ("801120", "食品饮料"), ("801150", "纺织服饰"), ("801160", "轻工制造"),
    ("801170", "医药生物"), ("801180", "建筑装饰"), ("801200", "商贸零售"),
    ("801210", "社会服务"), ("801230", "综合"),     ("801710", "建筑材料"),
    ("801720", "电力设备"), ("801730", "国防军工"), ("801740", "计算机"),
    ("801750", "传媒"),     ("801760", "通信"),     ("801770", "银行"),
    ("801780", "非银金融"), ("801790", "机械设备"), ("801880", "汽车"),
    ("801890", "交通运输"), ("801950", "煤炭"),     ("801960", "石油石化"),
    ("801970", "环保"),
)

# Tushare 用空字符串表示"当前在册"；pivot 时替换为远未来日期以通过 <= 过滤。
# 选 2099-12-31 避免与任何真实 out_date 冲突。
_FAR_FUTURE_DATE = "20991231"


def load_sw_l1_members(
    *,
    cache_dir: Path | str | None = None,
    use_cache: bool = True,
) -> pd.DataFrame:
    """加载 28 个申万一级行业的成分股 PIT 表。

    Returns:
        DataFrame[index_code, industry_code, industry_name, con_code,
                  in_date, out_date, is_new, *AUDIT_COLUMNS]
    """
    cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "sw_l1_members.parquet"

    if use_cache and cache_path.exists():
        return pd.read_parquet(cache_path)

    frames: list[pd.DataFrame] = []
    for industry_code, industry_name in SW_L1_INDUSTRIES:
        index_code = f"{industry_code}.SI"
        raw = pull_index_member(index_code=index_code)
        if raw.empty:
            continue
        raw = raw.copy()
        raw["industry_code"] = industry_code
        raw["industry_name"] = industry_name
        frames.append(raw)

    if not frames:
        return _empty_with_audit()

    df = pd.concat(frames, ignore_index=True)
    df = _annotate_audit(df)
    df.to_parquet(cache_path, index=False)
    return df


def pivot_to_daily_membership(
    members: pd.DataFrame,
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """把成分股 PIT 表展开为每日成员表。

    对每个 (trade_date in [start, end]) × (con_code in members)，
    若 in_date <= trade_date <= (out_date or MAX)，则该股该日在册。

    Returns:
        DataFrame[trade_date, con_code, industry_code, industry_name]
    """
    if members.empty:
        return pd.DataFrame(
            columns=["trade_date", "con_code", "industry_code", "industry_name"]
        )

    df = members.copy()
    df["in_date"] = pd.to_datetime(df["in_date"])
    # 当前在册的股票 out_date 为 NaN 或空串；都视为"未退出"= FAR_FUTURE_DATE。
    # 否则 pd.to_datetime(NaN) → NaT，比较 NaT >= d 返回 False，会把所有在册股票
    # 从所有日期的成员表中排除，导致行业聚合在某个日期后突然变空。
    out_clean = df["out_date"].astype("object").where(
        df["out_date"].notna() & (df["out_date"] != ""), _FAR_FUTURE_DATE
    )
    df["out_date_resolved"] = pd.to_datetime(out_clean)

    # 生成交易日序列（粗粒度：按日历日；后续 loader 用 margin_detail 的 trade_date 过滤）
    dates = pd.date_range(start=pd.Timestamp(start), end=pd.Timestamp(end), freq="D")

    out_frames: list[pd.DataFrame] = []
    for d in dates:
        mask = (df["in_date"] <= d) & (df["out_date_resolved"] >= d)
        active = df[mask]
        if active.empty:
            continue
        row = active[["con_code", "industry_code", "industry_name"]].copy()
        row["trade_date"] = d.strftime("%Y-%m-%d")
        out_frames.append(row)

    if not out_frames:
        return pd.DataFrame(
            columns=["trade_date", "con_code", "industry_code", "industry_name"]
        )
    return pd.concat(out_frames, ignore_index=True)


def _annotate_audit(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    fetched_at = pd.Timestamp.now(tz=TIMEZONE)
    df["source_date"] = fetched_at.strftime("%Y-%m-%d")
    df["first_observed_at"] = fetched_at
    df["available_at"] = fetched_at
    df["fetched_at"] = fetched_at
    df["source"] = "tushare"
    df["source_version"] = "index_member_sw_l1_v1"
    df["is_stale"] = False
    df["quality_flags"] = ""
    return df


def _empty_with_audit() -> pd.DataFrame:
    cols = [
        "index_code", "industry_code", "industry_name", "con_code",
        "in_date", "out_date", "is_new", *AUDIT_COLUMNS,
    ]
    return pd.DataFrame(columns=cols)
