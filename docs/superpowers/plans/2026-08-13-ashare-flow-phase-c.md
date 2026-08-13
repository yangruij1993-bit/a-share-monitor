# A 股 ETF 资金流监控 Phase C — 个股两融行业热力图 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 Phase B 已有的 15 面板日报里新增第 16 块面板——"个股两融按申万 L1 行业热力图"，28 行业 × 30 个交易日，颜色编码净融资余额 5 日变化（正=红、负=绿）。

**Architecture:**
1. 新增 data layer：`load_sw_l1_members`（申万一级成分股 PIT 表，parquet 缓存）+ `pull_margin_detail` / `load_margin_detail`（个股两融明细）。
2. 新增 indicator：`aggregate_margin_by_industry`（个股两融 × 行业 PIT 聚合成 28×N 表）+ `compute_net_margin_change`（5 日净融资变化）。
3. 新增 render：`industry_heatmap_panel`（plotly heatmap figure factory）+ `render_margin_industry_heatmap`（面板 renderer，含 stale fallback）。
4. Pipeline 接入：`_run_eod_preview_inner` 第 16 块面板；manifest panel_ids 加 `panel-margin-industry-heatmap`。

**Tech Stack:** pandas 2.x、plotly、tushare、parquet、pytest（continues Phase A/B pattern）。

**Spec reference:** `docs/资金流跟踪/2026-08-12-ashare-flow-daily-design.md` §5 Phase C 启动条件 + §3.5 共通验收。

---

## Carry-Forward Constraints (从 Phase B 继承，所有任务必须遵守)

1. **Token 解耦（spec §3.2.1）**：所有 Tushare 调用经 `flow_dashboard.data.tushare_client.get_pro_api()`，环境变量读 `ASHARE_FLOW_TUSHARE_TOKEN`（不是 `TUSHARE_TOKEN`）。
2. **Loader 契约（spec §3.2.1）**：所有 loader 必须返回含 `schema.AUDIT_COLUMNS` 的 DataFrame，并执行 `available_at <= as_of` 过滤。
3. **PIT 过滤**：申万成分股用 `in_date <= trade_date <= out_date`（`out_date` 为空表示当前在册）；不能用"今天的归属"回填历史。
4. **HTML escape**：所有插值字符串经 `from html import escape`。
5. **测试目录禁止 `__init__.py`**（Phase A LESSON）。
6. **使用 `python3 -m pytest`**（不是 bare `pytest`）。
7. **Stale 显式**：上游为空 / coverage=None 时面板必须显式 stale，不渲染空 figure。
8. **不调生成式模型（spec §3.6）**：颜色/数值都是规则计算，不调 LLM 写投资判断。
9. **本地 git**：直接 commit 到 main，无 remote。
10. **逐 task TDD + commit**：每个 task 先写失败测试，再实现，再 commit。

---

## File Structure（新增 / 修改）

### 新增文件

| 路径 | 责任 |
|---|---|
| `src/flow_dashboard/data/sw_l1_members.py` | 申万一级 28 个行业成分股 PIT 表 loader（含 parquet 缓存） |
| `src/flow_dashboard/render/panels_margin_industry.py` | 行业热力图面板 renderer（单文件，stale fallback） |
| `tests/flow_dashboard/data/test_sw_l1_members.py` | 申万成分股 loader 测试（含 PIT 边界） |
| `tests/flow_dashboard/data/test_load_margin_detail.py` | 个股两融 loader 测试 |
| `tests/flow_dashboard/indicators/test_margin_industry.py` | 行业聚合 + 净融资变化 indicator 测试 |
| `tests/flow_dashboard/render/test_industry_heatmap.py` | 热力图 figure factory + 面板 renderer 测试 |

### 修改文件

| 路径 | 修改 |
|---|---|
| `src/flow_dashboard/data/tushare_providers.py` | 新增 `pull_margin_detail(trade_date)` + `pull_index_member(index_code)` |
| `src/flow_dashboard/data/loaders.py` | 新增 `load_margin_detail(start, end, as_of)` |
| `src/flow_dashboard/indicators/margin.py` | 新增 `aggregate_margin_by_industry` + `compute_net_margin_change` |
| `src/flow_dashboard/render/figures.py` | 新增 `industry_heatmap_panel` figure factory |
| `src/flow_dashboard/pipeline.py` | `_run_eod_preview_inner` 加载热力图面板 + manifest panel_ids 加 `panel-margin-industry-heatmap` |
| `docs/资金流跟踪/phase_b_gate_report.md` | §1 表加 16 行；§6 测试计数更新；新增 §9 "Phase C 增量" |

---

## 申万一级 28 个行业代码表（hard-coded constant）

写到 `src/flow_dashboard/data/sw_l1_members.py` 里：

```python
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
```

---

## Task 1: 申万一级成分股 PIT loader

**Files:**
- Create: `src/flow_dashboard/data/sw_l1_members.py`
- Create: `tests/flow_dashboard/data/test_sw_l1_members.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/flow_dashboard/data/test_sw_l1_members.py
"""申万一级成分股 PIT loader 测试。"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pandas as pd
import pytest

from flow_dashboard.data.sw_l1_members import (
    SW_L1_INDUSTRIES,
    load_sw_l1_members,
    pivot_to_daily_membership,
)


def _fake_index_member(index_code: str) -> pd.DataFrame:
    """模拟 pro.index_member 返回。"""
    return pd.DataFrame([
        {"index_code": index_code, "con_code": "000001.SZ",
         "in_date": "20100101", "out_date": "", "is_new": "Y"},
        {"index_code": index_code, "con_code": "600000.SH",
         "in_date": "20100101", "out_date": "20200101", "is_new": "N"},
    ])


def test_sw_l1_industries_has_28_codes():
    assert len(SW_L1_INDUSTRIES) == 28
    codes = [c for c, _ in SW_L1_INDUSTRIES]
    assert "801010" in codes and "801970" in codes


def test_load_sw_l1_members_calls_28_index_codes(tmp_path):
    """loader 应该对 28 个 index_code 各调一次 pull_index_member。"""
    cache_dir = tmp_path / "cache"
    with patch(
        "flow_dashboard.data.sw_l1_members.pull_index_member",
        side_effect=_fake_index_member,
    ) as mock:
        df = load_sw_l1_members(cache_dir=cache_dir, use_cache=False)
    assert mock.call_count == 28
    # 28 行业 × 2 成分股 = 56 行
    assert len(df) == 56


def test_load_sw_l1_members_writes_parquet_cache(tmp_path):
    cache_dir = tmp_path / "cache"
    with patch(
        "flow_dashboard.data.sw_l1_members.pull_index_member",
        side_effect=_fake_index_member,
    ):
        load_sw_l1_members(cache_dir=cache_dir, use_cache=False)
    cache_path = cache_dir / "sw_l1_members.parquet"
    assert cache_path.exists()


def test_load_sw_l1_members_uses_cache_on_second_call(tmp_path):
    cache_dir = tmp_path / "cache"
    with patch(
        "flow_dashboard.data.sw_l1_members.pull_index_member",
        side_effect=_fake_index_member,
    ) as mock:
        load_sw_l1_members(cache_dir=cache_dir, use_cache=False)
        # 第二次：默认 use_cache=True，不应该再调 API
        load_sw_l1_members(cache_dir=cache_dir)
    assert mock.call_count == 28  # 仍是 28，不是 56


def test_load_sw_l1_members_has_audit_columns(tmp_path):
    with patch(
        "flow_dashboard.data.sw_l1_members.pull_index_member",
        side_effect=_fake_index_member,
    ):
        df = load_sw_l1_members(cache_dir=tmp_path, use_cache=False)
    from flow_dashboard.data.schema import AUDIT_COLUMNS
    for col in AUDIT_COLUMNS:
        assert col in df.columns, f"missing audit column: {col}"


def test_pivot_to_daily_membership_pit_correct():
    """PIT 关键测试：2020-01-02 时，已退出成分（out_date=2020-01-01）不应在册。"""
    members = pd.DataFrame([
        {"index_code": "801010.SI", "con_code": "000001.SZ",
         "in_date": "20100101", "out_date": "", "is_new": "Y"},
        {"index_code": "801010.SI", "con_code": "600000.SH",
         "in_date": "20100101", "out_date": "20200101", "is_new": "N"},
    ])
    daily = pivot_to_daily_membership(
        members,
        start=pd.Timestamp("2020-01-02"),
        end=pd.Timestamp("2020-01-03"),
    )
    # 2020-01-02: 000001.SZ 在册，600000.SH 已退出
    rows_0102 = daily[daily["trade_date"] == "2020-01-02"]
    assert (rows_0102["con_code"] == "000001.SZ").any()
    assert (rows_0102["con_code"] == "600000.SH").sum() == 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/flow_dashboard/data/test_sw_l1_members.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'flow_dashboard.data.sw_l1_members'`.

- [ ] **Step 3: Write the implementation**

```python
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
    # out_date 为空表示当前在册，用 end+1day 占位
    df["out_date_resolved"] = pd.to_datetime(
        df["out_date"].replace("", "20991231")
    )

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
```

Also add `pull_index_member` to `src/flow_dashboard/data/tushare_providers.py`:

```python
# Append to tushare_providers.py
def pull_index_member(index_code: str) -> pd.DataFrame:
    """拉取指数成分股（含历史进出，PIT 字段）。

    Args:
        index_code: 如 '801010.SI'（申万一级农林牧渔）

    Returns columns: index_code, con_code, in_date, out_date, is_new
    """
    pro = get_pro_api()
    df = pro.index_member(index_code=index_code)
    if df is None or df.empty:
        return pd.DataFrame(
            columns=["index_code", "con_code", "in_date", "out_date", "is_new"]
        )
    return df[["index_code", "con_code", "in_date", "out_date", "is_new"]]
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/flow_dashboard/data/test_sw_l1_members.py -v
```

Expected: 6/6 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/data/sw_l1_members.py \
        src/flow_dashboard/data/tushare_providers.py \
        tests/flow_dashboard/data/test_sw_l1_members.py
git commit -m "feat(phase-c): SW L1 members PIT loader (28 industries, parquet cache)"
```

---

## Task 2: 个股两融 provider + loader

**Files:**
- Modify: `src/flow_dashboard/data/tushare_providers.py` (append `pull_margin_detail`)
- Modify: `src/flow_dashboard/data/loaders.py` (append `load_margin_detail`)
- Create: `tests/flow_dashboard/data/test_load_margin_detail.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/flow_dashboard/data/test_load_margin_detail.py
"""个股两融明细 loader 测试。"""
from __future__ import annotations

from unittest.mock import patch

import pandas as pd
import pytest

from flow_dashboard.data.loaders import load_margin_detail


def _fake_margin_detail(trade_date: str) -> pd.DataFrame:
    return pd.DataFrame([
        {"trade_date": trade_date, "ts_code": "000001.SZ",
         "rzye": 1e9, "rqye": 1e8, "rzmre": 1e8, "rqyl": 1e7},
        {"trade_date": trade_date, "ts_code": "600000.SH",
         "rzye": 2e9, "rqye": 2e8, "rzmre": 2e8, "rqyl": 2e7},
    ])


def test_load_margin_detail_pulls_each_trade_date(tmp_path):
    """loader 应该对区间内每个 trade_date 调一次 pull_margin_detail。"""
    start = pd.Timestamp("2026-08-07")
    end = pd.Timestamp("2026-08-11")
    with patch(
        "flow_dashboard.data.tushare_providers.pull_margin_detail",
        side_effect=_fake_margin_detail,
    ) as mock:
        df = load_margin_detail(
            start=start, end=end,
            as_of=pd.Timestamp("2026-08-12"),
            cache_dir=tmp_path, use_cache=False,
        )
    # 5 个交易日 (08-07, 08-08, 08-10, 08-11, 加 08-09 周末会被 loader 过滤掉)
    # 但 loader 不知道交易日历，所以会拉 5 个日历日；让 loader 内部按 trade_date 拉所有日
    # 简化：每个日历日 1 次 = 5 次
    assert mock.call_count == 5
    assert len(df) == 10  # 5 days × 2 stocks


def test_load_margin_detail_has_audit_columns(tmp_path):
    with patch(
        "flow_dashboard.data.tushare_providers.pull_margin_detail",
        side_effect=_fake_margin_detail,
    ):
        df = load_margin_detail(
            start=pd.Timestamp("2026-08-07"),
            end=pd.Timestamp("2026-08-11"),
            as_of=pd.Timestamp("2026-08-12"),
            cache_dir=tmp_path, use_cache=False,
        )
    from flow_dashboard.data.schema import AUDIT_COLUMNS
    for col in AUDIT_COLUMNS:
        assert col in df.columns


def test_load_margin_detail_available_at_filter(tmp_path):
    """available_at > as_of 的行应该被过滤掉。"""
    as_of = pd.Timestamp("2026-08-12 12:00")
    with patch(
        "flow_dashboard.data.tushare_providers.pull_margin_detail",
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
    with patch(
        "flow_dashboard.data.tushare_providers.pull_margin_detail",
        side_effect=_fake_margin_detail,
    ) as mock:
        load_margin_detail(
            start=pd.Timestamp("2026-08-07"),
            end=pd.Timestamp("2026-08-11"),
            as_of=pd.Timestamp("2026-08-12"),
            cache_dir=tmp_path, use_cache=False,
        )
        load_margin_detail(
            start=pd.Timestamp("2026-08-07"),
            end=pd.Timestamp("2026-08-11"),
            as_of=pd.Timestamp("2026-08-12"),
            cache_dir=tmp_path,  # use_cache=True default
        )
    # 5 个 trade_date 只在第一次调；第二次走缓存
    assert mock.call_count == 5
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/flow_dashboard/data/test_load_margin_detail.py -v
```

Expected: FAIL with `ImportError: cannot import name 'load_margin_detail'`.

- [ ] **Step 3: Write the implementation**

Append to `src/flow_dashboard/data/tushare_providers.py`:

```python
def pull_margin_detail(trade_date: str) -> pd.DataFrame:
    """拉取个股两融明细（单日）。

    Args:
        trade_date: 'YYYYMMDD' 字符串

    Returns columns: trade_date, ts_code, rzye, rqye, rzmre, rqyl, rzche, rqchl, rqmcl, rzrqye
                     （单位：元；rzye=融资余额, rqye=融券余额, rzmre=融资买入额,
                       rqyl=融券卖出额, rzche=融资偿还额, rqchl=融券偿还额）
    """
    pro = get_pro_api()
    df = pro.margin_detail(trade_date=trade_date)
    if df is None or df.empty:
        return pd.DataFrame(columns=[
            "trade_date", "ts_code", "rzye", "rqye", "rzmre", "rqyl",
        ])
    df = df.copy()
    df["trade_date"] = _parse_mixed_date(df["trade_date"])
    for col in ("rzye", "rqye", "rzmre", "rqyl", "rzche", "rqchl", "rqmcl", "rzrqye"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df
```

Append to `src/flow_dashboard/data/loaders.py`:

```python
# ============ 个股两融明细（Phase C：行业热力图源数据） ============

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
    失败一天不影响其他日。
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
            cached = cached[cached["available_at"] <= pd.Timestamp(as_of)]
            if not cached.empty:
                out_frames.append(cached)
                continue

        fresh = pull_margin_detail(trade_date=d.strftime("%Y%m%d"))
        if fresh.empty:
            continue
        fresh = _annotate_margin_detail(fresh, fetched_at)
        fresh = fresh[fresh["available_at"] <= pd.Timestamp(as_of)]
        if use_cache:
            fresh.to_parquet(cache_path, index=False)
        if not fresh.empty:
            out_frames.append(fresh)

    if not out_frames:
        return _empty_with_audit()
    return pd.concat(out_frames, ignore_index=True)


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
```

Also add `pull_margin_detail` to the imports at the top of `loaders.py`:

```python
from flow_dashboard.data.tushare_providers import (
    pull_etf_share_size,
    pull_margin,
    pull_margin_detail,  # NEW
    pull_fut_daily,
    pull_index_daily,
    pull_fund_nav,
)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/flow_dashboard/data/test_load_margin_detail.py -v
```

Expected: 4/4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/data/tushare_providers.py \
        src/flow_dashboard/data/loaders.py \
        tests/flow_dashboard/data/test_load_margin_detail.py
git commit -m "feat(phase-c): per-stock margin_detail loader (per-day parquet cache)"
```

---

## Task 3: 行业聚合 indicator（aggregate_margin_by_industry）

**Files:**
- Modify: `src/flow_dashboard/indicators/margin.py` (append `aggregate_margin_by_industry`)
- Create: `tests/flow_dashboard/indicators/test_margin_industry.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/flow_dashboard/indicators/test_margin_industry.py
"""行业聚合 indicator 测试。"""
from __future__ import annotations

import pandas as pd
import pytest

from flow_dashboard.indicators.margin import aggregate_margin_by_industry


def _margin_df():
    """2 只股票 × 2 天的个股两融。"""
    return pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "ts_code": "000001.SZ",
         "rzye": 1e9, "rqye": 1e8},
        {"trade_date": pd.Timestamp("2026-08-07"), "ts_code": "600000.SH",
         "rzye": 2e9, "rqye": 2e8},
        {"trade_date": pd.Timestamp("2026-08-08"), "ts_code": "000001.SZ",
         "rzye": 1.1e9, "rqye": 1.1e8},
        {"trade_date": pd.Timestamp("2026-08-08"), "ts_code": "600000.SH",
         "rzye": 2.1e9, "rqye": 2.1e8},
    ])


def _members_daily():
    """PIT 展开：2 只股票分别属于不同行业。"""
    return pd.DataFrame([
        {"trade_date": "2026-08-07", "con_code": "000001.SZ",
         "industry_code": "801770", "industry_name": "银行"},
        {"trade_date": "2026-08-07", "con_code": "600000.SH",
         "industry_code": "801780", "industry_name": "非银金融"},
        {"trade_date": "2026-08-08", "con_code": "000001.SZ",
         "industry_code": "801770", "industry_name": "银行"},
        {"trade_date": "2026-08-08", "con_code": "600000.SH",
         "industry_code": "801780", "industry_name": "非银金融"},
    ])


def test_aggregate_margin_by_industry_basic():
    out = aggregate_margin_by_industry(_margin_df(), _members_daily())
    # 2 行业 × 2 天 = 4 行
    assert len(out) == 4
    # 银行 08-07：rzye=1e9, rqye=1e8
    row = out[(out["industry_code"] == "801770") & (out["trade_date"] == pd.Timestamp("2026-08-07"))].iloc[0]
    assert row["rzye"] == 1e9
    assert row["rqye"] == 1e8


def test_aggregate_margin_by_industry_groups_correctly():
    """同一行业多只股票应聚合。"""
    margin = pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "ts_code": "000001.SZ",
         "rzye": 1e9, "rqye": 1e8},
        {"trade_date": pd.Timestamp("2026-08-07"), "ts_code": "000002.SZ",
         "rzye": 2e9, "rqye": 2e8},
    ])
    members = pd.DataFrame([
        {"trade_date": "2026-08-07", "con_code": "000001.SZ",
         "industry_code": "801770", "industry_name": "银行"},
        {"trade_date": "2026-08-07", "con_code": "000002.SZ",
         "industry_code": "801770", "industry_name": "银行"},
    ])
    out = aggregate_margin_by_industry(margin, members)
    # 1 行业 × 1 天 = 1 行，rzye 求和 = 3e9
    assert len(out) == 1
    assert out.iloc[0]["rzye"] == 3e9


def test_aggregate_margin_by_industry_pit_membership_change():
    """PIT 关键：股票 08-08 起换行业，应分别计入。"""
    margin = pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "ts_code": "000001.SZ",
         "rzye": 1e9, "rqye": 1e8},
        {"trade_date": pd.Timestamp("2026-08-08"), "ts_code": "000001.SZ",
         "rzye": 2e9, "rqye": 2e8},
    ])
    members = pd.DataFrame([
        {"trade_date": "2026-08-07", "con_code": "000001.SZ",
         "industry_code": "801770", "industry_name": "银行"},
        {"trade_date": "2026-08-08", "con_code": "000001.SZ",
         "industry_code": "801780", "industry_name": "非银金融"},
    ])
    out = aggregate_margin_by_industry(margin, members)
    bank_0807 = out[(out["industry_code"] == "801770") & (out["trade_date"] == pd.Timestamp("2026-08-07"))]
    nonbank_0808 = out[(out["industry_code"] == "801780") & (out["trade_date"] == pd.Timestamp("2026-08-08"))]
    assert len(bank_0807) == 1 and bank_0807.iloc[0]["rzye"] == 1e9
    assert len(nonbank_0808) == 1 and nonbank_0808.iloc[0]["rzye"] == 2e9


def test_aggregate_margin_by_industry_drops_stocks_without_industry():
    """个股两融里有但申万成分股里没有的股票（如新股），应被忽略 + 不抛错。"""
    margin = pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "ts_code": "NEW.SZ",
         "rzye": 1e9, "rqye": 1e8},
    ])
    members = pd.DataFrame(
        columns=["trade_date", "con_code", "industry_code", "industry_name"]
    )
    out = aggregate_margin_by_industry(margin, members)
    assert out.empty
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/flow_dashboard/indicators/test_margin_industry.py -v
```

Expected: FAIL with `ImportError: cannot import name 'aggregate_margin_by_industry'`.

- [ ] **Step 3: Write the implementation**

Append to `src/flow_dashboard/indicators/margin.py`:

```python
def aggregate_margin_by_industry(
    margin_df: pd.DataFrame,
    members_daily: pd.DataFrame,
) -> pd.DataFrame:
    """按申万 L1 行业聚合个股两融。

    PIT 关键：用 members_daily（每日成分表）决定每只股票该日属于哪个行业，
    不用"今天的归属"。

    Args:
        margin_df: 个股两融明细，含 trade_date, ts_code, rzye, rqye
        members_daily: 每日成分股，含 trade_date, con_code, industry_code, industry_name

    Returns:
        DataFrame[trade_date, industry_code, industry_name,
                  rzye, rqye, net_margin (= rzye - rqye), stock_count]
    """
    if margin_df.empty or members_daily.empty:
        return pd.DataFrame(columns=[
            "trade_date", "industry_code", "industry_name",
            "rzye", "rqye", "net_margin", "stock_count",
        ])

    # 对齐 trade_date 类型为 datetime
    margin = margin_df.copy()
    margin["trade_date"] = pd.to_datetime(margin["trade_date"])
    members = members_daily.copy()
    members["trade_date"] = pd.to_datetime(members["trade_date"])

    # 内连接：股票两融 × 行业归属
    merged = margin.merge(
        members,
        left_on=["trade_date", "ts_code"],
        right_on=["trade_date", "con_code"],
        how="inner",
    )
    if merged.empty:
        return pd.DataFrame(columns=[
            "trade_date", "industry_code", "industry_name",
            "rzye", "rqye", "net_margin", "stock_count",
        ])

    # 按行业 × 日期聚合
    agg = merged.groupby(
        ["trade_date", "industry_code", "industry_name"], as_index=False
    ).agg(
        rzye=("rzye", "sum"),
        rqye=("rqye", "sum"),
        stock_count=("ts_code", "count"),
    )
    agg["net_margin"] = agg["rzye"] - agg["rqye"]
    return agg.sort_values(
        ["trade_date", "industry_code"]
    ).reset_index(drop=True)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/flow_dashboard/indicators/test_margin_industry.py -v
```

Expected: 4/4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/indicators/margin.py \
        tests/flow_dashboard/indicators/test_margin_industry.py
git commit -m "feat(phase-c): aggregate_margin_by_industry indicator with PIT membership"
```

---

## Task 4: 净融资余额 5 日变化 indicator（compute_net_margin_change）

**Files:**
- Modify: `src/flow_dashboard/indicators/margin.py` (append `compute_net_margin_change`)
- Modify: `tests/flow_dashboard/indicators/test_margin_industry.py` (append tests)

- [ ] **Step 1: Write the failing test**

Append to `tests/flow_dashboard/indicators/test_margin_industry.py`:

```python
from flow_dashboard.indicators.margin import (
    aggregate_margin_by_industry,
    compute_net_margin_change,
)


def _industry_df():
    """1 行业 × 7 天的聚合表（用于测 5 日变化）。"""
    rows = []
    base = pd.Timestamp("2026-08-01")
    for i in range(7):
        rows.append({
            "trade_date": base + pd.Timedelta(days=i),
            "industry_code": "801770",
            "industry_name": "银行",
            "rzye": 1e9 + i * 1e8,  # 每日 +1e8
            "rqye": 1e8 + i * 1e7,
            "net_margin": (1e9 + i * 1e8) - (1e8 + i * 1e7),
            "stock_count": 10,
        })
    return pd.DataFrame(rows)


def test_compute_net_margin_change_5d():
    df = compute_net_margin_change(_industry_df(), n_trading_days=5)
    # 前 5 天变化为 NaN（无 t-5）；第 6、7 天有变化
    assert df["net_margin_5d_change"].isna().sum() == 5
    # 第 7 天（i=6）：net_margin(t) - net_margin(t-5) = (1.6e9 - 1.1e8) - (1e9 - 1e8) = 5.9e8
    row_7 = df[df["trade_date"] == pd.Timestamp("2026-08-07")].iloc[0]
    expected = (1.6e9 - 1.1e8) - (1e9 - 1e8)
    assert abs(row_7["net_margin_5d_change"] - expected) < 1.0  # 浮点容差


def test_compute_net_margin_change_per_industry():
    """多行业时各自独立算 5 日变化。"""
    df_a = _industry_df()
    df_b = _industry_df().copy()
    df_b["industry_code"] = "801780"
    df_b["industry_name"] = "非银金融"
    df = pd.concat([df_a, df_b], ignore_index=True)
    out = compute_net_margin_change(df, n_trading_days=5)
    # 每个行业 7 行 × 5 NaN = 10 NaN
    assert out["net_margin_5d_change"].isna().sum() == 10


def test_compute_net_margin_change_empty_df():
    empty = pd.DataFrame(columns=[
        "trade_date", "industry_code", "industry_name",
        "rzye", "rqye", "net_margin", "stock_count",
    ])
    out = compute_net_margin_change(empty, n_trading_days=5)
    assert out.empty
    assert "net_margin_5d_change" in out.columns
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/flow_dashboard/indicators/test_margin_industry.py -v
```

Expected: FAIL with `ImportError: cannot import name 'compute_net_margin_change'`.

- [ ] **Step 3: Write the implementation**

Append to `src/flow_dashboard/indicators/margin.py`:

```python
def compute_net_margin_change(
    df: pd.DataFrame,
    *,
    n_trading_days: int = 5,
) -> pd.DataFrame:
    """按 industry_code 分组，算 net_margin 的 N 日变化。

    Args:
        df: aggregate_margin_by_industry 的输出
        n_trading_days: 滑动窗口（默认 5 个交易日）

    Returns:
        df 增加 net_margin_5d_change 列（前 N-1 日为 NaN）
    """
    if df.empty:
        out = df.copy()
        out["net_margin_5d_change"] = pd.Series(dtype=float)
        return out

    df = df.sort_values(
        ["industry_code", "trade_date"]
    ).reset_index(drop=True).copy()

    out_frames: list[pd.DataFrame] = []
    for industry_code, group in df.groupby("industry_code", sort=False):
        group = group.sort_values("trade_date").reset_index(drop=True).copy()
        group["net_margin_5d_change"] = (
            group["net_margin"] - group["net_margin"].shift(n_trading_days)
        )
        out_frames.append(group)
    return pd.concat(out_frames, ignore_index=True).sort_values(
        ["trade_date", "industry_code"]
    ).reset_index(drop=True)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/flow_dashboard/indicators/test_margin_industry.py -v
```

Expected: 7/7 PASS（4 个 Task 3 测试 + 3 个 Task 4 测试）.

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/indicators/margin.py \
        tests/flow_dashboard/indicators/test_margin_industry.py
git commit -m "feat(phase-c): compute_net_margin_change (5-day net margin delta per industry)"
```

---

## Task 5: 热力图 figure factory（industry_heatmap_panel）

**Files:**
- Modify: `src/flow_dashboard/render/figures.py` (append `industry_heatmap_panel`)
- Modify: `tests/flow_dashboard/render/test_figures.py` (append tests)

- [ ] **Step 1: Write the failing test**

Append to `tests/flow_dashboard/render/test_figures.py`:

```python
from flow_dashboard.render.figures import industry_heatmap_panel


def test_industry_heatmap_panel_basic():
    df = pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "industry_code": "801770",
         "industry_name": "银行", "net_margin_5d_change": 1e8},
        {"trade_date": pd.Timestamp("2026-08-07"), "industry_code": "801780",
         "industry_name": "非银金融", "net_margin_5d_change": -2e8},
        {"trade_date": pd.Timestamp("2026-08-08"), "industry_code": "801770",
         "industry_name": "银行", "net_margin_5d_change": 1.5e8},
        {"trade_date": pd.Timestamp("2026-08-08"), "industry_code": "801780",
         "industry_name": "非银金融", "net_margin_5d_change": None},  # NaN
    ])
    fig = industry_heatmap_panel(
        df, title="行业热力图", data_date="2026-08-08",
    )
    # Heatmap 是单 trace
    assert len(fig.data) == 1
    # x 轴是日期，y 轴是行业名
    assert fig.data[0].x == ["2026-08-07", "2026-08-08"]
    assert list(fig.data[0].y) == ["非银金融", "银行"]  # sort by name


def test_industry_heatmap_panel_yi_units():
    """数值应转换为亿元（除以 1e8）。"""
    df = pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "industry_code": "801770",
         "industry_name": "银行", "net_margin_5d_change": 1e8},
    ])
    fig = industry_heatmap_panel(
        df, title="行业热力图", data_date="2026-08-07",
    )
    # 1e8 元 → 1 亿元
    z = list(fig.data[0].z)
    assert z == [[1.0]]


def test_industry_heatmap_panel_empty_df_does_not_crash():
    empty = pd.DataFrame(columns=[
        "trade_date", "industry_code", "industry_name", "net_margin_5d_change",
    ])
    fig = industry_heatmap_panel(
        empty, title="行业热力图", data_date="2026-08-08",
    )
    # 空 figure（pipeline 在更上层 stale fallback，不应调到这里；但需要不崩）
    assert len(fig.data) == 0 or len(fig.data[0].x) == 0


def test_industry_heatmap_panel_colorscale_has_red_and_green():
    """净流入=红、净流出=绿（A 股配色约定）。"""
    df = pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "industry_code": "801770",
         "industry_name": "银行", "net_margin_5d_change": 1e8},
    ])
    fig = industry_heatmap_panel(
        df, title="行业热力图", data_date="2026-08-07",
    )
    colorscale = fig.data[0].colorscale
    # 负值端（绿）→ 0 → 正值端（红）；检查 colorscale 第一/最后一点颜色
    assert "rgb(0," in str(colorscale[0]) or "#00" in str(colorscale[0]).lower()
    assert "rgb(255," in str(colorscale[-1]) or "red" in str(colorscale[-1]).lower()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/flow_dashboard/render/test_figures.py::test_industry_heatmap_panel_basic -v
```

Expected: FAIL with `ImportError: cannot import name 'industry_heatmap_panel'`.

- [ ] **Step 3: Write the implementation**

Append to `src/flow_dashboard/render/figures.py`:

```python
def industry_heatmap_panel(
    df: pd.DataFrame,
    *,
    title: str,
    data_date: str,
    coverage: float | None = None,
    last_success_at: str | None = None,
    n_trading_days: int = 30,
) -> go.Figure:
    """行业 × 交易日 热力图（净融资 N 日变化，正红负绿）。

    Args:
        df: aggregate_margin_by_industry + compute_net_margin_change 输出，
            必须含 trade_date, industry_name, net_margin_5d_change
        n_trading_days: 显示最近 N 个交易日（默认 30）
    """
    if df.empty:
        return apply_theme(
            go.Figure(), title=title, y_title="行业",
            data_date=data_date, coverage=coverage,
            last_success_at=last_success_at, unit="亿元",
        )

    df = df.copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"])
    # 取最近 N 个交易日
    recent_dates = sorted(df["trade_date"].unique())[-n_trading_days:]
    df = df[df["trade_date"].isin(recent_dates)]

    # 构造矩阵：行=行业（按名称排序），列=日期
    pivot = df.pivot_table(
        index="industry_name",
        columns="trade_date",
        values="net_margin_5d_change",
        aggfunc="first",
    )
    pivot = pivot.reindex(sorted(pivot.index))  # 行业名排序
    pivot = pivot[sorted(pivot.columns)]  # 日期排序

    x = [d.strftime("%Y-%m-%d") for d in pivot.columns]
    y = list(pivot.index)
    # 元 → 亿元（保留 NaN）
    z = [[v / _CNY_TO_YI if pd.notna(v) else None for v in row]
         for row in pivot.values]

    fig = go.Figure(data=go.Heatmap(
        z=z, x=x, y=y,
        colorscale=[
            [0.0, "rgb(0, 128, 0)"],    # 负值=绿
            [0.5, "rgb(255, 255, 255)"],  # 0=白
            [1.0, "rgb(255, 0, 0)"],     # 正值=红
        ],
        zmid=0,
        colorbar={"title": "亿元"},
        hovertemplate="%{y}<br>%{x}<br>%{z:.2f} 亿元<extra></extra>",
    ))

    return apply_theme(
        fig, title=title, y_title="申万一级行业",
        data_date=data_date, coverage=coverage,
        last_success_at=last_success_at, unit="亿元",
    )
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/flow_dashboard/render/test_figures.py -v -k heatmap
```

Expected: 4/4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/render/figures.py tests/flow_dashboard/render/test_figures.py
git commit -m "feat(phase-c): industry_heatmap_panel figure (28 industries × 30 days)"
```

---

## Task 6: 面板 renderer（render_margin_industry_heatmap）

**Files:**
- Create: `src/flow_dashboard/render/panels_margin_industry.py`
- Create: `tests/flow_dashboard/render/test_panels_margin_industry.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/flow_dashboard/render/test_panels_margin_industry.py
"""个股两融行业热力图面板 renderer 测试。"""
from __future__ import annotations

import pandas as pd
import pytest

from flow_dashboard.render.panels_margin_industry import (
    render_margin_industry_heatmap,
)


def _industry_df(n_days: int = 5):
    rows = []
    base = pd.Timestamp("2026-08-05")
    for d_offset in range(n_days):
        for ind_code, ind_name in [("801770", "银行"), ("801780", "非银金融")]:
            rows.append({
                "trade_date": base + pd.Timedelta(days=d_offset),
                "industry_code": ind_code,
                "industry_name": ind_name,
                "rzye": 1e9, "rqye": 1e8, "net_margin": 9e8,
                "stock_count": 5,
                "net_margin_5d_change": 1e8 if d_offset >= 4 else None,
            })
    return pd.DataFrame(rows)


def test_render_margin_industry_heatmap_basic():
    html = render_margin_industry_heatmap(
        _industry_df(),
        data_date="2026-08-12",
        coverage=0.95, last_success_at="19:30",
    )
    assert "行业热力图" in html
    assert "Plotly.newPlot" in html
    assert 'id="panel-margin-industry-heatmap"' in html


def test_render_margin_industry_heatmap_empty_df_stale():
    empty = pd.DataFrame(columns=[
        "trade_date", "industry_code", "industry_name",
        "rzye", "rqye", "net_margin", "stock_count", "net_margin_5d_change",
    ])
    html = render_margin_industry_heatmap(
        empty, data_date="2026-08-12",
        coverage=None, last_success_at=None,
    )
    assert "stale" in html.lower() or "数据不可得" in html
    assert "Plotly.newPlot" not in html


def test_render_margin_industry_heatmap_coverage_none_stale():
    """df 有数据但 coverage=None（上游未冻结）也应 stale。"""
    html = render_margin_industry_heatmap(
        _industry_df(), data_date="2026-08-12",
        coverage=None, last_success_at="19:30",
    )
    assert "stale" in html.lower() or "数据不可得" in html
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/flow_dashboard/render/test_panels_margin_industry.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'flow_dashboard.render.panels_margin_industry'`.

- [ ] **Step 3: Write the implementation**

```python
# src/flow_dashboard/render/panels_margin_industry.py
"""个股两融按申万 L1 行业热力图面板（Phase C 第 16 块面板）。"""
from __future__ import annotations

from html import escape as _html_escape

import pandas as pd

from flow_dashboard.render.figures import industry_heatmap_panel
from flow_dashboard.render.theme import render_figure_to_html


_PANEL_ID = "panel-margin-industry-heatmap"
_PANEL_TITLE = "个股两融 — 申万 L1 行业热力图（5 日净融资变化）"


def _wrap_panel(div_id: str, title: str, body: str, stale: bool = False) -> str:
    stale_cls = " stale" if stale else ""
    return f"""<div class="panel{stale_cls}" id="{div_id}">
<h2 class="panel-title">{_html_escape(title)}</h2>
{body}
</div>"""


def _stale_message(reason: str = "数据不可得") -> str:
    return f'<div class="stale">⚠️ {reason}（stale）</div>'


def render_margin_industry_heatmap(
    df: pd.DataFrame,
    *,
    data_date: str,
    coverage: float | None,
    last_success_at: str | None,
) -> str:
    """渲染行业热力图面板。

    Args:
        df: aggregate_margin_by_industry + compute_net_margin_change 输出
        coverage: None 表示上游未冻结，面板 stale
    """
    if df.empty or coverage is None:
        return _wrap_panel(_PANEL_ID, _PANEL_TITLE, _stale_message(), stale=True)

    fig = industry_heatmap_panel(
        df, title=_PANEL_TITLE, data_date=data_date,
        coverage=coverage, last_success_at=last_success_at,
    )
    body = render_figure_to_html(fig, div_id=_PANEL_ID)
    return _wrap_panel(_PANEL_ID, _PANEL_TITLE, body)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/flow_dashboard/render/test_panels_margin_industry.py -v
```

Expected: 3/3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/render/panels_margin_industry.py \
        tests/flow_dashboard/render/test_panels_margin_industry.py
git commit -m "feat(phase-c): render_margin_industry_heatmap panel with stale fallback"
```

---

## Task 7: Pipeline 接入（_run_eod_preview_inner）

**Files:**
- Modify: `src/flow_dashboard/pipeline.py`（在现有 _run_eod_preview_inner 末尾追加新面板）
- Modify: `tests/flow_dashboard/test_pipeline.py`（如已有；否则新建并测试新面板接入）

- [ ] **Step 1: Read existing pipeline structure**

```bash
grep -n "panel_status\|panels.append\|panel_ids" src/flow_dashboard/pipeline.py | head -30
```

Confirm the location of `_run_eod_preview_inner`, the `panels.append(...)` chain, and the `panel_ids` list in the manifest payload.

- [ ] **Step 2: Write the failing integration test**

Append to `tests/flow_dashboard/test_pipeline.py` (or create if not exists):

```python
def test_run_eod_preview_includes_industry_heatmap_panel(monkeypatch, tmp_path):
    """eod_preview 生成的 HTML 应含 panel-margin-industry-heatmap。"""
    import pandas as pd
    from flow_dashboard.pipeline import run_eod_preview

    # Mock loaders
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_etf_share_for_pipeline",
        lambda **kw: pd.DataFrame([
            {"ts_code": "510050.SH", "trade_date": pd.Timestamp("2026-08-11"),
             "share_in_shares": 100e8, "unit_nav": 3.0, "total_size_cny": 300e8,
             "quality_flags": ""},
        ]),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_margin_for_pipeline",
        lambda **kw: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_fut_daily_for_pipeline",
        lambda **kw: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_index_daily_for_pipeline",
        lambda **kw: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_fund_nav_for_pipeline",
        lambda **kw: pd.DataFrame(),
    )
    # Mock 新的 margin_detail loader 和 sw_l1 members loader
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_margin_detail_for_pipeline",
        lambda **kw: pd.DataFrame([
            {"trade_date": pd.Timestamp("2026-08-11"), "ts_code": "000001.SZ",
             "rzye": 1e9, "rqye": 1e8},
        ]),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_sw_l1_members",
        lambda **kw: pd.DataFrame([
            {"trade_date": "2026-08-11", "con_code": "000001.SZ",
             "industry_code": "801770", "industry_name": "银行"},
        ]),
    )
    # PIT pivot 返回 1 天 × 1 股
    monkeypatch.setattr(
        "flow_dashboard.pipeline._pivot_sw_l1_to_daily",
        lambda members, start, end: pd.DataFrame([
            {"trade_date": "2026-08-11", "con_code": "000001.SZ",
             "industry_code": "801770", "industry_name": "银行"},
        ]),
    )

    out = run_eod_preview(
        data_date="2026-08-12",
        as_of=pd.Timestamp("2026-08-12 19:30", tz="Asia/Shanghai"),
        output_dir=tmp_path,
    )
    html = Path(out).read_text()
    assert 'id="panel-margin-industry-heatmap"' in html
```

- [ ] **Step 3: Run test to verify it fails**

```bash
python3 -m pytest tests/flow_dashboard/test_pipeline.py::test_run_eod_preview_includes_industry_heatmap_panel -v
```

Expected: FAIL（panel 不在 HTML 里）.

- [ ] **Step 4: Modify pipeline.py to wire in the new panel**

Add these imports near the top of `pipeline.py`:

```python
from flow_dashboard.data.sw_l1_members import (
    load_sw_l1_members, pivot_to_daily_membership as _pivot_sw_l1_to_daily,
)
from flow_dashboard.data.loaders import load_margin_detail as _load_margin_detail_for_pipeline_raw
from flow_dashboard.indicators.margin import (
    aggregate_margin_by_industry, compute_net_margin_change,
)
from flow_dashboard.render.panels_margin_industry import render_margin_industry_heatmap
```

Add a wrapper near `_load_fund_nav_for_pipeline`:

```python
def _load_margin_detail_for_pipeline(start, end, as_of):
    return _load_margin_detail_for_pipeline_raw(
        start=start, end=end, as_of=as_of,
    )


def _load_sw_l1_members():
    return load_sw_l1_members()
```

In `_run_eod_preview_inner`, **before** `body = "\n".join(panels)` (after the basis panel block), append:

```python
# Phase C 第 16 面板：行业热力图
margin_detail_df = _load_margin_detail_for_pipeline(start, end, as_of)
if not margin_detail_df.empty:
    members = _load_sw_l1_members()
    members_daily = _pivot_sw_l1_to_daily(
        members, start=start, end=end,
    )
    industry_agg = aggregate_margin_by_industry(margin_detail_df, members_daily)
    industry_with_change = compute_net_margin_change(industry_agg, n_trading_days=5)
    industry_coverage = 1.0 if not industry_with_change.empty else None
else:
    industry_with_change = pd.DataFrame()
    industry_coverage = None
panels.append(render_margin_industry_heatmap(
    industry_with_change,
    data_date=data_date,
    coverage=industry_coverage,
    last_success_at=as_of_format(as_of),
))
```

Also update the `panel_ids` list in the manifest payload (search for the existing 15-panel list):

```python
"panel-margin-industry-heatmap",  # NEW (Phase C)
```

- [ ] **Step 5: Run all tests**

```bash
python3 -m pytest tests/flow_dashboard/ -m "not live" -q
```

Expected: All previous tests pass + new test passes. Count should grow by ~3-5 (Task 7 included).

- [ ] **Step 6: Commit**

```bash
git add src/flow_dashboard/pipeline.py tests/flow_dashboard/test_pipeline.py
git commit -m "feat(phase-c): wire industry heatmap into eod_preview (16th panel)"
```

---

## Task 8: 端到端 dry-run + Gate Report 更新

**Files:**
- Modify: `docs/资金流跟踪/phase_b_gate_report.md`（更新 §1 表 + §6 测试计数；新增 §9 Phase C 增量）
- 不修改代码（验证 + 文档）

- [ ] **Step 1: Run end-to-end with real token**

```bash
export ASHARE_FLOW_TUSHARE_TOKEN="$TUSHARE_TOKEN"
python3 scripts/flow_dashboard/run_eod_preview.py --data-date 2026-08-13
```

Expected: `eod_preview published: .../report_2026-08-13_vNN.html`. Open the HTML and visually verify the new panel shows.

- [ ] **Step 2: Run full test suite**

```bash
python3 -m pytest tests/flow_dashboard/ -m "not live" -q
```

Expected: 全部通过；记录总数（应该比 Phase B 的 107 多约 15-20 个）.

- [ ] **Step 3: Update Gate Report**

Modify `docs/资金流跟踪/phase_b_gate_report.md`:

1. In §1 table, append a new row:
   ```
   | 16. margin-industry-heatmap | 个股两融行业热力图（5 日净融资变化） | panels_margin_industry.py | ✓ |
   ```

2. In §6, update Phase B test count and total:
   ```
   - 全部 Phase A 测试通过：36 个
   - 全部 Phase B 测试通过：71 个
   - 全部 Phase C（增量）测试通过：<填入实测> 个
   - Red Line 1 端到端守护：1 个
   - 合计 <填入总数> passed
   ```

3. Add a new §9 (renumber existing §9 if needed):

   ```markdown
   ## 9. Phase C 增量（2026-08-13）

   ### 9.1 已完成
   - 第 16 面板：`panel-margin-industry-heatmap` — 28 申万 L1 × 30 交易日，
     颜色编码净融资 5 日变化（正红负绿）。
   - 新 data layer：`load_sw_l1_members`（28 行业成分股 PIT 表）+
     `load_margin_detail`（个股两融明细，per-day parquet 缓存）。
   - 新 indicator：`aggregate_margin_by_industry`（PIT 行业归属聚合）+
     `compute_net_margin_change`（5 日净融资变化）。
   - 新 figure：`industry_heatmap_panel` + 面板 renderer `render_margin_industry_heatmap`。

   ### 9.2 已知限制（待 Phase D）
   - 个股两融数据有 ~3 天滞后（Tushare 数据回填延迟），最近 3 天的热力图格可能为空。
   - 热力图行用日历日（含周末），未来可切换为交易日。
   - 申万一级成分股缓存无 TTL，需手工 `use_cache=False` 刷新（半年一次即可）。

   ### 9.3 Phase D 候选
   - 公募基金主动权益代理指标（已敲定数据源 `fund_basic.invest_type`，规则已定）。
   - 港股 ETF 资金流（需手工下载港交所 CSV，5 分钟）。
   - 行业热力图增加"按板块聚合"切换（28 → 5 大板块）。
   ```

- [ ] **Step 4: Commit**

```bash
git add "docs/资金流跟踪/phase_b_gate_report.md"
git commit -m "docs(phase-c): update gate report — 16 panels, Phase C section"
```

- [ ] **Step 5: Final tag (optional)**

```bash
git tag -a phase-c-v1.0 -m "Phase C: industry heatmap (16th panel, SW L1 × 30d × 5d net margin change)"
```

---

## 自检清单

完成所有 task 后，运行：

```bash
# 1. 全部测试
python3 -m pytest tests/flow_dashboard/ -v

# 2. 端到端 dry-run
export ASHARE_FLOW_TUSHARE_TOKEN="$TUSHARE_TOKEN"
python3 scripts/flow_dashboard/run_eod_preview.py --data-date 2026-08-13
open output/ashare_flow_daily/latest.html  # 验证第 16 面板

# 3. 检查文件结构
find src/flow_dashboard -name "*.py" | sort | grep -E "sw_l1|panels_margin_industry"
find tests/flow_dashboard -name "*.py" | sort | grep -E "sw_l1|margin_industry|margin_detail"

# 4. 检查 manifest 含新 panel ID
grep -A 20 '"panels"' output/ashare_flow_daily/manifest/2026-08-13_v*.json | head -25
```

预期：
- 测试全绿（约 120+ 个，比 Phase B 多 ~15-20）
- 第 16 面板显示在 dashboard 末尾，28 行业 × 30 列热力图
- 颜色分布合理（多数行业偏白/淡色，少数偏红/绿）
- 新文件存在：sw_l1_members.py / panels_margin_industry.py + 3 个测试文件
- manifest `panels` 数组含 `panel-margin-industry-heatmap`

---

## Self-Review Checklist（writing-plans skill 要求）

完成本计划写作后，作者自查：

1. **Spec coverage**：spec §5 Phase C 启动条件中"个股两融行业热力"项 → 由 Tasks 1-7 覆盖（loader + indicator + render + pipeline）。
2. **Placeholder scan**：本计划无 TBD / TODO / "add error handling" 等占位符。
3. **Type consistency**：
   - `aggregate_margin_by_industry` 输出列（`net_margin`）→ `compute_net_margin_change` 输入列（`net_margin`）✓
   - `industry_heatmap_panel` 期望 `net_margin_5d_change` 列 → 与 `compute_net_margin_change` 输出列一致 ✓
   - Panel ID `panel-margin-industry-heatmap` 在 test / renderer / pipeline / manifest 一致 ✓
4. **PIT 红线**：Task 1 包含 PIT 边界测试（`test_pivot_to_daily_membership_pit_correct`）；Task 3 包含 PIT 行业归属变化测试（`test_aggregate_margin_by_industry_pit_membership_change`）。
5. **Stale 显式**：Task 6 包含 coverage=None 和空 df 的 stale 测试。
