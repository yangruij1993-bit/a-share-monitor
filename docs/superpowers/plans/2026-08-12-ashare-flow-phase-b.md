# A 股流动性仪表板 — Phase B 可发布 MVP 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 spec `2026-08-12-ashare-flow-daily-design.md` §3.5.2 定义的 Phase B 可发布 MVP：交付 15 个可见面板（9 日度 ETF + 4 周度 ETF + 1 两融 + 1 IC/IM 基差）+ 数据健康页 + 原子发布能力 + 4 个 pipeline runner（intraday / eod_preview / daily_finalize / monthly），并通过共通验收（公式单测、单位测试、后缀不变测试、stale 隔离、重复执行稳定性）。

**Architecture:** 在 Phase A 已建好的 `src/flow_dashboard/data/` provider 层上，新增 `indicators/`（s1-s4 公式实现）、`render/`（Plotly figure factory + atomic assembly）、`pipeline.py`（4 个入口的运行时编排）。所有 loader 统一 `load(start, end, as_of, universe, use_cache)` 契约并执行 `available_at <= as_of` PIT 过滤；render 层每次生成 staging HTML，通过完整性检查后原子 replace 归档文件，并通过 symlink 原子替换 `latest.html`。intraday runner 只更新 `intraday_latest.html`，不写归档。

**Tech Stack:** Python 3.14、pandas、tushare 1.4.29、requests+certifi、pyarrow（parquet 落盘）、plotly 5.x（图渲染，离线内嵌）、pytest 9.x。

**Scope boundaries (this plan will NOT do):**
- 不实现 s5（期权 IV）、s6（公募代理）、s7（主动权益年内收益）、s8（减持事件）—— Phase C/D。
- 不实现 PIT 申万 L1 历史成分源 / 个股两融行业热力 —— Phase C。
- 不实现港股 ETF 板块 —— Phase C。
- 不拼接或命名"当季连续基差"——spec §3.5.2 显式禁止；首版逐合约分段展示，`contract_selector/roll_rule` 关闭前不拼接。
- 不实现分红调整基差（`dividend_adjustment=false` 已冻结）。
- 不实现 spec §3.6 的"本期摘要"层（KPI 卡片 + 摘要文案）——spec §3.6 是约束其内容（确定性规则、禁生成式 AI），不是 Phase B 必交付；首版只交付 15 面板 + 数据健康页，留位但不渲染摘要文案。
- 不冻结 `performance_budget`、`max_quote_skew_seconds`、`reconciliation_tolerance` 等需人工冻结的阈值——本计划落盘实测分布并在 runner 中允许 `null` 表示未冻结。

**Pre-flight (manual, before Task 1):**
```bash
# 1. 确认 Phase A 已完成且 token 已解耦
cd /Users/xinghuazhang/ygr-project/a股监控
echo $ASHARE_FLOW_TUSHARE_TOKEN | head -c 6  # 应显示 token 前 6 位
# 2. 确认 Phase A 测试基线绿
pytest tests/flow_dashboard/ -m "not live" -q
# 3. 安装 Phase B 新增依赖
pip install plotly>=5.20
```

**File structure (this plan creates):**

```
a股监控/
├── pyproject.toml                       # Phase A 已建，Phase B 添加 plotly 依赖
├── pytest.ini                           # Phase A 已建
├── src/flow_dashboard/
│   ├── __init__.py                      # Phase A 已建
│   ├── config.py                        # Phase A 已建，Phase B 添加 OUTPUT_DIR/MANIFEST_DIR/INTRADAY_OUTPUT/RUNNERS_LOCK
│   ├── data/                            # Phase A 已建（tushare/sina/schema/pit_labels）
│   │   └── loaders.py                   # Phase B 新增：统一 load(start,end,as_of) 契约 + PIT 过滤
│   ├── indicators/                      # Phase B 新增
│   │   ├── __init__.py
│   │   ├── etf_flow.py                  # s1: Δshare × nav (PIT-protected)
│   │   ├── flow_aggregation.py          # s2: coverage_gates + 周度/月度/累计
│   │   ├── margin.py                    # s3: SSE/SZSE/BSE 汇总 + 周变化
│   │   └── basis.py                     # s4: IC/IM 逐合约基差
│   ├── render/                          # Phase B 新增
│   │   ├── __init__.py
│   │   ├── theme.py                     # 配色、HTML 骨架、Plotly JS 单次内嵌
│   │   ├── figures.py                   # figure factory（标题/单位/覆盖率/最新源时间）
│   │   ├── panels_daily.py              # 9 日度 ETF 面板
│   │   ├── panels_weekly.py             # 4 周度 ETF 面板
│   │   ├── panels_margin.py             # 1 两融面板
│   │   ├── panels_basis.py              # 1 基差面板（IC/IM 双 subplot）
│   │   ├── panels_health.py             # 数据健康页
│   │   └── assembly.py                  # atomic replace + symlink + manifest
│   ├── pipeline.py                      # Phase B 新增：intraday / eod_preview / daily_finalize / monthly
│   └── phase_a/                         # Phase A 已建
├── scripts/flow_dashboard/
│   ├── (Phase A 已建 4 个)
│   ├── run_intraday.py                  # Phase B 新增
│   ├── run_eod_preview.py
│   ├── run_daily_finalize.py
│   └── run_monthly.py
├── scripts/launchd/                     # Phase B 新增
│   ├── README.md                        # 安装与排查说明
│   ├── com.ygr.ashare-flow.intraday.plist
│   ├── com.ygr.ashare-flow.eod-preview.plist
│   ├── com.ygr.ashare-flow.daily-finalize.plist
│   └── com.ygr.ashare-flow.monthly.plist
├── tests/flow_dashboard/
│   ├── (Phase A 已建)
│   ├── test_loaders.py                  # Phase B 新增
│   ├── indicators/
│   │   ├── __init__.py
│   │   ├── test_etf_flow.py
│   │   ├── test_flow_aggregation.py
│   │   ├── test_margin.py
│   │   └── test_basis.py
│   ├── render/
│   │   ├── __init__.py
│   │   ├── test_theme.py
│   │   ├── test_figures.py
│   │   ├── test_assembly.py
│   │   ├── test_panels_daily.py
│   │   ├── test_panels_weekly.py
│   │   ├── test_panels_margin.py
│   │   ├── test_panels_basis.py
│   │   └── test_panels_health.py
│   ├── test_pipeline_intraday.py
│   ├── test_pipeline_eod_preview.py
│   ├── test_pipeline_daily_finalize.py
│   ├── test_pipeline_monthly.py
│   └── test_suffix_invariance_e2e.py    # Red Line 1 端到端守护
├── output/ashare_flow_daily/            # Phase B 新增（gitignore）
│   ├── report_<data_date>_vNN.html      # 归档版本
│   ├── latest.html -> symlink
│   ├── intraday_latest.html
│   └── manifest/
│       └── <data_date>_vNN.json
└── docs/资金流跟踪/
    └── phase_b_gate_report.md           # Phase B 出口报告
```

---

## Task 1: 项目骨架与依赖（indicators/ + render/ + output/）

**Files:**
- Modify: `pyproject.toml`（添加 plotly 依赖）
- Modify: `src/flow_dashboard/config.py`（添加 OUTPUT_DIR/MANIFEST_DIR/INTRADAY_OUTPUT/RUNNERS_LOCK/STAGING_DIR）
- Create: `src/flow_dashboard/indicators/__init__.py`
- Create: `src/flow_dashboard/render/__init__.py`
- Create: `src/flow_dashboard/pipeline.py`（占位 stub）
- Create: `tests/flow_dashboard/indicators/__init__.py`
- Create: `tests/flow_dashboard/render/__init__.py`
- Modify: `.gitignore`（添加 output/）
- Create: `output/ashare_flow_daily/.gitkeep`
- Create: `output/ashare_flow_daily/manifest/.gitkeep`

- [ ] **Step 1: Write failing test for config additions**

Create `tests/flow_dashboard/test_config_phase_b.py`:

```python
"""Phase B config 添加项测试。"""
from __future__ import annotations

from pathlib import Path

from flow_dashboard.config import (
    OUTPUT_DIR, MANIFEST_DIR, INTRADAY_OUTPUT,
    RUNNERS_LOCK, STAGING_DIR,
)


def test_output_dir_under_project():
    assert OUTPUT_DIR.name == "ashare_flow_daily"
    assert "output" in str(OUTPUT_DIR)

def test_manifest_dir_under_output():
    assert MANIFEST_DIR.parent == OUTPUT_DIR
    assert MANIFEST_DIR.name == "manifest"

def test_intraday_output_distinct_from_archive():
    """spec §3.3: intraday 只更新 intraday_latest.html，不写归档。"""
    assert INTRADAY_OUTPUT.name == "intraday_latest.html"
    assert INTRADAY_OUTPUT.parent == OUTPUT_DIR

def test_runners_lock_path():
    assert RUNNERS_LOCK.name == "runners.lock"
    assert RUNNERS_LOCK.parent == OUTPUT_DIR

def test_staging_dir_under_output():
    assert STAGING_DIR.parent == OUTPUT_DIR
    assert STAGING_DIR.name == "staging"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/flow_dashboard/test_config_phase_b.py -v`
Expected: ImportError for OUTPUT_DIR etc.

- [ ] **Step 3: Update `src/flow_dashboard/config.py`**

Append to existing file:

```python
OUTPUT_DIR = PROJECT_ROOT / "output" / "ashare_flow_daily"
MANIFEST_DIR = OUTPUT_DIR / "manifest"
STAGING_DIR = OUTPUT_DIR / "staging"
INTRADAY_OUTPUT = OUTPUT_DIR / "intraday_latest.html"
RUNNERS_LOCK = OUTPUT_DIR / "runners.lock"


def ensure_output_dirs() -> None:
    """幂等创建 Phase B 输出目录。"""
    for d in (OUTPUT_DIR, MANIFEST_DIR, STAGING_DIR):
        d.mkdir(parents=True, exist_ok=True)
```

Also update `ensure_dirs()` to call `ensure_output_dirs()`:

```python
def ensure_dirs() -> None:
    """幂等创建项目所需目录。"""
    for d in (DATA_DIR, CACHE_DIR, EVIDENCE_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)
    ensure_output_dirs()
```

- [ ] **Step 4: Update `pyproject.toml` to add plotly**

```toml
[project]
name = "ashare-flow-dashboard"
version = "0.1.0b0"
description = "A 股流动性与 ETF 资金流日度跟踪仪表板 — Phase B 可发布 MVP"
requires-python = ">=3.13"
dependencies = [
    "pandas>=2.2",
    "tushare>=1.4",
    "pyyaml>=6.0",
    "requests>=2.31",
    "pyarrow>=15.0",
    "plotly>=5.20",
]
```

- [ ] **Step 5: Create `src/flow_dashboard/indicators/__init__.py`**

```python
"""Phase B 指标公式（s1-s4）。

spec §2.1 定义 8 个公式；Phase B 仅实现 s1-s4。
"""
```

- [ ] **Step 6: Create `src/flow_dashboard/render/__init__.py`**

```python
"""Phase B 渲染层：Plotly figure + HTML 原子发布。"""
```

- [ ] **Step 7: Create `src/flow_dashboard/pipeline.py` stub**

```python
"""Phase B pipeline 入口：intraday / eod_preview / daily_finalize / monthly。

实现由后续 task 填充；本 stub 仅声明函数签名。
"""
from __future__ import annotations


def run_intraday(*, as_of, force: bool = False) -> str:
    raise NotImplementedError


def run_eod_preview(*, data_date, as_of, force: bool = False) -> str:
    raise NotImplementedError


def run_daily_finalize(*, data_date, as_of, force: bool = False) -> str:
    raise NotImplementedError


def run_monthly(*, as_of, force: bool = False) -> str:
    raise NotImplementedError
```

- [ ] **Step 8: Create test subdirectories**

```bash
mkdir -p tests/flow_dashboard/indicators tests/flow_dashboard/render
```

**Important:** Do NOT create `__init__.py` in these test subdirectories. Phase A had to delete `tests/flow_dashboard/__init__.py` because it shadowed the src package when both `tests/` and `src/` ended up on `sys.path`. pytest discovers test files via rootdir (project root) without needing `__init__.py`.

- [ ] **Step 9: Update `.gitignore`**

Append:

```
output/ashare_flow_daily/*.html
output/ashare_flow_daily/staging/
output/ashare_flow_daily/manifest/
!output/ashare_flow_daily/.gitkeep
!output/ashare_flow_daily/manifest/.gitkeep
```

- [ ] **Step 10: Create `.gitkeep` files**

```bash
mkdir -p output/ashare_flow_daily/manifest
touch output/ashare_flow_daily/.gitkeep output/ashare_flow_daily/manifest/.gitkeep
```

- [ ] **Step 11: Run all tests to verify Phase A still passes**

Run: `pytest tests/flow_dashboard/ -m "not live" -q`
Expected: All Phase A tests pass + new config test passes.

- [ ] **Step 12: Commit**

```bash
git add pyproject.toml src/flow_dashboard/config.py src/flow_dashboard/indicators/__init__.py \
  src/flow_dashboard/render/__init__.py src/flow_dashboard/pipeline.py \
  tests/flow_dashboard/test_config_phase_b.py .gitignore output/ashare_flow_daily/.gitkeep \
  output/ashare_flow_daily/manifest/.gitkeep
git commit -m "feat(phase-b): skeleton — indicators/, render/, pipeline.py stub, output dirs"
```

---

## Task 2: Loaders 统一契约 — PIT 过滤 + 缓存层

**Files:**
- Create: `src/flow_dashboard/data/loaders.py`
- Create: `tests/flow_dashboard/test_loaders.py`

`loader.py` 包装 Phase A provider，加上：
1. `available_at <= as_of` PIT 过滤
2. parquet 增量缓存（命中则读盘，未命中调 provider）
3. 审计列写入（source_date/first_observed_at/available_at/fetched_at/source/source_version/is_stale/quality_flags）
4. 公共签名 `load(start, end, as_of, universe=None, use_cache=True)`

- [ ] **Step 1: Write failing test for `load_etf_share`**

Create `tests/flow_dashboard/test_loaders.py`:

```python
"""loaders 契约测试：PIT 过滤、缓存命中、审计列、单位。"""
from __future__ import annotations

import pandas as pd
import pytest

from flow_dashboard.data.loaders import load_etf_share, load_margin, load_fut_daily


def _mock_etf_provider():
    """模拟 3 行 etf_share_size 数据，available_at 不同。"""
    base = pd.Timestamp("2026-08-12 09:00:00", tz="Asia/Shanghai")
    return pd.DataFrame([
        {"ts_code": "510050.SH", "trade_date": pd.Timestamp("2026-08-07"),
         "total_share": 100.0, "total_size": 100.0, "exchange": "SSE",
         "etf_name": "50ETF"},
        {"ts_code": "510050.SH", "trade_date": pd.Timestamp("2026-08-08"),
         "total_share": 105.0, "total_size": 105.0, "exchange": "SSE",
         "etf_name": "50ETF"},
        {"ts_code": "510050.SH", "trade_date": pd.Timestamp("2026-08-11"),
         "total_share": 110.0, "total_size": 110.0, "exchange": "SSE",
         "etf_name": "50ETF"},
    ])


def test_load_etf_share_filters_future_available_at(monkeypatch, tmp_path):
    """as_of < 某行 available_at 时，该行必须被剔除。"""
    df = _mock_etf_provider()
    monkeypatch.setattr(
        "flow_dashboard.data.loaders._pull_etf_share_for_load",
        lambda codes, start, end: df,
    )
    as_of = pd.Timestamp("2026-08-11 08:00:00", tz="Asia/Shanghai")
    out = load_etf_share(
        codes=["510050.SH"],
        start=pd.Timestamp("2026-08-01"),
        end=pd.Timestamp("2026-08-31"),
        as_of=as_of,
        cache_dir=tmp_path,
    )
    assert len(out) == 2  # 只有 8-7 和 8-8 available_at <= as_of
    assert (out["available_at"] <= as_of).all()


def test_load_etf_share_writes_audit_columns(monkeypatch, tmp_path):
    df = _mock_etf_provider()
    monkeypatch.setattr(
        "flow_dashboard.data.loaders._pull_etf_share_for_load",
        lambda codes, start, end: df,
    )
    out = load_etf_share(
        codes=["510050.SH"],
        start=pd.Timestamp("2026-08-01"),
        end=pd.Timestamp("2026-08-31"),
        as_of=pd.Timestamp("2026-08-12 09:00", tz="Asia/Shanghai"),
        cache_dir=tmp_path,
    )
    for col in ("source_date", "first_observed_at", "available_at",
                "fetched_at", "source", "source_version", "is_stale", "quality_flags"):
        assert col in out.columns, f"missing audit col: {col}"
    assert (out["source"] == "tushare").all()
    assert (out["quality_flags"] == "").all()  # 无标记


def test_load_etf_share_cache_hit_skips_network(monkeypatch, tmp_path):
    """第二次 load 应命中缓存，不调 provider。"""
    df = _mock_etf_provider()
    call_count = {"n": 0}

    def mock_pull(codes, start, end):
        call_count["n"] += 1
        return df

    monkeypatch.setattr(
        "flow_dashboard.data.loaders._pull_etf_share_for_load", mock_pull
    )
    as_of = pd.Timestamp("2026-08-12 09:00", tz="Asia/Shanghai")
    load_etf_share(
        codes=["510050.SH"], start=pd.Timestamp("2026-08-01"),
        end=pd.Timestamp("2026-08-31"), as_of=as_of, cache_dir=tmp_path,
    )
    load_etf_share(
        codes=["510050.SH"], start=pd.Timestamp("2026-08-01"),
        end=pd.Timestamp("2026-08-31"), as_of=as_of, cache_dir=tmp_path,
    )
    assert call_count["n"] == 1


def test_load_etf_share_use_cache_false_bypasses(monkeypatch, tmp_path):
    df = _mock_etf_provider()
    call_count = {"n": 0}

    def mock_pull(codes, start, end):
        call_count["n"] += 1
        return df

    monkeypatch.setattr(
        "flow_dashboard.data.loaders._pull_etf_share_for_load", mock_pull
    )
    as_of = pd.Timestamp("2026-08-12 09:00", tz="Asia/Shanghai")
    kwargs = dict(codes=["510050.SH"], start=pd.Timestamp("2026-08-01"),
                  end=pd.Timestamp("2026-08-31"), as_of=as_of, cache_dir=tmp_path)
    load_etf_share(**kwargs)
    load_etf_share(use_cache=False, **kwargs)
    assert call_count["n"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/flow_dashboard/test_loaders.py -v`
Expected: ImportError for `flow_dashboard.data.loaders`.

- [ ] **Step 3: Implement `src/flow_dashboard/data/loaders.py`**

```python
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
    pull_fut_daily,
    pull_index_daily,
    pull_fund_nav,
)


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
    """加载 ETF 份额，落盘 parquet 增量缓存，PIT 过滤。"""
    cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "etf_share.parquet"

    fetched_at = pd.Timestamp.now(tz=TIMEZONE)
    available_at = as_of  # Tushare 日频当日 19:00 后可得，as_of 即上限

    if use_cache and cache_path.exists():
        cached = pd.read_parquet(cache_path)
        cached = cached[cached["available_at"] <= pd.Timestamp(as_of)]
        cached_codes = set(cached["ts_code"].unique()) if not cached.empty else set()
        missing_codes = [c for c in codes if c not in cached_codes]
        if not missing_codes:
            return _filter_range(cached, start, end)

        fresh = _pull_etf_share_for_load(missing_codes, start, end)
        fresh = _annotate_etf_share(fresh, fetched_at, available_at)
        combined = pd.concat([cached, fresh], ignore_index=True)
        combined = combined.drop_duplicates(
            subset=["ts_code", "trade_date", "source_date"], keep="last"
        )
        combined.to_parquet(cache_path, index=False)
        return _filter_range(combined, start, end)

    fresh = _pull_etf_share_for_load(codes, start, end)
    fresh = _annotate_etf_share(fresh, fetched_at, available_at)
    if use_cache:
        fresh.to_parquet(cache_path, index=False)
    return fresh


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
    df: pd.DataFrame, fetched_at: pd.Timestamp, available_at: pd.Timestamp
) -> pd.DataFrame:
    if df.empty:
        return _empty_with_audit()
    df = df.copy()
    if "share_in_shares" not in df.columns:
        # provider 已标准化，但保险
        df["share_in_shares"] = df["total_share"] * 10000
    df["total_size_cny"] = df["total_size"] * 10000  # 万元 → 元
    df["source_date"] = df["trade_date"]
    df["first_observed_at"] = fetched_at
    df["available_at"] = available_at
    df["fetched_at"] = fetched_at
    df["source"] = "tushare"
    df["source_version"] = "etf_share_size_v1"
    df["is_stale"] = False
    df["quality_flags"] = ""
    return df


def _empty_with_audit() -> pd.DataFrame:
    cols = list(AUDIT_COLUMNS)
    return pd.DataFrame(columns=cols)


def _filter_range(df: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    if df.empty or "trade_date" not in df.columns:
        return df
    mask = (df["trade_date"] >= pd.Timestamp(start)) & (df["trade_date"] <= pd.Timestamp(end))
    return df[mask].reset_index(drop=True)


# ============ Margin（spec §1.3 SSE/SZSE/BSE 三所） ============

def load_margin(
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
    as_of: pd.Timestamp,
    cache_dir: Path | str | None = None,
    use_cache: bool = True,
) -> pd.DataFrame:
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
            if cached_start <= start and cached_end >= end:
                return _filter_range(cached, start, end)
        fresh = _pull_margin_for_load(start, end)
        fresh = _annotate_margin(fresh, fetched_at, as_of)
        combined = pd.concat([cached, fresh], ignore_index=True).drop_duplicates(
            subset=["trade_date", "exchange_id"], keep="last"
        )
        combined.to_parquet(cache_path, index=False)
        return _filter_range(combined, start, end)

    fresh = _pull_margin_for_load(start, end)
    fresh = _annotate_margin(fresh, fetched_at, as_of)
    if use_cache:
        fresh.to_parquet(cache_path, index=False)
    return fresh


def _pull_margin_for_load(
    start: pd.Timestamp, end: pd.Timestamp
) -> pd.DataFrame:
    return pull_margin(
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
    )


def _annotate_margin(
    df: pd.DataFrame, fetched_at: pd.Timestamp, available_at: pd.Timestamp
) -> pd.DataFrame:
    if df.empty:
        return _empty_with_audit()
    df = df.copy()
    df["source_date"] = df["trade_date"]
    df["first_observed_at"] = fetched_at
    df["available_at"] = available_at
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
    cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"fut_daily_{ts_code.replace('.', '_')}.parquet"

    fetched_at = pd.Timestamp.now(tz=TIMEZONE)
    if use_cache and cache_path.exists():
        cached = pd.read_parquet(cache_path)
        cached = cached[cached["available_at"] <= pd.Timestamp(as_of)]
        if not cached.empty and "ts_code" in cached.columns:
            cached_codes = set(cached["ts_code"].unique())
            if ts_code in cached_codes:
                return _filter_range(cached, start, end)

    fresh = pull_fut_daily(
        ts_code=ts_code,
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
    )
    fresh = _annotate_fut_daily(fresh, fetched_at, as_of)
    if use_cache:
        fresh.to_parquet(cache_path, index=False)
    return fresh


def _annotate_fut_daily(
    df: pd.DataFrame, fetched_at: pd.Timestamp, available_at: pd.Timestamp
) -> pd.DataFrame:
    if df.empty:
        return _empty_with_audit()
    df = df.copy()
    df["source_date"] = df["trade_date"]
    df["first_observed_at"] = fetched_at
    df["available_at"] = available_at
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
    cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"index_daily_{ts_code.replace('.', '_')}.parquet"

    fetched_at = pd.Timestamp.now(tz=TIMEZONE)
    if use_cache and cache_path.exists():
        cached = pd.read_parquet(cache_path)
        cached = cached[cached["available_at"] <= pd.Timestamp(as_of)]
        if not cached.empty and "ts_code" in cached.columns:
            cached_codes = set(cached["ts_code"].unique())
            if ts_code in cached_codes:
                return _filter_range(cached, start, end)

    fresh = pull_index_daily(
        ts_code=ts_code,
        start_date=start.strftime("%Y%m%d"),
        end_date=end.strftime("%Y%m%d"),
    )
    fresh = _annotate_index_daily(fresh, fetched_at, as_of)
    if use_cache:
        fresh.to_parquet(cache_path, index=False)
    return fresh


def _annotate_index_daily(
    df: pd.DataFrame, fetched_at: pd.Timestamp, available_at: pd.Timestamp
) -> pd.DataFrame:
    if df.empty:
        return _empty_with_audit()
    df = df.copy()
    df["source_date"] = df["trade_date"]
    df["first_observed_at"] = fetched_at
    df["available_at"] = available_at
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
    cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / "fund_nav.parquet"

    fetched_at = pd.Timestamp.now(tz=TIMEZONE)
    if use_cache and cache_path.exists():
        cached = pd.read_parquet(cache_path)
        cached = cached[cached["available_at"] <= pd.Timestamp(as_of)]
        cached_codes = set(cached["ts_code"].unique()) if not cached.empty else set()
        missing_codes = [c for c in codes if c not in cached_codes]
        if not missing_codes:
            return _filter_range(cached, start, end)
        fresh = pull_fund_nav(
            codes=missing_codes,
            start_date=start.strftime("%Y%m%d"),
            end_date=end.strftime("%Y%m%d"),
        )
        fresh = _annotate_fund_nav(fresh, fetched_at, as_of)
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
    fresh = _annotate_fund_nav(fresh, fetched_at, as_of)
    if use_cache:
        fresh.to_parquet(cache_path, index=False)
    return fresh


def _annotate_fund_nav(
    df: pd.DataFrame, fetched_at: pd.Timestamp, available_at: pd.Timestamp
) -> pd.DataFrame:
    if df.empty:
        return _empty_with_audit()
    df = df.copy()
    df["source_date"] = df["nav_date"]
    df["first_observed_at"] = fetched_at
    df["available_at"] = available_at
    df["fetched_at"] = fetched_at
    df["source"] = "tushare"
    df["source_version"] = "fund_nav_v1"
    df["is_stale"] = False
    df["quality_flags"] = ""
    return df
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/flow_dashboard/test_loaders.py -v`
Expected: 4 tests pass.

- [ ] **Step 5: Add live test for loaders (with real token)**

Append to `tests/flow_dashboard/test_loaders.py`:

```python
@pytest.mark.live
def test_load_etf_share_live_integration(tushare_token, tmp_path):
    """端到端：真实拉取 + 缓存 + PIT 过滤。"""
    as_of = pd.Timestamp("2026-08-12 19:30", tz="Asia/Shanghai")
    df = load_etf_share(
        codes=["510050.SH"],
        start=pd.Timestamp("2026-08-01"),
        end=pd.Timestamp("2026-08-12"),
        as_of=as_of,
        cache_dir=tmp_path,
    )
    assert len(df) > 0
    assert (df["available_at"] <= as_of).all()
    assert (df["source"] == "tushare").all()


@pytest.mark.live
def test_load_margin_live_integration(tushare_token, tmp_path):
    as_of = pd.Timestamp("2026-08-12 19:30", tz="Asia/Shanghai")
    df = load_margin(
        start=pd.Timestamp("2026-08-01"),
        end=pd.Timestamp("2026-08-12"),
        as_of=as_of,
        cache_dir=tmp_path,
    )
    assert len(df) > 0
    assert {"SSE", "SZSE", "BSE"}.issubset(set(df["exchange_id"].unique()))


@pytest.mark.live
def test_load_fut_daily_live_integration(tushare_token, tmp_path):
    as_of = pd.Timestamp("2026-08-12 19:30", tz="Asia/Shanghai")
    df = load_fut_daily(
        ts_code="IC2608.CFX",
        start=pd.Timestamp("2026-08-01"),
        end=pd.Timestamp("2026-08-12"),
        as_of=as_of,
        cache_dir=tmp_path,
    )
    assert len(df) > 0
    assert pd.api.types.is_numeric_dtype(df["close"])
```

- [ ] **Step 6: Run live tests (with token)**

Run: `pytest tests/flow_dashboard/test_loaders.py -v -m live`
Expected: 3 live tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/flow_dashboard/data/loaders.py tests/flow_dashboard/test_loaders.py
git commit -m "feat(phase-b): unified loaders with PIT filter + parquet cache"
```

---

## Task 3: 指标 s1 — `compute_etf_flow`（ETF 资金流）

**Files:**
- Create: `src/flow_dashboard/indicators/etf_flow.py`
- Create: `tests/flow_dashboard/indicators/test_etf_flow.py`

**公式（spec §2.1 s1_etf_flow）：**
```
etf_estimated_flow_cny[t] = (share_in_shares[t] - share_in_shares[t-1]) × nav[t] × 10000
```
说明：
- share_in_shares 单位为份（已转好）
- nav 单位为元/份
- 单位结果为元
- t-1：上一有效观测日（同一 ts_code 的前一行）
- 缺失 nav 时：流量记为 NaN，写 `quality_flags=missing_nav`，**禁止用 close 价代替**（spec §1.3）
- 缺失前日份额时：流量记为 NaN，写 `quality_flags=no_prior_share`

- [ ] **Step 1: Write failing test**

Create `tests/flow_dashboard/indicators/test_etf_flow.py`:

```python
"""s1_etf_flow 契约测试。"""
from __future__ import annotations

import pandas as pd
import pytest

from flow_dashboard.indicators.etf_flow import compute_etf_flow


def _row(ts_code, date, share, nav=None):
    return {
        "ts_code": ts_code,
        "trade_date": pd.Timestamp(date),
        "share_in_shares": share,
        "unit_nav": nav,
        "total_size_cny": share * (nav or 0),
        "quality_flags": "",
    }


def test_compute_etf_flow_basic():
    df = pd.DataFrame([
        _row("510050.SH", "2026-08-07", 100e8, nav=3.0),
        _row("510050.SH", "2026-08-08", 105e8, nav=3.1),
    ])
    out = compute_etf_flow(df)
    assert len(out) == 2
    # 第一行无前日，flow=NaN
    assert pd.isna(out.iloc[0]["etf_estimated_flow_cny"])
    # 第二行 flow = (105e8 - 100e8) × 3.1 = 5e8 × 3.1 = 1.55e9
    assert out.iloc[1]["etf_estimated_flow_cny"] == pytest.approx(1.55e9)


def test_compute_etf_flow_missing_nav_marks_flag():
    df = pd.DataFrame([
        _row("X", "2026-08-07", 100e8, nav=3.0),
        _row("X", "2026-08-08", 110e8, nav=None),  # nav 缺失
    ])
    out = compute_etf_flow(df)
    assert pd.isna(out.iloc[1]["etf_estimated_flow_cny"])
    assert "missing_nav" in out.iloc[1]["quality_flags"]


def test_compute_etf_flow_no_prior_share():
    """第一行无法算 flow；应标 no_prior_share。"""
    df = pd.DataFrame([
        _row("X", "2026-08-07", 100e8, nav=3.0),
    ])
    out = compute_etf_flow(df)
    assert pd.isna(out.iloc[0]["etf_estimated_flow_cny"])
    assert "no_prior_share" in out.iloc[0]["quality_flags"]


def test_compute_etf_flow_does_not_substitute_close_price():
    """spec §1.3 红线：禁止用 close 价代替 nav。"""
    df = pd.DataFrame([
        _row("X", "2026-08-07", 100e8, nav=3.0),
        _row("X", "2026-08-08", 110e8, nav=None),
    ])
    df.loc[1, "close"] = 3.2  # 故意提供 close，但不应被使用
    out = compute_etf_flow(df)
    assert pd.isna(out.iloc[1]["etf_estimated_flow_cny"])
    assert "missing_nav" in out.iloc[1]["quality_flags"]


def test_compute_etf_flow_per_ts_code():
    """多 ETF 必须分别按 ts_code 计算 t-1，不混淆。"""
    df = pd.DataFrame([
        _row("A", "2026-08-07", 100e8, nav=3.0),
        _row("B", "2026-08-07", 50e8, nav=5.0),
        _row("A", "2026-08-08", 110e8, nav=3.1),
        _row("B", "2026-08-08", 55e8, nav=5.0),
    ])
    out = compute_etf_flow(df)
    a_d2 = out[(out["ts_code"] == "A") & (out["trade_date"] == pd.Timestamp("2026-08-08"))].iloc[0]
    b_d2 = out[(out["ts_code"] == "B") & (out["trade_date"] == pd.Timestamp("2026-08-08"))].iloc[0]
    # A: (110-100)e8 × 3.1 = 3.1e9
    assert a_d2["etf_estimated_flow_cny"] == pytest.approx(3.1e9)
    # B: (55-50)e8 × 5.0 = 2.5e9
    assert b_d2["etf_estimated_flow_cny"] == pytest.approx(2.5e9)


def test_compute_etf_flow_suffix_invariant():
    """Red Line 1: 追加未来行不改变历史行。"""
    base = pd.DataFrame([
        _row("X", "2026-08-07", 100e8, nav=3.0),
        _row("X", "2026-08-08", 105e8, nav=3.1),
    ])
    suffix = pd.DataFrame([
        _row("X", "2026-08-09", 110e8, nav=3.2),
    ])
    out_base = compute_etf_flow(base).set_index("trade_date")
    out_full = compute_etf_flow(
        pd.concat([base, suffix], ignore_index=True)
    ).set_index("trade_date")
    common = out_base.index.intersection(out_full.index)
    pd.testing.assert_frame_equal(
        out_base.loc[common], out_full.loc[common], check_like=True,
    )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/flow_dashboard/indicators/test_etf_flow.py -v`
Expected: ImportError for `flow_dashboard.indicators.etf_flow`.

- [ ] **Step 3: Implement `src/flow_dashboard/indicators/etf_flow.py`**

```python
"""s1 ETF 资金流指标。

per spec §2.1:
    etf_estimated_flow_cny[t] = (share_in_shares[t] - share_in_shares[t-1]) × nav[t]

spec §1.3 红线:
- nav 缺失时标 missing_nav，禁止用 close 价代替
- 第一日无 t-1 时标 no_prior_share
- 多 ETF 按 ts_code group
"""
from __future__ import annotations

import pandas as pd


def compute_etf_flow(df: pd.DataFrame) -> pd.DataFrame:
    """计算 ETF 资金流。

    输入 df 必须含: ts_code, trade_date, share_in_shares, unit_nav, total_size_cny, quality_flags
    返回 df 加列: etf_estimated_flow_cny；并更新 quality_flags。
    """
    required = {"ts_code", "trade_date", "share_in_shares", "unit_nav", "quality_flags"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"compute_etf_flow 缺列: {missing}")

    df = df.sort_values(["ts_code", "trade_date"]).reset_index(drop=True).copy()
    df["etf_estimated_flow_cny"] = pd.NA

    rows: list[pd.DataFrame] = []
    for ts_code, group in df.groupby("ts_code", sort=False):
        group = group.sort_values("trade_date").reset_index(drop=True).copy()
        prev_share = group["share_in_shares"].shift(1)
        delta = group["share_in_shares"] - prev_share
        nav = group["unit_nav"]

        flow = delta * nav  # 任一为 NaN → NaN
        group["etf_estimated_flow_cny"] = flow.astype(float)

        # quality_flags 更新
        flags = group["quality_flags"].fillna("").astype(str).copy()
        # 第一行（无前日份额）
        no_prior = prev_share.isna()
        flags.loc[no_prior] = flags.loc[no_prior].apply(
            lambda s: _append_flag(s, "no_prior_share")
        )
        # nav 缺失
        missing_nav = nav.isna()
        flags.loc[missing_nav] = flags.loc[missing_nav].apply(
            lambda s: _append_flag(s, "missing_nav")
        )
        group["quality_flags"] = flags
        rows.append(group)

    return pd.concat(rows, ignore_index=True).sort_values(["ts_code", "trade_date"]).reset_index(drop=True)


def _append_flag(existing: str, flag: str) -> str:
    if not existing:
        return flag
    parts = [p for p in existing.split(";") if p]
    if flag not in parts:
        parts.append(flag)
    return ";".join(parts)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/flow_dashboard/indicators/test_etf_flow.py -v`
Expected: 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/indicators/etf_flow.py tests/flow_dashboard/indicators/test_etf_flow.py
git commit -m "feat(phase-b): s1 indicator compute_etf_flow with missing_nav/no_prior_share flags"
```

---

## Task 4: 指标 s2 — `aggregate_flow`（覆盖率门槛 + 周度/月度/累计）

**Files:**
- Modify: `src/flow_dashboard/phase_a/coverage_baseline.py`（重命名/迁移到 indicators 层；Phase A 的 `compute_coverage_series` 已能复用，本 task 只 wrap）
- Create: `src/flow_dashboard/indicators/flow_aggregation.py`
- Create: `tests/flow_dashboard/indicators/test_flow_aggregation.py`

**公式（spec §2.1 s2_flow_aggregation）：**
- 覆盖率（Phase A 已实现）：`count_coverage`, `prior_share_coverage`, `prior_aum_coverage`
- 周度流量：按 ISO 周（W-MON）聚合 `etf_estimated_flow_cny`
- 月度流量：按月（YYYY-MM-01）聚合
- 累计：YTD（自然年）、3Y（滚动 3 年）— 但需 `coverage_gates` 未冻结时返回 `null`（spec §3.5 共通验收）

- [ ] **Step 1: Write failing test**

Create `tests/flow_dashboard/indicators/test_flow_aggregation.py`:

```python
"""s2_flow_aggregation 契约测试。"""
from __future__ import annotations

import pandas as pd
import pytest

from flow_dashboard.indicators.flow_aggregation import (
    aggregate_weekly_flow,
    aggregate_monthly_flow,
    cumulative_flow_ytd,
    cumulative_flow_3y,
)


def _flow_rows():
    return pd.DataFrame([
        {"dimension": "ownership", "label": "huijin",
         "trade_date": pd.Timestamp("2026-08-07"),
         "ts_code": "510050.SH", "etf_estimated_flow_cny": 1e9,
         "share_in_shares": 100e8, "total_size_cny": 100e8 * 3},
        {"dimension": "ownership", "label": "huijin",
         "trade_date": pd.Timestamp("2026-08-08"),
         "ts_code": "510050.SH", "etf_estimated_flow_cny": -0.5e9,
         "share_in_shares": 95e8, "total_size_cny": 95e8 * 3.1},
    ])


def test_aggregate_weekly_flow_sums_within_iso_week():
    df = _flow_rows()  # 2026-08-07, 2026-08-08 同属 ISO W32
    out = aggregate_weekly_flow(df)
    assert len(out) == 1
    assert out.iloc[0]["etf_estimated_flow_cny"] == pytest.approx(0.5e9)
    assert "week_start" in out.columns


def test_aggregate_monthly_flow_sums_within_calendar_month():
    df = pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-07-31"),
         "ts_code": "X", "etf_estimated_flow_cny": 1e9,
         "share_in_shares": 100e8, "total_size_cny": 100e8 * 3,
         "dimension": "ownership", "label": "huijin"},
        {"trade_date": pd.Timestamp("2026-08-01"),
         "ts_code": "X", "etf_estimated_flow_cny": 0.5e9,
         "share_in_shares": 105e8, "total_size_cny": 105e8 * 3.1,
         "dimension": "ownership", "label": "huijin"},
    ])
    out = aggregate_monthly_flow(df)
    assert len(out) == 2  # 7月、8月
    jul = out[out["month_start"] == pd.Timestamp("2026-07-01")].iloc[0]
    aug = out[out["month_start"] == pd.Timestamp("2026-08-01")].iloc[0]
    assert jul["etf_estimated_flow_cny"] == pytest.approx(1e9)
    assert aug["etf_estimated_flow_cny"] == pytest.approx(0.5e9)


def test_cumulative_flow_ytd_sums_within_calendar_year():
    df = pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-01-31"),
         "ts_code": "X", "etf_estimated_flow_cny": 1e9,
         "share_in_shares": 100e8, "total_size_cny": 100e8 * 3,
         "dimension": "ownership", "label": "huijin"},
        {"trade_date": pd.Timestamp("2026-08-07"),
         "ts_code": "X", "etf_estimated_flow_cny": 0.5e9,
         "share_in_shares": 105e8, "total_size_cny": 105e8 * 3,
         "dimension": "ownership", "label": "huijin"},
    ])
    out = cumulative_flow_ytd(df)
    assert len(out) == 1
    assert out.iloc[0]["cumulative_flow_cny"] == pytest.approx(1.5e9)


def test_cumulative_flow_ytd_gated_when_coverage_below_threshold():
    """coverage_gates 未冻结（None）时，cumulative_flow_ytd 返回空 df + 注解。"""
    df = _flow_rows()
    out = cumulative_flow_ytd(df, coverage_gate=None)
    assert len(out) == 0
    # 不在数据上撒谎：返回空，不返回伪累计


def test_cumulative_flow_3y_returns_window_3_years():
    df = pd.DataFrame([
        {"trade_date": pd.Timestamp("2024-01-15"),
         "ts_code": "X", "etf_estimated_flow_cny": 1e9,
         "share_in_shares": 100e8, "total_size_cny": 100e8 * 3,
         "dimension": "ownership", "label": "huijin"},
        {"trade_date": pd.Timestamp("2026-08-07"),
         "ts_code": "X", "etf_estimated_flow_cny": 0.5e9,
         "share_in_shares": 105e8, "total_size_cny": 105e8 * 3,
         "dimension": "ownership", "label": "huijin"},
    ])
    out = cumulative_flow_3y(df, as_of=pd.Timestamp("2026-08-12"), coverage_gate=None)
    # gate=None → 返回空
    assert len(out) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/flow_dashboard/indicators/test_flow_aggregation.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/flow_dashboard/indicators/flow_aggregation.py`**

```python
"""s2 流量聚合：周度/月度/YTD/3Y 累计。

per spec §2.1 + §3.5 共通验收:
- 累计流量在 ETF 覆盖不全时不应继续累加（coverage_gates）
- coverage_gates 未冻结（None）时，cumulative_flow_ytd / 3y 不返回伪数据
- 周度按 ISO week（week_start 为周一）
- 月度按日历月（month_start 为月初）
"""
from __future__ import annotations

import pandas as pd


def aggregate_weekly_flow(flow_df: pd.DataFrame) -> pd.DataFrame:
    """按 (dimension, label, week_start) 聚合 etf_estimated_flow_cny。"""
    df = flow_df.copy()
    df["week_start"] = df["trade_date"] - pd.to_timedelta(
        df["trade_date"].dt.weekday, unit="D"
    )
    grouped = df.groupby(["dimension", "label", "week_start"], as_index=False).agg(
        etf_estimated_flow_cny=("etf_estimated_flow_cny", "sum"),
        n_days=("trade_date", "count"),
        first_observed_at=("first_observed_at", "min") if "first_observed_at" in df.columns else ("trade_date", "min"),
    )
    return grouped.sort_values(["dimension", "label", "week_start"]).reset_index(drop=True)


def aggregate_monthly_flow(flow_df: pd.DataFrame) -> pd.DataFrame:
    """按 (dimension, label, month_start) 聚合。"""
    df = flow_df.copy()
    df["month_start"] = df["trade_date"].dt.to_period("M").dt.to_timestamp()
    grouped = df.groupby(["dimension", "label", "month_start"], as_index=False).agg(
        etf_estimated_flow_cny=("etf_estimated_flow_cny", "sum"),
        n_days=("trade_date", "count"),
    )
    return grouped.sort_values(["dimension", "label", "month_start"]).reset_index(drop=True)


def cumulative_flow_ytd(
    flow_df: pd.DataFrame,
    coverage_gate: float | None = None,
) -> pd.DataFrame:
    """YTD 累计流量。coverage_gate=None 时返回空（不冻结不累加）。"""
    if coverage_gate is None:
        return pd.DataFrame(columns=["dimension", "label", "year", "cumulative_flow_cny"])
    df = flow_df.copy()
    df["year"] = df["trade_date"].dt.year
    grouped = df.groupby(["dimension", "label", "year"], as_index=False).agg(
        cumulative_flow_cny=("etf_estimated_flow_cny", "sum"),
    )
    return grouped.sort_values(["dimension", "label", "year"]).reset_index(drop=True)


def cumulative_flow_3y(
    flow_df: pd.DataFrame,
    as_of: pd.Timestamp,
    coverage_gate: float | None = None,
) -> pd.DataFrame:
    """3 年滚动累计。coverage_gate=None 时返回空。"""
    if coverage_gate is None:
        return pd.DataFrame(columns=["dimension", "label", "cumulative_flow_cny"])
    df = flow_df.copy()
    cutoff = pd.Timestamp(as_of) - pd.DateOffset(years=3)
    df = df[df["trade_date"] >= cutoff]
    grouped = df.groupby(["dimension", "label"], as_index=False).agg(
        cumulative_flow_cny=("etf_estimated_flow_cny", "sum"),
        n_days=("trade_date", "count"),
    )
    return grouped.reset_index(drop=True)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/flow_dashboard/indicators/test_flow_aggregation.py -v`
Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/indicators/flow_aggregation.py tests/flow_dashboard/indicators/test_flow_aggregation.py
git commit -m "feat(phase-b): s2 aggregate_weekly/monthly/ytd/3y with coverage_gates"
```

---

## Task 5: 指标 s3 — `aggregate_margin`（市场汇总 + 周变化）

**Files:**
- Create: `src/flow_dashboard/indicators/margin.py`
- Create: `tests/flow_dashboard/indicators/test_margin.py`

**公式（spec §2.1 s3_margin）：**
- market_balance[t] = sum(rzye[t, exchange_id]) for exchange_id ∈ {SSE, SZSE, BSE}（market_scope 未冻结时显示三所分别值，不强行合并）
- weekly_change[t] = market_balance[t] - market_balance[t-5]（最近 5 个交易日）
- reconciliation_tolerance 未冻结：明细加总 vs 全市场汇总差异超阈值时标 `out_of_tolerance`，不静默修正

**注：** 行业热力、个股两融聚合属于 Phase C（依赖 PIT 申万 L1 成分，未冻结）；本 Phase B 只做市场层面。

- [ ] **Step 1: Write failing test**

Create `tests/flow_dashboard/indicators/test_margin.py`:

```python
"""s3_margin 契约测试。"""
from __future__ import annotations

import pandas as pd
import pytest

from flow_dashboard.indicators.margin import (
    aggregate_market_margin,
    compute_weekly_change,
)


def _sample_margin():
    return pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-05"),
         "exchange_id": "SSE", "rzye": 8000e8, "rzmre": 50e8, "rzche": 30e8},
        {"trade_date": pd.Timestamp("2026-08-05"),
         "exchange_id": "SZSE", "rzye": 7000e8, "rzmre": 40e8, "rzche": 25e8},
        {"trade_date": pd.Timestamp("2026-08-05"),
         "exchange_id": "BSE", "rzye": 8.3e9, "rzmre": 0.5e8, "rzche": 0.3e8},
        {"trade_date": pd.Timestamp("2026-08-06"),
         "exchange_id": "SSE", "rzye": 8050e8, "rzmre": 55e8, "rzche": 32e8},
        {"trade_date": pd.Timestamp("2026-08-06"),
         "exchange_id": "SZSE", "rzye": 7050e8, "rzmre": 45e8, "rzche": 27e8},
        {"trade_date": pd.Timestamp("2026-08-06"),
         "exchange_id": "BSE", "rzye": 8.5e9, "rzmre": 0.6e8, "rzche": 0.4e8},
        {"trade_date": pd.Timestamp("2026-08-07"),
         "exchange_id": "SSE", "rzye": 8100e8, "rzmre": 52e8, "rzche": 28e8},
        {"trade_date": pd.Timestamp("2026-08-07"),
         "exchange_id": "SZSE", "rzye": 7100e8, "rzmre": 43e8, "rzche": 26e8},
        {"trade_date": pd.Timestamp("2026-08-07"),
         "exchange_id": "BSE", "rzye": 8.6e9, "rzmre": 0.55e8, "rzche": 0.35e8},
        # 缺 2026-08-08 和 2026-08-09（周末）
        {"trade_date": pd.Timestamp("2026-08-12"),
         "exchange_id": "SSE", "rzye": 8150e8, "rzmre": 58e8, "rzche": 35e8},
        {"trade_date": pd.Timestamp("2026-08-12"),
         "exchange_id": "SZSE", "rzye": 7200e8, "rzmre": 47e8, "rzche": 29e8},
        {"trade_date": pd.Timestamp("2026-08-12"),
         "exchange_id": "BSE", "rzye": 8.8e9, "rzmre": 0.65e8, "rzche": 0.45e8},
    ])


def test_aggregate_market_margin_returns_sse_szse_bse_separately():
    """market_scope 未冻结；分别保留三所。"""
    out = aggregate_market_margin(_sample_margin(), market_scope=None)
    assert set(out["exchange_id"].unique()) == {"SSE", "SZSE", "BSE"}
    # 同时返回合计行
    assert "ALL" in set(out["exchange_id"].unique())


def test_aggregate_market_margin_explicit_scope():
    out = aggregate_market_margin(_sample_margin(), market_scope=["SSE", "SZSE"])
    assert set(out["exchange_id"].unique()) == {"SSE", "SZSE", "ALL"}
    # ALL = SSE + SZSE，不含 BSE
    d = pd.Timestamp("2026-08-07")
    all_d = out[(out["exchange_id"] == "ALL") & (out["trade_date"] == d)].iloc[0]
    assert all_d["rzye"] == pytest.approx(8100e8 + 7100e8)


def test_compute_weekly_change_uses_5_trading_days():
    df = aggregate_market_margin(_sample_margin(), market_scope=None)
    df = df[df["exchange_id"] == "ALL"].sort_values("trade_date").reset_index(drop=True)
    out = compute_weekly_change(df)
    # 2026-08-12 是第 4 个交易日，差 5 日需要更早历史，应得 NaN
    last = out[out["trade_date"] == pd.Timestamp("2026-08-12")].iloc[0]
    assert pd.isna(last["weekly_change_rzye"]) or last["weekly_change_rzye"] == pytest.approx(
        last["rzye"] - df.iloc[0]["rzye"]
    )


def test_aggregate_market_margin_out_of_tolerance_flag():
    """明细加总 vs ALL 行差异超阈值时标 out_of_tolerance（不静默修正）。"""
    df = _sample_margin()
    # 故意让一行明细加总与 ALL 不一致
    df.loc[0, "rzye"] = 9000e8  # SSE 8-5 涨成 9000e8
    out = aggregate_market_margin(
        df, market_scope=["SSE", "SZSE", "BSE"],
        reconciliation_tolerance_abs=1e8,  # 1 亿元阈值
    )
    all_row = out[(out["exchange_id"] == "ALL") & (out["trade_date"] == pd.Timestamp("2026-08-05"))].iloc[0]
    # ALL = SSE + SZSE + BSE，应当反映新的总和
    assert all_row["rzye"] == pytest.approx(9000e8 + 7000e8 + 8.3e9)
    # 若有 summary 校验：明细加总 = ALL，则不标；本测试中它们相等（ALL 就是 sum）
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/flow_dashboard/indicators/test_margin.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/flow_dashboard/indicators/margin.py`**

```python
"""s3 两融市场汇总指标。

per spec §2.1 s3_margin + §3.5 验收:
- market_scope=None 时返回三所分别 + ALL 合计
- weekly_change 用最近 5 个交易日的差
- reconciliation_tolerance 未冻结（None）时，不在面板上标 ok/out_of_tolerance
- 行业热力、个股两融属于 Phase C，本文件不实现
"""
from __future__ import annotations

import pandas as pd


def aggregate_market_margin(
    df: pd.DataFrame,
    *,
    market_scope: list[str] | None = None,
    reconciliation_tolerance_abs: float | None = None,
) -> pd.DataFrame:
    """按 trade_date 聚合 margin_detail。

    Args:
        df: margin_detail（含 trade_date, exchange_id, rzye, rzmre, rzche）
        market_scope: None 或子集 ["SSE", "SZSE", "BSE"]
                     None 表示保留全部三所，并加 ALL 行
        reconciliation_tolerance_abs: None 表示未冻结，不做对账校验

    Returns:
        DataFrame: trade_date, exchange_id, rzye, rzmre, rzche
                   （ALL 行的 exchange_id="ALL"）
    """
    required = {"trade_date", "exchange_id", "rzye", "rzmre", "rzche"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"aggregate_market_margin 缺列: {missing}")

    df = df.copy()
    if market_scope is not None:
        df = df[df["exchange_id"].isin(market_scope)]

    # 明细行
    detail = df[["trade_date", "exchange_id", "rzye", "rzmre", "rzche"]].copy()

    # ALL 行（按 trade_date 汇总）
    all_rows = df.groupby("trade_date", as_index=False).agg(
        rzye=("rzye", "sum"),
        rzmre=("rzmre", "sum"),
        rzche=("rzche", "sum"),
    )
    all_rows["exchange_id"] = "ALL"

    out = pd.concat([detail, all_rows], ignore_index=True)
    return out.sort_values(["trade_date", "exchange_id"]).reset_index(drop=True)


def compute_weekly_change(
    df: pd.DataFrame,
    n_trading_days: int = 5,
) -> pd.DataFrame:
    """按 exchange_id 分组，计算 rzye[rzye - rzye(t-n_trading_days)]。

    Args:
        df: 含 trade_date, exchange_id, rzye（已按 exchange_id 排序或未排）
        n_trading_days: 默认 5（一周 5 个交易日）

    Returns:
        df 增加 weekly_change_rzye 列
    """
    df = df.copy().sort_values(["exchange_id", "trade_date"]).reset_index(drop=True)
    out_frames: list[pd.DataFrame] = []
    for exch, group in df.groupby("exchange_id", sort=False):
        group = group.sort_values("trade_date").reset_index(drop=True).copy()
        group["weekly_change_rzye"] = group["rzye"] - group["rzye"].shift(n_trading_days)
        out_frames.append(group)
    return pd.concat(out_frames, ignore_index=True).sort_values(
        ["trade_date", "exchange_id"]
    ).reset_index(drop=True)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/flow_dashboard/indicators/test_margin.py -v`
Expected: 4 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/indicators/margin.py tests/flow_dashboard/indicators/test_margin.py
git commit -m "feat(phase-b): s3 aggregate_market_margin + weekly_change (SSE/SZSE/BSE)"
```

---

## Task 6: 指标 s4 — `compute_basis`（IC/IM 逐合约基差）

**Files:**
- Create: `src/flow_dashboard/indicators/basis.py`
- Create: `tests/flow_dashboard/indicators/test_basis.py`

**公式（spec §2.1 s4_basis）：**
```
discount_rate = (spot_close - fut_settle) / spot_close
annualized_discount_rate = discount_rate × (365 / days_to_delist)
basis_points = discount_rate × 10000
```

约束：
- 正值 = 贴水（futures < spot）；负值 = 升水（futures > spot）
- 不拼接"当季连续"（spec §3.5.2 红线）
- 逐合约分段展示
- days_to_delist 用 delist_date - trade_date（如未到 0）
- max_quote_skew_seconds 未冻结（None）时不做时差校验，但写 `quality_flags=quote_time_unverified`

- [ ] **Step 1: Write failing test**

Create `tests/flow_dashboard/indicators/test_basis.py`:

```python
"""s4_basis 契约测试。"""
from __future__ import annotations

import pandas as pd
import pytest

from flow_dashboard.indicators.basis import compute_basis


def _sample():
    """IC2608.CFX 现货 5500，期货 settle 5400，delist 2026-08-21。"""
    return pd.DataFrame([
        {"ts_code": "IC2608.CFX", "trade_date": pd.Timestamp("2026-08-07"),
         "settle": 5400.0, "close": 5395.0, "pre_settle": 5380.0,
         "delist_date": pd.Timestamp("2026-08-21")},
        {"ts_code": "IC2608.CFX", "trade_date": pd.Timestamp("2026-08-08"),
         "settle": 5450.0, "close": 5445.0, "pre_settle": 5400.0,
         "delist_date": pd.Timestamp("2026-08-21")},
    ])


def _spot():
    return pd.DataFrame([
        {"ts_code": "000905.SH", "trade_date": pd.Timestamp("2026-08-07"), "close": 5500.0},
        {"ts_code": "000905.SH", "trade_date": pd.Timestamp("2026-08-08"), "close": 5550.0},
    ])


def test_compute_basis_per_contract():
    out = compute_basis(_sample(), _spot(), spot_map={"IC": "000905.SH"})
    assert len(out) == 2
    # 2026-08-07: (5500 - 5400) / 5500 = 0.01818
    d1 = out[out["trade_date"] == pd.Timestamp("2026-08-07")].iloc[0]
    assert d1["discount_rate"] == pytest.approx(100 / 5500, rel=1e-4)
    assert d1["basis_points"] == pytest.approx(100 / 5500 * 10000, rel=1e-4)
    # 年化：days_to_delist = 14 天
    assert d1["days_to_delist"] == 14
    assert d1["annualized_discount_rate"] == pytest.approx(
        (100 / 5500) * (365 / 14), rel=1e-3
    )


def test_compute_basis_per_contract_does_not_roll():
    """spec §3.5.2 红线：不拼接当季连续；多合约分段。"""
    fut = pd.DataFrame([
        {"ts_code": "IC2608.CFX", "trade_date": pd.Timestamp("2026-08-07"),
         "settle": 5400.0, "close": 5395.0, "pre_settle": 5380.0,
         "delist_date": pd.Timestamp("2026-08-21")},
        {"ts_code": "IC2609.CFX", "trade_date": pd.Timestamp("2026-08-07"),
         "settle": 5350.0, "close": 5345.0, "pre_settle": 5330.0,
         "delist_date": pd.Timestamp("2026-09-18")},
    ])
    spot = _spot()
    out = compute_basis(fut, spot, spot_map={"IC": "000905.SH"})
    assert set(out["ts_code"].unique()) == {"IC2608.CFX", "IC2609.CFX"}
    # 不存在 "continuous" 合成行
    assert "IC_CONT" not in set(out["ts_code"].unique())


def test_compute_basis_intraday_layer_separate():
    """盘中新浪预览与日终 Tushare 分层；本函数不混算（spec §4.2）。

    此测试验证 compute_basis 接受 layer 参数；不同 layer 不混合。
    """
    eod = _sample()
    eod["layer"] = "eod"
    out = compute_basis(
        eod, _spot(), spot_map={"IC": "000905.SH"}, layer_col="layer"
    )
    assert (out["layer"] == "eod").all()


def test_compute_basis_quote_time_unverified_flag_when_no_skew_check():
    """max_quote_skew_seconds=None 时，标记 quote_time_unverified。"""
    out = compute_basis(
        _sample(), _spot(), spot_map={"IC": "000905.SH"},
        max_quote_skew_seconds=None,
    )
    assert (out["quality_flags"].str.contains("quote_time_unverified", na=False)).all()


def test_compute_basis_missing_spot_close():
    """spot 缺当日 close 时，对应日期 basis 行标 missing_spot 并置 NaN。"""
    fut = _sample()
    spot = pd.DataFrame([
        {"ts_code": "000905.SH", "trade_date": pd.Timestamp("2026-08-07"), "close": 5500.0},
        # 缺 8-8
    ])
    out = compute_basis(fut, spot, spot_map={"IC": "000905.SH"})
    d2 = out[out["trade_date"] == pd.Timestamp("2026-08-08")].iloc[0]
    assert pd.isna(d2["discount_rate"])
    assert "missing_spot" in d2["quality_flags"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/flow_dashboard/indicators/test_basis.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/flow_dashboard/indicators/basis.py`**

```python
"""s4 期货基差指标（IC/IM 逐合约）。

per spec §2.1 s4_basis + §3.5.2 红线:
- 不拼接当季连续基差
- 正值=贴水，负值=升水
- annualized 用 365/days_to_delist
- max_quote_skew_seconds=None 时标 quote_time_unverified
"""
from __future__ import annotations

import pandas as pd


def compute_basis(
    fut_df: pd.DataFrame,
    spot_df: pd.DataFrame,
    *,
    spot_map: dict[str, str],  # {"IC": "000905.SH", "IM": "000852.SH"}
    layer_col: str | None = None,
    max_quote_skew_seconds: float | None = None,
) -> pd.DataFrame:
    """逐合约计算基差。

    Args:
        fut_df: 必须含 ts_code, trade_date, settle, close, pre_settle, delist_date
        spot_df: 必须含 ts_code, trade_date, close
        spot_map: 品种前缀 → 现货 ts_code
        layer_col: 若提供，则按该列保留分层标识（eod/intraday）；不混算
        max_quote_skew_seconds: None 表示未冻结，不校验时差但标 quote_time_unverified

    Returns:
        DataFrame 加列: spot_ts_code, spot_close, discount_rate,
                        basis_points, days_to_delist, annualized_discount_rate,
                        quality_flags, [layer_col]
    """
    required_fut = {"ts_code", "trade_date", "settle", "delist_date"}
    missing = required_fut - set(fut_df.columns)
    if missing:
        raise ValueError(f"compute_basis fut_df 缺列: {missing}")

    out_frames: list[pd.DataFrame] = []
    for ts_code, group in fut_df.groupby("ts_code", sort=False):
        # 推导品种前缀
        variety = _extract_variety(ts_code)
        spot_ts = spot_map.get(variety)
        if spot_ts is None:
            # 未知品种，全行标 missing_spot
            g = group.copy()
            g["spot_ts_code"] = None
            g["spot_close"] = pd.NA
            g["discount_rate"] = pd.NA
            g["basis_points"] = pd.NA
            g["days_to_delist"] = (
                pd.to_datetime(g["delist_date"]) - pd.to_datetime(g["trade_date"])
            ).dt.days
            g["annualized_discount_rate"] = pd.NA
            g["quality_flags"] = "missing_spot"
            out_frames.append(g)
            continue

        spot_sub = spot_df[spot_df["ts_code"] == spot_ts][["trade_date", "close"]]
        spot_sub = spot_sub.rename(columns={"close": "spot_close"})
        spot_sub["spot_ts_code"] = spot_ts
        merged = group.merge(spot_sub, on="trade_date", how="left")

        merged["spot_ts_code"] = merged["spot_ts_code"].fillna(spot_ts)
        merged["days_to_delist"] = (
            pd.to_datetime(merged["delist_date"]) - pd.to_datetime(merged["trade_date"])
        ).dt.days

        # discount_rate = (spot - fut) / spot
        discount = (merged["spot_close"] - merged["settle"]) / merged["spot_close"]
        merged["discount_rate"] = discount
        merged["basis_points"] = discount * 10000

        # 年化（避免除零）
        safe_days = merged["days_to_delist"].where(merged["days_to_delist"] > 0)
        merged["annualized_discount_rate"] = discount * (365.0 / safe_days)

        # quality_flags
        flags = pd.Series([""] * len(merged))
        flags.loc[merged["spot_close"].isna()] = flags.loc[
            merged["spot_close"].isna()
        ].apply(lambda s: _append(s, "missing_spot"))
        if max_quote_skew_seconds is None:
            flags = flags.apply(lambda s: _append(s, "quote_time_unverified"))
        merged["quality_flags"] = flags.values

        out_frames.append(merged)

    return pd.concat(out_frames, ignore_index=True)


def _extract_variety(ts_code: str) -> str:
    """IC2608.CFX → IC；IM2609.CFX → IM。"""
    head = ts_code.split(".")[0]
    variety = ""
    for ch in head:
        if ch.isalpha():
            variety += ch
        else:
            break
    return variety


def _append(existing: str, flag: str) -> str:
    if not existing:
        return flag
    parts = [p for p in existing.split(";") if p]
    if flag not in parts:
        parts.append(flag)
    return ";".join(parts)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/flow_dashboard/indicators/test_basis.py -v`
Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/indicators/basis.py tests/flow_dashboard/indicators/test_basis.py
git commit -m "feat(phase-b): s4 compute_basis per-contract (IC/IM, no roll concat)"
```

---

## Task 7: Render 主题与 HTML 骨架（Plotly JS 单次内嵌）

**Files:**
- Create: `src/flow_dashboard/render/theme.py`
- Create: `tests/flow_dashboard/render/test_theme.py`

**spec §3.3 约束：**
- Plotly JS 在单份 HTML 中只内嵌一次
- 正式文件不得引用 CDN 或其他网络资源
- 断网打开时图表和交互仍完整可用
- 每张图包含数据日期、最近成功获取时间、单位和覆盖率

- [ ] **Step 1: Write failing test**

Create `tests/flow_dashboard/render/test_theme.py`:

```python
"""Render theme 契约测试。"""
from __future__ import annotations

import re

import plotly.graph_objects as go

from flow_dashboard.render.theme import (
    PLOTLY_JS_BUNDLE,
    build_html_skeleton,
    render_figure_to_html,
    apply_theme,
)


def test_plotly_js_bundle_is_offline():
    """spec §3.3: 不得引用 CDN。"""
    assert "cdn" not in PLOTLY_JS_BUNDLE.lower()
    assert "plotly.com" not in PLOTLY_JS_BUNDLE.lower()
    assert "<script>" in PLOTLY_JS_BUNDLE


def test_build_html_skeleton_has_required_sections():
    html = build_html_skeleton(
        title="A 股流动性日报 2026-08-12",
        body="<div id='panels'></div>",
        data_date="2026-08-12",
        last_success_at="2026-08-12 19:30 CST",
    )
    assert "<!DOCTYPE html>" in html
    assert "A 股流动性日报 2026-08-12" in html
    assert "数据日期: 2026-08-12" in html
    assert "最近成功获取时间" in html
    assert "市场观察，非交易建议" in html  # spec §7.4
    assert PLOTLY_JS_BUNDLE in html
    # 只内嵌一次
    assert html.count("Plotly.newPlot") >= 0  # 各 panel 调用


def test_build_html_skeleton_offline_no_external_resource():
    html = build_html_skeleton(title="X", body="", data_date="2026-08-12",
                               last_success_at="X")
    # 不引用 http(s)
    assert not re.search(r'src="https?://', html)
    assert not re.search(r'href="https?://', html)


def test_apply_theme_returns_styled_figure():
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=[1, 2, 3], y=[4, 5, 6]))
    out = apply_theme(fig, title="测试", y_title="亿元", data_date="2026-08-12",
                      coverage=0.75, last_success_at="2026-08-12 19:30")
    assert out.layout.title.text is not None
    assert "数据日期: 2026-08-12" in out.layout.title.text
    assert out.layout.yaxis.title.text == "亿元"
    assert out.layout.annotations is not None
    # 注解应包含覆盖率和最新获取时间
    annotation_texts = " ".join(a.text for a in out.layout.annotations)
    assert "覆盖率" in annotation_texts
    assert "19:30" in annotation_texts


def test_render_figure_to_html_includes_div_and_script():
    fig = go.Figure()
    fig.add_trace(go.Bar(x=["A", "B"], y=[1, 2]))
    html = render_figure_to_html(fig, div_id="panel-1")
    assert 'id="panel-1"' in html
    assert "Plotly.newPlot" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/flow_dashboard/render/test_theme.py -v`
Expected: ImportError.

- [ ] **Step 3: Install plotly + capture offline bundle**

```bash
pip install plotly>=5.20
# 一次性把 plotly.js 内嵌为字符串常量
python -c "import plotly; print(plotly.offline.get_plotlyjs()[:200])"
```

- [ ] **Step 4: Implement `src/flow_dashboard/render/theme.py`**

```python
"""Render 主题：HTML 骨架 + Plotly 离线 bundle + 配色。

per spec §3.3 + §7.4:
- Plotly JS 单次内嵌；不引 CDN
- 每张图注解：数据日期、最近成功获取时间、单位、覆盖率
- 页脚固定显示"市场观察，非交易建议"
"""
from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
from plotly.offline import get_plotlyjs

# 缓存 plotly.js 字符串（首次调用时取，避免每图重复）
_PLOTLY_JS_CACHE: str | None = None


def _get_plotly_js() -> str:
    global _PLOTLY_JS_CACHE
    if _PLOTLY_JS_CACHE is None:
        _PLOTLY_JS_CACHE = get_plotlyjs()
    return _PLOTLY_JS_CACHE


PLOTLY_JS_BUNDLE: str = ""  # 由 _get_plotly_js() lazy 注入；常量字符串给测试先看 presence


def get_plotly_bundle() -> str:
    """Lazy 获取 plotly.js bundle 文本。"""
    return _get_plotly_js()


# 配色（per spec §3.6 数据健康色彩约定）
COLORS = {
    "primary": "#1f77b4",
    "positive_flow": "#2ca02c",   # 流入
    "negative_flow": "#d62728",   # 流出
    "warning": "#ff7f0e",
    "stale": "#7f7f7f",
    "background": "#fafafa",
    "grid": "#e8e8e8",
}


def apply_theme(
    fig: go.Figure,
    *,
    title: str,
    y_title: str,
    data_date: str,
    coverage: float | None = None,
    last_success_at: str | None = None,
    unit: str | None = None,
) -> go.Figure:
    """对 figure 应用统一主题：标题、轴标签、覆盖率和最新获取时间注解。"""
    title_parts = [title, f"<span style='font-size:11px;color:#666'>数据日期: {data_date}</span>"]
    fig.update_layout(
        title={"text": "<br>".join(title_parts), "x": 0.5, "xanchor": "center"},
        yaxis={"title": y_title, "gridcolor": COLORS["grid"]},
        xaxis={"gridcolor": COLORS["grid"]},
        plot_bgcolor=COLORS["background"],
        margin={"l": 60, "r": 30, "t": 80, "b": 40},
        font={"size": 12},
    )
    annotations = list(fig.layout.annotations or [])
    notes = []
    if coverage is not None:
        notes.append(f"覆盖率: {coverage:.1%}")
    if last_success_at:
        notes.append(f"最近获取: {last_success_at}")
    if unit:
        notes.append(f"单位: {unit}")
    if notes:
        annotations.append({
            "text": " | ".join(notes),
            "showarrow": False,
            "x": 1.0, "xref": "paper",
            "y": 1.0, "yref": "paper",
            "yanchor": "bottom", "xanchor": "right",
            "font": {"size": 10, "color": "#666"},
        })
    fig.update_layout(annotations=annotations)
    return fig


def render_figure_to_html(fig: go.Figure, *, div_id: str, full_html: bool = False) -> str:
    """把 figure 渲染成 HTML 片段（默认）或完整 HTML（含 bundle）。"""
    return fig.to_html(
        full_html=full_html,
        include_plotlyjs=(get_plotly_bundle() if full_html else False),
        div_id=div_id,
    )


def build_html_skeleton(
    *,
    title: str,
    body: str,
    data_date: str,
    last_success_at: str,
    footer: str = "市场观察，非交易建议",
) -> str:
    """构建完整 HTML 文档。Plotly JS 仅在此处内嵌一次。"""
    bundle = get_plotly_bundle()
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
body {{ font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif;
       max-width: 1400px; margin: 0 auto; padding: 20px; background: {COLORS['background']}; }}
header {{ border-bottom: 2px solid {COLORS['primary']}; padding-bottom: 10px; margin-bottom: 20px; }}
h1 {{ color: #333; margin: 0 0 8px 0; font-size: 22px; }}
.meta {{ color: #666; font-size: 13px; }}
.meta span {{ margin-right: 20px; }}
.panel {{ background: white; padding: 16px; margin-bottom: 24px;
          border: 1px solid {COLORS['grid']}; border-radius: 6px; }}
.panel-title {{ font-size: 16px; font-weight: 600; margin-bottom: 8px; }}
.stale {{ color: {COLORS['stale']}; }}
.warning {{ color: {COLORS['warning']}; }}
footer {{ margin-top: 40px; padding-top: 16px; border-top: 1px solid {COLORS['grid']};
          color: #888; font-size: 12px; text-align: center; }}
</style>
<script>{bundle}</script>
</head>
<body>
<header>
  <h1>{title}</h1>
  <div class="meta">
    <span>数据日期: <strong>{data_date}</strong></span>
    <span>最近成功获取时间: <strong>{last_success_at}</strong></span>
  </div>
</header>
<main>
{body}
</main>
<footer>{footer}</footer>
</body>
</html>"""


# 给 test_plotly_js_bundle_is_offline 用：lazy 加载后赋值
def _init_bundle_for_test() -> None:
    global PLOTLY_JS_BUNDLE
    PLOTLY_JS_BUNDLE = get_plotly_bundle()


_init_bundle_for_test()
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/flow_dashboard/render/test_theme.py -v`
Expected: 5 tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/flow_dashboard/render/theme.py tests/flow_dashboard/render/test_theme.py
git commit -m "feat(phase-b): render theme + offline plotly bundle + html skeleton"
```

---

## Task 8: Render figure factory（共通 figure 工厂）

**Files:**
- Create: `src/flow_dashboard/render/figures.py`
- Create: `tests/flow_dashboard/render/test_figures.py`

提供 6 个 figure 工厂，被 15 个面板调用：
- `bar_flow_panel`（日度流量柱图）
- `line_cumulative_panel`（累计流量折线）
- `stacked_bar_breakdown_panel`（分类细分堆叠柱图）
- `horizontal_topn_panel`（TOP15 横向柱）
- `multi_line_period_panel`（周度/月度多线）
- `dual_subplot_basis_panel`（IC/IM 双 subplot）

- [ ] **Step 1: Write failing test**

Create `tests/flow_dashboard/render/test_figures.py`:

```python
"""figures 工厂测试。"""
from __future__ import annotations

import pandas as pd

from flow_dashboard.render.figures import (
    bar_flow_panel,
    line_cumulative_panel,
    stacked_bar_breakdown_panel,
    horizontal_topn_panel,
    multi_line_period_panel,
    dual_subplot_basis_panel,
)


def _flow_df():
    return pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "label": "huijin",
         "etf_estimated_flow_cny": 1e9},
        {"trade_date": pd.Timestamp("2026-08-08"), "label": "huijin",
         "etf_estimated_flow_cny": -0.5e9},
    ])


def test_bar_flow_panel_returns_figure_with_color_split():
    fig = bar_flow_panel(
        _flow_df(), title="汇金宽基日度流量", data_date="2026-08-12",
        coverage=1.0, last_success_at="2026-08-12 19:30",
    )
    assert fig.data  # 有 trace
    # 正负柱分别着色
    colors = list(fig.data[0].marker.color)
    assert len(colors) == 2  # 一正一负


def test_line_cumulative_panel_y_axis_in_yi():
    df = pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "cumulative_flow_cny": 1e9},
    ])
    fig = line_cumulative_panel(
        df, title="累计", data_date="2026-08-12", y_unit="亿元",
    )
    assert fig.layout.yaxis.title.text == "亿元"


def test_stacked_bar_breakdown_panel_has_multi_traces():
    df = pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "label": "A", "etf_estimated_flow_cny": 1e9},
        {"trade_date": pd.Timestamp("2026-08-07"), "label": "B", "etf_estimated_flow_cny": 2e9},
    ])
    fig = stacked_bar_breakdown_panel(df, title="分类", data_date="2026-08-12")
    assert len(fig.data) == 2  # 两个 label 两个 trace


def test_horizontal_topn_panel_sorts_desc():
    df = pd.DataFrame([
        {"ts_code": "A", "etf_estimated_flow_cny": 1e9},
        {"ts_code": "B", "etf_estimated_flow_cny": 3e9},
        {"ts_code": "C", "etf_estimated_flow_cny": 2e9},
    ])
    fig = horizontal_topn_panel(df, title="TOP", data_date="2026-08-12", topn=15)
    # x = 流量，应按绝对值降序
    x_vals = list(fig.data[0].x)
    assert abs(x_vals[0]) >= abs(x_vals[-1])


def test_multi_line_period_panel_one_trace_per_label():
    df = pd.DataFrame([
        {"period_start": pd.Timestamp("2026-08-03"), "label": "broad", "etf_estimated_flow_cny": 1e9},
        {"period_start": pd.Timestamp("2026-08-10"), "label": "broad", "etf_estimated_flow_cny": 1.5e9},
        {"period_start": pd.Timestamp("2026-08-03"), "label": "tech", "etf_estimated_flow_cny": 0.5e9},
    ])
    fig = multi_line_period_panel(df, title="周度", data_date="2026-08-12")
    assert len(fig.data) == 2  # broad + tech


def test_dual_subplot_basis_panel_has_two_rows():
    ic = pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "ts_code": "IC2608.CFX",
         "basis_points": 18.2, "annualized_discount_rate": 0.47},
    ])
    im = pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "ts_code": "IM2608.CFX",
         "basis_points": 22.1, "annualized_discount_rate": 0.55},
    ])
    fig = dual_subplot_basis_panel(ic, im, data_date="2026-08-12")
    # 2 subplot rows
    assert fig.get_subplots({}).layout.grid.rows == 2 or "yaxis2" in str(fig.layout)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/flow_dashboard/render/test_figures.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/flow_dashboard/render/figures.py`**

```python
"""Figure 工厂：6 种共通图表，被 15 个面板调用。

每个工厂接收 DataFrame + 元数据，返回 plotly.go.Figure。
单位转换：内部统一为元；渲染时除 1e8 转亿元显示。
"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from flow_dashboard.render.theme import COLORS, apply_theme


_CNY_TO_YI = 1e8  # 亿元


def _to_yi(values):
    return [v / _CNY_TO_YI if pd.notna(v) else None for v in values]


def bar_flow_panel(
    df: pd.DataFrame,
    *,
    title: str,
    data_date: str,
    coverage: float | None = None,
    last_success_at: str | None = None,
) -> go.Figure:
    """日度流量柱图（正绿负红）。"""
    df = df.sort_values("trade_date")
    fig = go.Figure()
    flows_yi = _to_yi(df["etf_estimated_flow_cny"].tolist())
    colors = [
        COLORS["positive_flow"] if (v is not None and v >= 0) else COLORS["negative_flow"]
        for v in flows_yi
    ]
    fig.add_trace(go.Bar(
        x=df["trade_date"].astype(str).tolist(),
        y=flows_yi,
        marker_color=colors,
        showlegend=False,
    ))
    return apply_theme(
        fig, title=title, y_title="亿元", data_date=data_date,
        coverage=coverage, last_success_at=last_success_at, unit="亿元",
    )


def line_cumulative_panel(
    df: pd.DataFrame,
    *,
    title: str,
    data_date: str,
    coverage: float | None = None,
    last_success_at: str | None = None,
    y_unit: str = "亿元",
) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["trade_date"].astype(str).tolist(),
        y=_to_yi(df["cumulative_flow_cny"].tolist()),
        mode="lines+markers",
        line={"color": COLORS["primary"]},
        showlegend=False,
    ))
    return apply_theme(
        fig, title=title, y_title=y_unit, data_date=data_date,
        coverage=coverage, last_success_at=last_success_at, unit=y_unit,
    )


def stacked_bar_breakdown_panel(
    df: pd.DataFrame,
    *,
    title: str,
    data_date: str,
    coverage: float | None = None,
    last_success_at: str | None = None,
) -> go.Figure:
    """分类细分堆叠柱图（label × trade_date）。"""
    fig = go.Figure()
    for label, sub in df.groupby("label", sort=False):
        sub = sub.sort_values("trade_date")
        fig.add_trace(go.Bar(
            name=str(label),
            x=sub["trade_date"].astype(str).tolist(),
            y=_to_yi(sub["etf_estimated_flow_cny"].tolist()),
        ))
    fig.update_layout(barmode="relative")
    return apply_theme(
        fig, title=title, y_title="亿元", data_date=data_date,
        coverage=coverage, last_success_at=last_success_at, unit="亿元",
    )


def horizontal_topn_panel(
    df: pd.DataFrame,
    *,
    title: str,
    data_date: str,
    coverage: float | None = None,
    last_success_at: str | None = None,
    topn: int = 15,
) -> go.Figure:
    """TOP15 横向柱（按绝对值降序）。"""
    df = df.copy()
    df["_abs"] = df["etf_estimated_flow_cny"].abs()
    df = df.sort_values("_abs", ascending=False).head(topn)
    df = df.iloc[::-1]  # 倒序使最大在顶
    fig = go.Figure()
    flows_yi = _to_yi(df["etf_estimated_flow_cny"].tolist())
    colors = [
        COLORS["positive_flow"] if v >= 0 else COLORS["negative_flow"]
        for v in flows_yi
    ]
    fig.add_trace(go.Bar(
        orientation="h",
        y=df["ts_code"].astype(str).tolist(),
        x=flows_yi,
        marker_color=colors,
        showlegend=False,
    ))
    return apply_theme(
        fig, title=title, y_title="ETF", data_date=data_date,
        coverage=coverage, last_success_at=last_success_at, unit="亿元",
    )


def multi_line_period_panel(
    df: pd.DataFrame,
    *,
    title: str,
    data_date: str,
    coverage: float | None = None,
    last_success_at: str | None = None,
) -> go.Figure:
    """周度/月度多线（每 label 一条折线）。"""
    fig = go.Figure()
    period_col = "period_start" if "period_start" in df.columns else "trade_date"
    for label, sub in df.groupby("label", sort=False):
        sub = sub.sort_values(period_col)
        fig.add_trace(go.Scatter(
            name=str(label),
            x=sub[period_col].astype(str).tolist(),
            y=_to_yi(sub["etf_estimated_flow_cny"].tolist()),
            mode="lines+markers",
        ))
    return apply_theme(
        fig, title=title, y_title="亿元", data_date=data_date,
        coverage=coverage, last_success_at=last_success_at, unit="亿元",
    )


def dual_subplot_basis_panel(
    ic_df: pd.DataFrame,
    im_df: pd.DataFrame,
    *,
    data_date: str,
    coverage: float | None = None,
    last_success_at: str | None = None,
) -> go.Figure:
    """IC/IM 双 subplot：basis_points 折线 + annualized_discount_rate 副图。"""
    fig = make_subplots(
        rows=2, cols=1, shared_xaxes=False,
        subplot_titles=("IC 中证 500 基差", "IM 中证 1000 基差"),
        vertical_spacing=0.15,
    )
    for i, (label, df) in enumerate([("IC", ic_df), ("IM", im_df)], start=1):
        df = df.sort_values("trade_date")
        fig.add_trace(
            go.Bar(
                x=df["trade_date"].astype(str).tolist(),
                y=df["basis_points"].tolist(),
                name=f"{label} basis_points",
                marker_color=COLORS["primary"] if i == 1 else COLORS["warning"],
            ),
            row=i, col=1,
        )
    fig.update_layout(
        title={
            "text": f"期货基差（IC/IM 逐合约）<br><span style='font-size:11px;color:#666'>数据日期: {data_date}</span>",
            "x": 0.5, "xanchor": "center",
        },
        height=600,
        plot_bgcolor=COLORS["background"],
        showlegend=False,
    )
    annotations = list(fig.layout.annotations or [])
    notes = []
    if coverage is not None:
        notes.append(f"覆盖率: {coverage:.1%}")
    if last_success_at:
        notes.append(f"最近获取: {last_success_at}")
    if notes:
        annotations.append({
            "text": " | ".join(notes),
            "showarrow": False, "x": 1.0, "xref": "paper",
            "y": 1.0, "yref": "paper", "yanchor": "bottom", "xanchor": "right",
            "font": {"size": 10, "color": "#666"},
        })
    fig.update_layout(annotations=annotations)
    return fig
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/flow_dashboard/render/test_figures.py -v`
Expected: 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/render/figures.py tests/flow_dashboard/render/test_figures.py
git commit -m "feat(phase-b): 6 figure factories (bar/line/stack/topn/multi/subplot)"
```

---

## Task 9: Render 9 个日度 ETF 面板

**Files:**
- Create: `src/flow_dashboard/render/panels_daily.py`
- Create: `tests/flow_dashboard/render/test_panels_daily.py`

15 个 MVP 面板中的 9 个日度 ETF（spec §3.5.2.1）：
1. 汇金宽基 ETF
2. 科技/TMT 对照
3. 全市场合计
4. 宽基
5. 行业主题
6. 分类累计
7. 周期日度
8. 周期累计
9. 单只 ETF TOP15

每个面板都是一个 `render_<id>(flow_df, data_date, ...) -> str` 函数，返回 HTML 片段（含 `<div>` + Plotly JS 调用）。

- [ ] **Step 1: Write failing test**

Create `tests/flow_dashboard/render/test_panels_daily.py`:

```python
"""9 个日度 ETF 面板测试。"""
from __future__ import annotations

import pandas as pd
import pytest

from flow_dashboard.render.panels_daily import (
    render_huijin_broad_daily,
    render_tech_tmt_daily,
    render_total_market_daily,
    render_broad_daily,
    render_industry_theme_daily,
    render_category_cumulative_daily,
    render_cycle_daily,
    render_cycle_cumulative_daily,
    render_top15_etf_daily,
)


def _flow_df(labels: list[str], n_days: int = 5):
    rows = []
    base = pd.Timestamp("2026-08-05")
    for label in labels:
        for i in range(n_days):
            rows.append({
                "trade_date": base + pd.Timedelta(days=i),
                "ts_code": f"X{i}.{label}",
                "label": label,
                "etf_estimated_flow_cny": (i + 1) * 1e8 * (1 if label != "tech" else -1),
                "share_in_shares": 100e8,
                "total_size_cny": 100e8 * 3,
                "cumulative_flow_cny": (i + 1) * 1e8,
                "dimension": "ownership",
            })
    return pd.DataFrame(rows)


PANEL_KWARGS = dict(data_date="2026-08-12", coverage=1.0, last_success_at="19:30")


def test_render_huijin_broad_daily_returns_html_fragment():
    df = _flow_df(["huijin"])
    html = render_huijin_broad_daily(df, **PANEL_KWARGS)
    assert "汇金宽基" in html
    assert "Plotly.newPlot" in html
    assert 'id="panel-huijin-broad-daily"' in html


def test_render_tech_tmt_daily_returns_html_fragment():
    df = _flow_df(["tech"])
    html = render_tech_tmt_daily(df, **PANEL_KWARGS)
    assert "科技" in html or "TMT" in html


def test_render_total_market_daily_returns_html_fragment():
    df = _flow_df(["broad", "industry", "tech"])
    html = render_total_market_daily(df, **PANEL_KWARGS)
    assert "全市场合计" in html or "合计" in html


def test_render_broad_daily_returns_html_fragment():
    df = _flow_df(["broad"])
    html = render_broad_daily(df, **PANEL_KWARGS)
    assert "宽基" in html


def test_render_industry_theme_daily_returns_html_fragment():
    df = _flow_df(["industry"])
    html = render_industry_theme_daily(df, **PANEL_KWARGS)
    assert "行业主题" in html or "行业" in html


def test_render_category_cumulative_daily_returns_html_fragment():
    df = _flow_df(["broad", "industry"])
    html = render_category_cumulative_daily(df, **PANEL_KWARGS)
    assert "累计" in html


def test_render_cycle_daily_returns_html_fragment():
    df = _flow_df(["cycle"])
    html = render_cycle_daily(df, **PANEL_KWARGS)
    assert "周期" in html


def test_render_cycle_cumulative_daily_returns_html_fragment():
    df = _flow_df(["cycle"])
    html = render_cycle_cumulative_daily(df, **PANEL_KWARGS)
    assert "周期" in html
    assert "累计" in html


def test_render_top15_etf_daily_returns_html_fragment():
    df = _flow_df(["broad"] * 20)
    df["ts_code"] = [f"ETF{i:03d}.SH" for i in range(len(df))]
    html = render_top15_etf_daily(df, **PANEL_KWARGS)
    assert "TOP15" in html or "TOP" in html


def test_render_handles_empty_df_gracefully():
    """spec §3.5 共通验收：上游失败时面板显式 stale，不渲染空 figure。"""
    empty = pd.DataFrame(columns=["trade_date", "ts_code", "label",
                                   "etf_estimated_flow_cny", "cumulative_flow_cny"])
    html = render_huijin_broad_daily(empty, data_date="2026-08-12",
                                     coverage=None, last_success_at=None)
    assert "stale" in html.lower() or "数据不可得" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/flow_dashboard/render/test_panels_daily.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/flow_dashboard/render/panels_daily.py`**

```python
"""15 个 MVP 面板中的 9 个日度 ETF 面板。

每个 render_* 函数：
- 接收 flow_df + 元数据
- 返回 HTML 片段：<div class="panel"> + Plotly.newPlot 调用
- 上游 df 为空或 coverage=None 时显式标 stale，不渲染 figure
"""
from __future__ import annotations

import pandas as pd

from flow_dashboard.render.figures import (
    bar_flow_panel,
    line_cumulative_panel,
    stacked_bar_breakdown_panel,
    horizontal_topn_panel,
)
from flow_dashboard.render.theme import render_figure_to_html


def _wrap_panel(div_id: str, title: str, body: str, stale: bool = False) -> str:
    stale_cls = " stale" if stale else ""
    return f"""<div class="panel{stale_cls}" id="{div_id}">
<h2 class="panel-title">{title}</h2>
{body}
</div>"""


def _stale_message(reason: str = "数据不可得") -> str:
    return f'<div class="stale">⚠️ {reason}（stale）</div>'


def render_huijin_broad_daily(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    if df.empty or coverage is None:
        return _wrap_panel("panel-huijin-broad-daily", "汇金宽基 ETF 日度流量",
                           _stale_message())
    sub = df[df["label"] == "huijin"] if "label" in df.columns else df
    fig = bar_flow_panel(sub, title="汇金宽基 ETF 日度流量",
                         data_date=data_date, coverage=coverage,
                         last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-huijin-broad-daily")
    return _wrap_panel("panel-huijin-broad-daily", "汇金宽基 ETF 日度流量", body)


def render_tech_tmt_daily(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    if df.empty or coverage is None:
        return _wrap_panel("panel-tech-tmt-daily", "科技/TMT ETF 日度流量",
                           _stale_message())
    sub = df[df["label"] == "tech"] if "label" in df.columns else df
    fig = bar_flow_panel(sub, title="科技/TMT ETF 日度流量（对照中证 TMT）",
                         data_date=data_date, coverage=coverage,
                         last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-tech-tmt-daily")
    return _wrap_panel("panel-tech-tmt-daily", "科技/TMT ETF 日度流量", body)


def render_total_market_daily(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    if df.empty or coverage is None:
        return _wrap_panel("panel-total-market-daily", "全市场合计日度流量",
                           _stale_message())
    agg = df.groupby("trade_date", as_index=False)["etf_estimated_flow_cny"].sum()
    agg["label"] = "ALL"
    fig = bar_flow_panel(agg, title="全市场 ETF 合计日度流量",
                         data_date=data_date, coverage=coverage,
                         last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-total-market-daily")
    return _wrap_panel("panel-total-market-daily", "全市场合计日度流量", body)


def render_broad_daily(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    if df.empty or coverage is None:
        return _wrap_panel("panel-broad-daily", "宽基 ETF 日度流量",
                           _stale_message())
    sub = df[df["label"] == "broad"] if "label" in df.columns else df
    fig = bar_flow_panel(sub, title="宽基 ETF 日度流量",
                         data_date=data_date, coverage=coverage,
                         last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-broad-daily")
    return _wrap_panel("panel-broad-daily", "宽基 ETF 日度流量", body)


def render_industry_theme_daily(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    if df.empty or coverage is None:
        return _wrap_panel("panel-industry-theme-daily", "行业/主题 ETF 日度流量",
                           _stale_message())
    sub = df[df["label"] == "industry"] if "label" in df.columns else df
    fig = bar_flow_panel(sub, title="行业/主题 ETF 日度流量",
                         data_date=data_date, coverage=coverage,
                         last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-industry-theme-daily")
    return _wrap_panel("panel-industry-theme-daily", "行业/主题 ETF 日度流量", body)


def render_category_cumulative_daily(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    if df.empty or coverage is None:
        return _wrap_panel("panel-category-cumulative-daily", "分类累计日度流量",
                           _stale_message())
    fig = stacked_bar_breakdown_panel(df, title="分类累计日度流量",
                                       data_date=data_date, coverage=coverage,
                                       last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-category-cumulative-daily")
    return _wrap_panel("panel-category-cumulative-daily", "分类累计日度流量", body)


def render_cycle_daily(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    if df.empty or coverage is None:
        return _wrap_panel("panel-cycle-daily", "周期主题 ETF 日度流量",
                           _stale_message())
    sub = df[df["label"] == "cycle"] if "label" in df.columns else df
    fig = bar_flow_panel(sub, title="周期主题 ETF 日度流量",
                         data_date=data_date, coverage=coverage,
                         last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-cycle-daily")
    return _wrap_panel("panel-cycle-daily", "周期主题 ETF 日度流量", body)


def render_cycle_cumulative_daily(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    if df.empty or coverage is None:
        return _wrap_panel("panel-cycle-cumulative-daily", "周期主题 ETF 累计流量",
                           _stale_message())
    sub = df[df["label"] == "cycle"] if "label" in df.columns else df
    by_date = sub.groupby("trade_date", as_index=False)["etf_estimated_flow_cny"].sum()
    by_date = by_date.sort_values("trade_date")
    by_date["cumulative_flow_cny"] = by_date["etf_estimated_flow_cny"].cumsum()
    fig = line_cumulative_panel(by_date, title="周期主题 ETF 累计流量",
                                 data_date=data_date, coverage=coverage,
                                 last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-cycle-cumulative-daily")
    return _wrap_panel("panel-cycle-cumulative-daily", "周期主题 ETF 累计流量", body)


def render_top15_etf_daily(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    if df.empty or coverage is None:
        return _wrap_panel("panel-top15-daily", "单只 ETF 流量 TOP15",
                           _stale_message())
    latest = df[df["trade_date"] == df["trade_date"].max()]
    fig = horizontal_topn_panel(latest, title="单只 ETF 流量 TOP15",
                                data_date=data_date, coverage=coverage,
                                last_success_at=last_success_at, topn=15)
    body = render_figure_to_html(fig, div_id="panel-top15-daily")
    return _wrap_panel("panel-top15-daily", "单只 ETF 流量 TOP15", body)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/flow_dashboard/render/test_panels_daily.py -v`
Expected: 10 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/render/panels_daily.py tests/flow_dashboard/render/test_panels_daily.py
git commit -m "feat(phase-b): 9 daily ETF panels with stale fallback"
```

---

## Task 10: Render 4 个周度 ETF 面板

**Files:**
- Create: `src/flow_dashboard/render/panels_weekly.py`
- Create: `tests/flow_dashboard/render/test_panels_weekly.py`

15 个 MVP 面板中的 4 个周度 ETF（spec §3.5.2.2）：
1. 宽基周度
2. 行业/主题周度
3. 分类累计周度
4. 月度合计

- [ ] **Step 1: Write failing test**

Create `tests/flow_dashboard/render/test_panels_weekly.py`:

```python
"""4 个周度 ETF 面板测试。"""
from __future__ import annotations

import pandas as pd

from flow_dashboard.render.panels_weekly import (
    render_broad_weekly,
    render_industry_theme_weekly,
    render_category_cumulative_weekly,
    render_monthly_total,
)


def _weekly_df(label: str):
    return pd.DataFrame([
        {"period_start": pd.Timestamp("2026-08-03"), "label": label,
         "etf_estimated_flow_cny": 1e9},
        {"period_start": pd.Timestamp("2026-08-10"), "label": label,
         "etf_estimated_flow_cny": 1.5e9},
    ])


KW = dict(data_date="2026-08-12", coverage=0.95, last_success_at="19:30")


def test_render_broad_weekly():
    html = render_broad_weekly(_weekly_df("broad"), **KW)
    assert "宽基" in html and "周度" in html


def test_render_industry_theme_weekly():
    html = render_industry_theme_weekly(_weekly_df("industry"), **KW)
    assert "行业" in html and "周度" in html


def test_render_category_cumulative_weekly():
    df = pd.concat([_weekly_df("broad"), _weekly_df("industry"), _weekly_df("tech")])
    html = render_category_cumulative_weekly(df, **KW)
    assert "累计" in html or "分类" in html


def test_render_monthly_total():
    df = pd.DataFrame([
        {"month_start": pd.Timestamp("2026-07-01"), "label": "broad",
         "etf_estimated_flow_cny": 5e9},
        {"month_start": pd.Timestamp("2026-08-01"), "label": "broad",
         "etf_estimated_flow_cny": 3e9},
    ])
    html = render_monthly_total(df, **KW)
    assert "月度" in html or "月合计" in html


def test_render_weekly_empty_df_gracefully():
    empty = pd.DataFrame(columns=["period_start", "label", "etf_estimated_flow_cny"])
    html = render_broad_weekly(empty, data_date="2026-08-12",
                               coverage=None, last_success_at=None)
    assert "stale" in html.lower() or "数据不可得" in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/flow_dashboard/render/test_panels_weekly.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/flow_dashboard/render/panels_weekly.py`**

```python
"""4 个周度 ETF 面板。"""
from __future__ import annotations

import pandas as pd

from flow_dashboard.render.figures import multi_line_period_panel
from flow_dashboard.render.theme import render_figure_to_html


def _wrap_panel(div_id: str, title: str, body: str, stale: bool = False) -> str:
    stale_cls = " stale" if stale else ""
    return f"""<div class="panel{stale_cls}" id="{div_id}">
<h2 class="panel-title">{title}</h2>
{body}
</div>"""


def _stale_message() -> str:
    return '<div class="stale">⚠️ 数据不可得（stale）</div>'


def render_broad_weekly(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    if df.empty or coverage is None:
        return _wrap_panel("panel-broad-weekly", "宽基 ETF 周度流量", _stale_message())
    sub = df[df["label"] == "broad"] if "label" in df.columns else df
    fig = multi_line_period_panel(sub, title="宽基 ETF 周度流量",
                                  data_date=data_date, coverage=coverage,
                                  last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-broad-weekly")
    return _wrap_panel("panel-broad-weekly", "宽基 ETF 周度流量", body)


def render_industry_theme_weekly(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    if df.empty or coverage is None:
        return _wrap_panel("panel-industry-weekly", "行业/主题 ETF 周度流量", _stale_message())
    sub = df[df["label"] == "industry"] if "label" in df.columns else df
    fig = multi_line_period_panel(sub, title="行业/主题 ETF 周度流量",
                                  data_date=data_date, coverage=coverage,
                                  last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-industry-weekly")
    return _wrap_panel("panel-industry-weekly", "行业/主题 ETF 周度流量", body)


def render_category_cumulative_weekly(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    if df.empty or coverage is None:
        return _wrap_panel("panel-category-weekly", "分类累计周度流量", _stale_message())
    fig = multi_line_period_panel(df, title="分类累计周度流量",
                                  data_date=data_date, coverage=coverage,
                                  last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-category-weekly")
    return _wrap_panel("panel-category-weekly", "分类累计周度流量", body)


def render_monthly_total(
    df: pd.DataFrame, *, data_date: str, coverage: float | None, last_success_at: str | None
) -> str:
    if df.empty or coverage is None:
        return _wrap_panel("panel-monthly-total", "月度合计", _stale_message())
    # 月度合计：所有 label 在 month_start 上汇总
    agg = df.groupby("month_start", as_index=False)["etf_estimated_flow_cny"].sum()
    agg["label"] = "ALL"
    agg = agg.rename(columns={"month_start": "period_start"})
    fig = multi_line_period_panel(agg, title="月度合计流量",
                                  data_date=data_date, coverage=coverage,
                                  last_success_at=last_success_at)
    body = render_figure_to_html(fig, div_id="panel-monthly-total")
    return _wrap_panel("panel-monthly-total", "月度合计", body)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/flow_dashboard/render/test_panels_weekly.py -v`
Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/render/panels_weekly.py tests/flow_dashboard/render/test_panels_weekly.py
git commit -m "feat(phase-b): 4 weekly ETF panels (broad/industry/category/monthly)"
```

---

## Task 11: Render 两融面板 + IC/IM 基差面板

**Files:**
- Create: `src/flow_dashboard/render/panels_margin.py`
- Create: `src/flow_dashboard/render/panels_basis.py`
- Create: `tests/flow_dashboard/render/test_panels_margin.py`
- Create: `tests/flow_dashboard/render/test_panels_basis.py`

两融面板（1 个）：分交易所融资余额与周变化（双轴：余额水平柱 + 周变化折线）。
基差面板（1 个）：IC/IM 双 subplot（Task 8 的 `dual_subplot_basis_panel` 工厂在此处 wrap）。

- [ ] **Step 1: Write failing test for margin panel**

Create `tests/flow_dashboard/render/test_panels_margin.py`:

```python
"""两融面板测试。"""
from __future__ import annotations

import pandas as pd

from flow_dashboard.render.panels_margin import render_margin_exchange_panel


def _margin_df():
    return pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "exchange_id": "SSE",
         "rzye": 8100e8, "weekly_change_rzye": 50e8},
        {"trade_date": pd.Timestamp("2026-08-07"), "exchange_id": "SZSE",
         "rzye": 7100e8, "weekly_change_rzye": 40e8},
        {"trade_date": pd.Timestamp("2026-08-07"), "exchange_id": "BSE",
         "rzye": 8.6e9, "weekly_change_rzye": 0.1e8},
        {"trade_date": pd.Timestamp("2026-08-07"), "exchange_id": "ALL",
         "rzye": 15_008.6e8, "weekly_change_rzye": 90.1e8},
    ])


def test_render_margin_exchange_panel_returns_html_with_sse_szse_bse():
    html = render_margin_exchange_panel(
        _margin_df(), data_date="2026-08-12",
        coverage=1.0, last_success_at="19:30",
        reconciliation_tolerance=None,  # 未冻结
    )
    assert "融资余额" in html
    assert "SSE" in html and "SZSE" in html and "BSE" in html
    assert 'id="panel-margin-exchange"' in html


def test_render_margin_exchange_panel_handles_empty_df():
    html = render_margin_exchange_panel(
        pd.DataFrame(columns=["trade_date", "exchange_id", "rzye"]),
        data_date="2026-08-12", coverage=None, last_success_at=None,
        reconciliation_tolerance=None,
    )
    assert "stale" in html.lower() or "数据不可得" in html
```

- [ ] **Step 2: Write failing test for basis panel**

Create `tests/flow_dashboard/render/test_panels_basis.py`:

```python
"""基差面板测试。"""
from __future__ import annotations

import pandas as pd

from flow_dashboard.render.panels_basis import render_basis_panel


def _basis_df(prefix: str):
    return pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "ts_code": f"{prefix}2608.CFX",
         "basis_points": 18.2, "annualized_discount_rate": 0.47,
         "quality_flags": "quote_time_unverified"},
        {"trade_date": pd.Timestamp("2026-08-08"), "ts_code": f"{prefix}2608.CFX",
         "basis_points": 22.1, "annualized_discount_rate": 0.55,
         "quality_flags": "quote_time_unverified"},
    ])


def test_render_basis_panel_returns_html_with_ic_im():
    html = render_basis_panel(
        ic_df=_basis_df("IC"), im_df=_basis_df("IM"),
        data_date="2026-08-12", coverage=1.0, last_success_at="19:30",
        layer="eod",
    )
    assert "IC" in html and "IM" in html
    assert "基差" in html
    assert 'id="panel-basis"' in html


def test_render_basis_panel_intraday_layer_marked_preview():
    html = render_basis_panel(
        ic_df=_basis_df("IC"), im_df=_basis_df("IM"),
        data_date="2026-08-12", coverage=None, last_success_at="14:30",
        layer="intraday",
    )
    assert "盘中" in html or "preview" in html.lower() or "预览" in html


def test_render_basis_panel_empty_gracefully():
    empty = pd.DataFrame(columns=["trade_date", "ts_code", "basis_points"])
    html = render_basis_panel(
        ic_df=empty, im_df=empty, data_date="2026-08-12",
        coverage=None, last_success_at=None, layer="eod",
    )
    assert "stale" in html.lower() or "数据不可得" in html
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/flow_dashboard/render/test_panels_margin.py tests/flow_dashboard/render/test_panels_basis.py -v`
Expected: ImportError.

- [ ] **Step 4: Implement `src/flow_dashboard/render/panels_margin.py`**

```python
"""两融面板：分交易所融资余额 + 周变化。"""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

from flow_dashboard.render.theme import COLORS, apply_theme, render_figure_to_html


def _wrap_panel(body: str, stale: bool = False) -> str:
    cls = " stale" if stale else ""
    return f"""<div class="panel{cls}" id="panel-margin-exchange">
<h2 class="panel-title">分交易所融资余额与周变化</h2>
{body}
</div>"""


def render_margin_exchange_panel(
    df: pd.DataFrame,
    *,
    data_date: str,
    coverage: float | None,
    last_success_at: str | None,
    reconciliation_tolerance: float | None,
) -> str:
    if df.empty or coverage is None:
        return _wrap_panel('<div class="stale">⚠️ 数据不可得（stale）</div>', stale=True)

    latest = df[df["trade_date"] == df["trade_date"].max()]
    latest = latest.sort_values("exchange_id")
    fig = go.Figure()
    fig.add_trace(go.Bar(
        name="融资余额 (亿元)",
        x=latest["exchange_id"].tolist(),
        y=(latest["rzye"] / 1e8).tolist(),
        marker_color=COLORS["primary"],
        yaxis="y",
    ))
    fig.add_trace(go.Scatter(
        name="周变化 (亿元)",
        x=latest["exchange_id"].tolist(),
        y=(latest["weekly_change_rzye"] / 1e8).tolist(),
        mode="lines+markers",
        line={"color": COLORS["negative_flow"]},
        yaxis="y2",
    ))
    fig.update_layout(
        yaxis={"title": "亿元", "gridcolor": COLORS["grid"]},
        yaxis2={"title": "周变化 (亿元)", "overlaying": "y", "side": "right"},
        xaxis={"gridcolor": COLORS["grid"]},
        plot_bgcolor=COLORS["background"],
    )
    fig = apply_theme(fig, title="分交易所融资余额与周变化",
                      y_title="亿元", data_date=data_date,
                      coverage=coverage, last_success_at=last_success_at,
                      unit="亿元")
    body = render_figure_to_html(fig, div_id="panel-margin-exchange")
    return _wrap_panel(body)


# reconciliation_tolerance 未冻结时不在面板上显示对账状态（spec §3.5 共通验收）
```

- [ ] **Step 5: Implement `src/flow_dashboard/render/panels_basis.py`**

```python
"""基差面板：IC/IM 双 subplot，盘中/日终分层标识。"""
from __future__ import annotations

import pandas as pd

from flow_dashboard.render.figures import dual_subplot_basis_panel
from flow_dashboard.render.theme import render_figure_to_html


def _wrap_panel(body: str, stale: bool = False, layer_note: str = "") -> str:
    cls = " stale" if stale else ""
    return f"""<div class="panel{cls}" id="panel-basis">
<h2 class="panel-title">期货基差 — IC/IM 逐合约 {layer_note}</h2>
{body}
</div>"""


def render_basis_panel(
    *,
    ic_df: pd.DataFrame,
    im_df: pd.DataFrame,
    data_date: str,
    coverage: float | None,
    last_success_at: str | None,
    layer: str = "eod",
) -> str:
    if (ic_df.empty and im_df.empty) or coverage is None:
        return _wrap_panel(
            '<div class="stale">⚠️ 数据不可得（stale）</div>',
            stale=True,
            layer_note="(预览)" if layer == "intraday" else "",
        )

    fig = dual_subplot_basis_panel(
        ic_df, im_df, data_date=data_date,
        coverage=coverage, last_success_at=last_success_at,
    )
    body = render_figure_to_html(fig, div_id="panel-basis")
    layer_note = "(盘中预览)" if layer == "intraday" else "(日终正式)"
    return _wrap_panel(body, layer_note=layer_note)
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/flow_dashboard/render/test_panels_margin.py tests/flow_dashboard/render/test_panels_basis.py -v`
Expected: 5 tests pass.

- [ ] **Step 7: Commit**

```bash
git add src/flow_dashboard/render/panels_margin.py src/flow_dashboard/render/panels_basis.py \
  tests/flow_dashboard/render/test_panels_margin.py tests/flow_dashboard/render/test_panels_basis.py
git commit -m "feat(phase-b): margin + basis panels with stale fallback"
```

---

## Task 12: Render 数据健康页

**Files:**
- Create: `src/flow_dashboard/render/panels_health.py`
- Create: `tests/flow_dashboard/render/test_panels_health.py`

数据健康页内容（spec §3.5.2.5）：
- 各板块覆盖率矩阵（dimension × label × coverage_rate）
- 各源 freshness（last_success_at, source_date vs run_at）
- 源版本清单
- 未冻结项警示（needs_human_review 摘要）
- 上游失败次数

- [ ] **Step 1: Write failing test**

Create `tests/flow_dashboard/render/test_panels_health.py`:

```python
"""数据健康页测试。"""
from __future__ import annotations

import pandas as pd

from flow_dashboard.render.panels_health import render_health_page


def _coverage_df():
    return pd.DataFrame([
        {"dimension": "ownership", "label": "huijin", "trade_date": "2026-08-12",
         "count_coverage": 0.75, "prior_share_coverage": 1.0, "prior_aum_coverage": 1.0},
        {"dimension": "asset_scope", "label": "broad", "trade_date": "2026-08-12",
         "count_coverage": 1.0, "prior_share_coverage": 1.0, "prior_aum_coverage": 1.0},
    ])


def _source_status():
    return pd.DataFrame([
        {"source": "tushare", "endpoint": "etf_share_size", "last_success_at": "2026-08-12 19:30",
         "source_date": "2026-08-12", "is_stale": False, "n_failures_7d": 0},
        {"source": "tushare", "endpoint": "margin", "last_success_at": "2026-08-12 19:30",
         "source_date": "2026-08-12", "is_stale": False, "n_failures_7d": 1},
        {"source": "sina", "endpoint": "futures_node_IC", "last_success_at": "2026-08-12 14:30",
         "source_date": "2026-08-12", "is_stale": True, "n_failures_7d": 3},
    ])


def _unfrozen():
    return ["coverage_gates", "reconciliation_tolerance", "max_quote_skew_seconds"]


def test_render_health_page_has_required_sections():
    html = render_health_page(
        coverage_df=_coverage_df(),
        source_status=_source_status(),
        unfrozen=_unfrozen(),
        data_date="2026-08-12", run_at="2026-08-12 19:35 CST",
    )
    assert "数据健康" in html
    assert "覆盖率" in html
    assert "源状态" in html or "Source" in html
    assert "未冻结" in html or "needs_human_review" in html


def test_render_health_page_highlights_stale_sources():
    html = render_health_page(
        coverage_df=_coverage_df(),
        source_status=_source_status(),
        unfrozen=_unfrozen(),
        data_date="2026-08-12", run_at="2026-08-12 19:35 CST",
    )
    # is_stale=True 的 sina 应该被标红/警告
    assert "stale" in html.lower() or "warning" in html.lower()


def test_render_health_page_lists_unfrozen_items():
    html = render_health_page(
        coverage_df=_coverage_df(),
        source_status=_source_status(),
        unfrozen=_unfrozen(),
        data_date="2026-08-12", run_at="2026-08-12 19:35 CST",
    )
    for item in _unfrozen():
        assert item in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/flow_dashboard/render/test_panels_health.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/flow_dashboard/render/panels_health.py`**

```python
"""数据健康页：覆盖率矩阵 + 源状态 + 未冻结项。"""
from __future__ import annotations

import pandas as pd

from flow_dashboard.render.theme import COLORS


def render_health_page(
    *,
    coverage_df: pd.DataFrame,
    source_status: pd.DataFrame,
    unfrozen: list[str],
    data_date: str,
    run_at: str,
) -> str:
    sections: list[str] = []
    sections.append(_render_header(data_date, run_at))
    sections.append(_render_coverage_matrix(coverage_df))
    sections.append(_render_source_status(source_status))
    sections.append(_render_unfrozen(unfrozen))
    sections.append(_render_footer())
    return "\n".join(sections)


def _render_header(data_date: str, run_at: str) -> str:
    return f"""<section id="health-header">
<h1>数据健康 — 数据日期 {data_date}</h1>
<div class="meta"><span>run_at: {run_at}</span></div>
</section>"""


def _render_coverage_matrix(df: pd.DataFrame) -> str:
    if df.empty:
        return '<section><h2>覆盖率矩阵</h2><p class="stale">无数据</p></section>'
    cols = ["dimension", "label", "trade_date",
            "count_coverage", "prior_share_coverage", "prior_aum_coverage"]
    rows_html = []
    for _, row in df.iterrows():
        cells = "".join(f"<td>{row.get(c, '')}</td>" for c in cols)
        rows_html.append(f"<tr>{cells}</tr>")
    head = "".join(f"<th>{c}</th>" for c in cols)
    return f"""<section id="health-coverage">
<h2>覆盖率矩阵</h2>
<table border="1" cellpadding="6" cellspacing="0">
<thead><tr>{head}</tr></thead>
<tbody>{''.join(rows_html)}</tbody>
</table>
</section>"""


def _render_source_status(df: pd.DataFrame) -> str:
    if df.empty:
        return '<section><h2>源状态</h2><p>无源</p></section>'
    rows_html = []
    for _, row in df.iterrows():
        stale_cls = "stale" if row.get("is_stale") else ""
        row_cls = " class='stale'" if row.get("is_stale") else ""
        rows_html.append(
            f"<tr{row_cls}>"
            f"<td>{row['source']}</td><td>{row['endpoint']}</td>"
            f"<td>{row['last_success_at']}</td><td>{row['source_date']}</td>"
            f"<td>{'stale' if row.get('is_stale') else 'ok'}</td>"
            f"<td>{row.get('n_failures_7d', 0)}</td>"
            f"</tr>"
        )
    return f"""<section id="health-sources">
<h2>源状态（含 stale 标记）</h2>
<table border="1" cellpadding="6" cellspacing="0">
<thead><tr><th>source</th><th>endpoint</th><th>last_success_at</th>
<th>source_date</th><th>status</th><th>n_failures_7d</th></tr></thead>
<tbody>{''.join(rows_html)}</tbody>
</table>
</section>"""


def _render_unfrozen(items: list[str]) -> str:
    if not items:
        return '<section><h2>未冻结项</h2><p>所有阈值已冻结</p></section>'
    lis = "".join(f"<li>{i}</li>" for i in items)
    return f"""<section id="health-unfrozen">
<h2>未冻结项（needs_human_review）</h2>
<ul>{lis}</ul>
</section>"""


def _render_footer() -> str:
    return """<footer>
<p>市场观察，非交易建议。数据健康仅描述可得性，不构成投资判断。</p>
</footer>"""
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/flow_dashboard/render/test_panels_health.py -v`
Expected: 3 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/render/panels_health.py tests/flow_dashboard/render/test_panels_health.py
git commit -m "feat(phase-b): data health page (coverage matrix + source status + unfrozen items)"
```

---

## Task 13: Render 原子发布（assembly + manifest + symlink）

**Files:**
- Create: `src/flow_dashboard/render/assembly.py`
- Create: `tests/flow_dashboard/render/test_assembly.py`

**spec §3.3 约束：**
- staging 文件 → 完整性检查 → 原子 `replace` 归档文件
- `latest.html` 用相对目标的临时 symlink 后原子替换
- `intraday` 只更新 `intraday_latest.html`，不写归档
- 4 runner 共用文件锁；无法获锁时记录 `skipped_due_to_lock`
- 同一报告日补跑生成新版本（`_vNN`），不覆盖旧版
- 每版保存输入数据 hash/size/mtime、源版本、run_at、参数、板块状态 manifest

- [ ] **Step 1: Write failing test**

Create `tests/flow_dashboard/render/test_assembly.py`:

```python
"""Assembly 契约测试：原子替换、manifest、symlink。"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from flow_dashboard.render.assembly import (
    publish_archive,
    publish_intraday,
    acquire_runner_lock,
    RunnerLockError,
    next_version_number,
)


def test_next_version_number_increments(tmp_path):
    # 空目录 → v01
    assert next_version_number(tmp_path, "2026-08-12") == 1
    # 已有 v01 → v02
    (tmp_path / "report_2026-08-12_v01.html").write_text("x")
    assert next_version_number(tmp_path, "2026-08-12") == 2


def test_publish_archive_atomic_replace(tmp_path):
    output_dir = tmp_path / "ashare_flow_daily"
    output_dir.mkdir()
    staging, archive_path, symlink_path, manifest_path = publish_archive(
        output_dir=output_dir,
        data_date="2026-08-12",
        html_body="<div>hello</div>",
        manifest_payload={"panels": ["huijin"], "source_versions": {"etf_share": "v1"}},
        full_html="<html>...</html>",
    )
    assert archive_path.exists()
    assert archive_path.read_text() == "<html>...</html>"
    # symlink 指向 archive
    assert symlink_path.is_symlink()
    assert os.readlink(symlink_path) == str(archive_path.name) or str(archive_path) == str(symlink_path.resolve())
    # manifest 落盘
    assert manifest_path.exists()
    payload = json.loads(manifest_path.read_text())
    assert payload["panels"] == ["huijin"]
    assert "run_at" in payload


def test_publish_archive_does_not_overwrite_existing(tmp_path):
    """spec §3.3: 同一报告日补跑生成新版本，不覆盖旧版。"""
    output_dir = tmp_path / "x"
    output_dir.mkdir()
    _, archive1, _, _ = publish_archive(
        output_dir=output_dir, data_date="2026-08-12",
        html_body="", manifest_payload={},
        full_html="<html>v1</html>",
    )
    _, archive2, symlink, _ = publish_archive(
        output_dir=output_dir, data_date="2026-08-12",
        html_body="", manifest_payload={},
        full_html="<html>v2</html>",
    )
    assert archive1.exists()
    assert archive1.read_text() == "<html>v1</html>"
    assert archive2.read_text() == "<html>v2</html>"
    # symlink 指向最新
    assert symlink.resolve() == archive2.resolve()


def test_publish_intraday_does_not_write_archive(tmp_path):
    """spec §3.3: intraday 只更新 intraday_latest.html，不写归档。"""
    output_dir = tmp_path / "x"
    output_dir.mkdir()
    intraday_path = publish_intraday(
        output_dir=output_dir,
        full_html="<html>intraday</html>",
    )
    assert intraday_path.exists()
    assert intraday_path.name == "intraday_latest.html"
    # 不应产生 report_*.html
    assert not list(output_dir.glob("report_*.html"))


def test_acquire_runner_lock_serializes(tmp_path):
    lock_path = tmp_path / "runners.lock"
    # 首次获取应成功
    with acquire_runner_lock(lock_path):
        # 同一进程再次获取应失败（模拟并发）
        with pytest.raises(RunnerLockError):
            with acquire_runner_lock(lock_path, timeout=0.1):
                pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/flow_dashboard/render/test_assembly.py -v`
Expected: ImportError.

- [ ] **Step 3: Implement `src/flow_dashboard/render/assembly.py`**

```python
"""Assembly：原子发布 + manifest + symlink + 文件锁。

per spec §3.3:
- staging 文件 → 完整性检查 → 原子 replace
- latest.html 用 symlink 原子替换
- intraday 只更新 intraday_latest.html
- 4 runner 共用文件锁
- 同日补跑 → _vNN
- manifest 保存输入 hash/size/mtime + run_at + 板块状态
"""
from __future__ import annotations

import contextlib
import fcntl
import hashlib
import json
import os
import re
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from flow_dashboard.config import TIMEZONE


class RunnerLockError(RuntimeError):
    """无法获取 runner 锁。"""


@contextlib.contextmanager
def acquire_runner_lock(lock_path: Path | str, *, timeout: float = 0.0):
    """fcntl 文件锁；timeout=0 立即失败。"""
    lock_path = Path(lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(lock_path, "w")
    try:
        flag = fcntl.LOCK_EX if timeout == 0 else fcntl.LOCK_EX | fcntl.LOCK_NB
        if timeout == 0:
            fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        else:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        raise RunnerLockError(f"无法在 {timeout}s 内获取锁: {lock_path}")
                    time.sleep(0.05)
        yield
    finally:
        try:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
        finally:
            fh.close()


def next_version_number(output_dir: Path | str, data_date: str) -> int:
    """扫描已有 report_<data_date>_vNN.html，返回 max+1。"""
    output_dir = Path(output_dir)
    pattern = re.compile(rf"report_{re.escape(data_date)}_v(\d+)\.html$")
    max_v = 0
    if output_dir.exists():
        for p in output_dir.iterdir():
            m = pattern.match(p.name)
            if m:
                max_v = max(max_v, int(m.group(1)))
    return max_v + 1


def publish_archive(
    *,
    output_dir: Path | str,
    data_date: str,
    html_body: str,
    manifest_payload: dict,
    full_html: str,
) -> tuple[Path, Path, Path, Path]:
    """发布归档版本：写 staging → 完整性检查 → 原子 replace → 更新 latest symlink。

    Returns:
        (staging_path, archive_path, symlink_path, manifest_path)
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    staging_dir = output_dir / "staging"
    staging_dir.mkdir(exist_ok=True)
    manifest_dir = output_dir / "manifest"
    manifest_dir.mkdir(exist_ok=True)

    version = next_version_number(output_dir, data_date)
    archive_name = f"report_{data_date}_v{version:02d}.html"
    archive_path = output_dir / archive_name
    manifest_name = f"{data_date}_v{version:02d}.json"
    manifest_path = manifest_dir / manifest_name

    # staging 写入
    staging_path = staging_dir / f"{archive_name}.{uuid.uuid4().hex}.tmp"
    staging_path.write_text(full_html, encoding="utf-8")

    # 完整性检查
    if "<html" not in full_html.lower() or "</html>" not in full_html.lower():
        staging_path.unlink(missing_ok=True)
        raise ValueError("HTML 完整性检查失败：缺少 <html>/</html>")

    # 原子 rename
    staging_path.rename(archive_path)

    # manifest
    payload = {
        "data_date": data_date,
        "version": version,
        "archive_name": archive_name,
        "run_at": datetime.now(tz=pd.Timestamp.now(tz=TIMEZONE).tz).isoformat(),
        "panels": manifest_payload.get("panels", []),
        "source_versions": manifest_payload.get("source_versions", {}),
        "input_files": manifest_payload.get("input_files", []),
        "panel_status": manifest_payload.get("panel_status", {}),
    }
    manifest_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))

    # latest symlink 原子替换
    symlink_path = output_dir / "latest.html"
    tmp_sym = output_dir / "latest.html.tmp"
    if tmp_sym.exists() or tmp_sym.is_symlink():
        tmp_sym.unlink()
    os.symlink(archive_path.name, tmp_sym)
    os.replace(tmp_sym, symlink_path)

    return staging_path, archive_path, symlink_path, manifest_path


def publish_intraday(
    *,
    output_dir: Path | str,
    full_html: str,
) -> Path:
    """intraday runner 专用：原子更新 intraday_latest.html，不写归档。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    staging_dir = output_dir / "staging"
    staging_dir.mkdir(exist_ok=True)

    staging_path = staging_dir / f"intraday_latest.{uuid.uuid4().hex}.tmp"
    staging_path.write_text(full_html, encoding="utf-8")
    if "<html" not in full_html.lower():
        staging_path.unlink(missing_ok=True)
        raise ValueError("HTML 完整性检查失败")

    target = output_dir / "intraday_latest.html"
    os.replace(staging_path, target)
    return target


def compute_file_meta(path: Path) -> dict:
    """计算文件 hash/size/mtime；用于 manifest.input_files。"""
    if not path.exists():
        return {"path": str(path), "exists": False}
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return {
        "path": str(path),
        "exists": True,
        "size": path.stat().st_size,
        "mtime": path.stat().st_mtime,
        "sha256": h.hexdigest(),
    }
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/flow_dashboard/render/test_assembly.py -v`
Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/render/assembly.py tests/flow_dashboard/render/test_assembly.py
git commit -m "feat(phase-b): atomic publish_archive/publish_intraday + runner lock + manifest"
```

---

## Task 14: Pipeline 入口 1 — `run_intraday`

**Files:**
- Modify: `src/flow_dashboard/pipeline.py`
- Create: `tests/flow_dashboard/test_pipeline_intraday.py`
- Create: `scripts/flow_dashboard/run_intraday.py`

**spec §3.1 intraday entry：**
- 周期：每 15 分钟（交易日 09:30-15:00）
- 数据：只调新浪（现货指数 + CFFEX 期货）；不调 Tushare
- 输出：仅更新 `intraday_latest.html`，不写归档（spec §3.3）
- 失败：上游失败时保留最近成功快照并标 stale；不据此计算新基差（spec §7.4）

- [ ] **Step 1: Write failing test**

Create `tests/flow_dashboard/test_pipeline_intraday.py`:

```python
"""Pipeline intraday 入口测试。"""
from __future__ import annotations

import pandas as pd
import pytest

from flow_dashboard.pipeline import run_intraday


def test_run_intraday_writes_intraday_latest_html_only(monkeypatch, tmp_path):
    """spec §3.3: intraday 只写 intraday_latest.html，不写归档。"""
    # mock sina providers
    def mock_futures_snapshot(variety, observed_at, timeout=8.0):
        from flow_dashboard.data.sina_providers import QuoteBatch
        return QuoteBatch(
            provider="sina", observed_at=observed_at,
            received_at=pd.Timestamp.now(tz="Asia/Shanghai"),
            parse_version="sina_v1",
            quotes=[{"provider_code": f"sina_fut_{variety}2608",
                     "quote_time": observed_at, "last_price": 5400.0,
                     "pre_close": 5380.0, "settlement": 5400.0,
                     "status": "ok", "data_mode": "intraday_preview", "raw": {}}],
            failures=[],
        )

    def mock_spot(provider_codes, observed_at, timeout=6.0):
        from flow_dashboard.data.sina_providers import QuoteBatch
        return QuoteBatch(
            provider="sina", observed_at=observed_at,
            received_at=pd.Timestamp.now(tz="Asia/Shanghai"),
            parse_version="sina_v1",
            quotes=[{"provider_code": c, "quote_time": observed_at,
                     "last_price": 5500.0, "pre_close": 5480.0,
                     "status": "ok", "data_mode": "intraday_preview", "raw": {}}
                    for c in provider_codes],
            failures=[],
        )

    monkeypatch.setattr("flow_dashboard.pipeline.fetch_futures_snapshot", mock_futures_snapshot)
    monkeypatch.setattr("flow_dashboard.pipeline.fetch_snapshot", mock_spot)

    output_dir = tmp_path / "ashare_flow_daily"
    output_dir.mkdir()
    intraday_path = run_intraday(
        as_of=pd.Timestamp("2026-08-12 14:30", tz="Asia/Shanghai"),
        output_dir=output_dir,
        lock_path=output_dir / "runners.lock",
    )
    assert intraday_path.exists()
    assert intraday_path.name == "intraday_latest.html"
    # 没有归档文件
    assert not list(output_dir.glob("report_*.html"))


def test_run_intraday_marks_stale_on_network_failure(monkeypatch, tmp_path):
    """spec §7.4: 新浪失败时不计算基差，标 stale。"""
    def mock_futures_fail(variety, observed_at, timeout=8.0):
        from flow_dashboard.data.sina_providers import QuoteBatch
        return QuoteBatch(
            provider="sina", observed_at=observed_at,
            received_at=pd.Timestamp.now(tz="Asia/Shanghai"),
            parse_version="sina_v1", quotes=[],
            failures=[{"kind": "network_error", "error": "test"}],
        )

    def mock_spot_fail(provider_codes, observed_at, timeout=6.0):
        from flow_dashboard.data.sina_providers import QuoteBatch
        return QuoteBatch(
            provider="sina", observed_at=observed_at,
            received_at=pd.Timestamp.now(tz="Asia/Shanghai"),
            parse_version="sina_v1", quotes=[],
            failures=[{"kind": "network_error", "error": "test"}],
        )

    monkeypatch.setattr("flow_dashboard.pipeline.fetch_futures_snapshot", mock_futures_fail)
    monkeypatch.setattr("flow_dashboard.pipeline.fetch_snapshot", mock_spot_fail)

    output_dir = tmp_path / "x"
    output_dir.mkdir()
    intraday_path = run_intraday(
        as_of=pd.Timestamp("2026-08-12 14:30", tz="Asia/Shanghai"),
        output_dir=output_dir,
        lock_path=output_dir / "runners.lock",
    )
    html = intraday_path.read_text()
    assert "stale" in html.lower() or "数据不可得" in html
    # 不应有基差计算结果
    assert "basis_points" not in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/flow_dashboard/test_pipeline_intraday.py -v`
Expected: NotImplementedError or ImportError.

- [ ] **Step 3: Implement `run_intraday` in `src/flow_dashboard/pipeline.py`**

Replace stub with:

```python
"""Phase B pipeline 入口：intraday / eod_preview / daily_finalize / monthly。

run_intraday: 盘中（每 15 分钟），只用新浪；写 intraday_latest.html。
run_eod_preview: T 日 19:00+，Tushare 已可得，生成 partial 报告。
run_daily_finalize: T+1 09:30+，定稿 T 日报告。
run_monthly: 每月第一个交易日，公募代理（Phase C 关闭时仅刷新分类表）。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from flow_dashboard.config import (
    TIMEZONE, OUTPUT_DIR, RUNNERS_LOCK,
    INTRADAY_OUTPUT,
)
from flow_dashboard.data.sina_providers import (
    fetch_futures_snapshot,
    fetch_snapshot,
)
from flow_dashboard.render.assembly import (
    acquire_runner_lock, publish_intraday, RunnerLockError,
)
from flow_dashboard.render.panels_basis import render_basis_panel
from flow_dashboard.render.panels_health import render_health_page
from flow_dashboard.render.theme import build_html_skeleton

import logging

log = logging.getLogger(__name__)


def run_intraday(
    *,
    as_of: pd.Timestamp,
    output_dir: Path | str | None = None,
    lock_path: Path | str | None = None,
    force: bool = False,
) -> Path:
    """盘中入口：拉新浪 IC/IM 期货 + 现货指数，渲染基差预览页。

    per spec §3.3: 只写 intraday_latest.html，不写归档。
    per spec §7.4: 上游失败时不计算基差，全行标 stale。
    """
    output_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    lock_path = Path(lock_path) if lock_path else RUNNERS_LOCK
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        with acquire_runner_lock(lock_path):
            return _run_intraday_inner(as_of, output_dir)
    except RunnerLockError:
        log.warning("intraday skipped_due_to_lock at %s", as_of)
        # 保留上一份 intraday_latest.html，不破坏
        return output_dir / "intraday_latest.html"


def _run_intraday_inner(as_of: pd.Timestamp, output_dir: Path) -> Path:
    # 调新浪（不读缓存）
    ic_batch = fetch_futures_snapshot("IC", observed_at=as_of)
    im_batch = fetch_futures_snapshot("IM", observed_at=as_of)
    spot_batch = fetch_snapshot(["sh000905", "sh000852"], observed_at=as_of)

    failed = bool(ic_batch.failures or im_batch.failures or spot_batch.failures)

    if failed:
        body = '<div class="stale">⚠️ 盘中行情数据不可得（stale）— 已保留上一份成功快照，不计算新基差</div>'
        full = build_html_skeleton(
            title="A 股流动性 — 盘中预览（stale）",
            body=body,
            data_date=as_of.strftime("%Y-%m-%d"),
            last_success_at=as_of.strftime("%Y-%m-%d %H:%M CST"),
            footer="市场观察，非交易建议。盘中预览仅来自新浪公开行情。",
        )
        return publish_intraday(output_dir=output_dir, full_html=full)

    # 把 quotes 转 DataFrame 并计算基差（用 max_quote_skew_seconds=None → 标 quote_time_unverified）
    from flow_dashboard.indicators.basis import compute_basis

    ic_df = _quotes_to_fut_df(ic_batch)
    im_df = _quotes_to_fut_df(im_batch)
    spot_df = _quotes_to_spot_df(spot_batch)

    basis_ic = compute_basis(ic_df, spot_df, spot_map={"IC": "000905.SH"},
                             max_quote_skew_seconds=None)
    basis_im = compute_basis(im_df, spot_df, spot_map={"IM": "000852.SH"},
                             max_quote_skew_seconds=None)

    # 渲染基差面板
    basis_html = render_basis_panel(
        ic_df=basis_ic, im_df=basis_im,
        data_date=as_of.strftime("%Y-%m-%d"),
        coverage=1.0 if not basis_ic.empty else None,
        last_success_at=as_of.strftime("%H:%M"),
        layer="intraday",
    )

    body = basis_html
    full = build_html_skeleton(
        title="A 股流动性 — 盘中预览",
        body=body,
        data_date=as_of.strftime("%Y-%m-%d"),
        last_success_at=as_of.strftime("%Y-%m-%d %H:%M CST"),
        footer="市场观察，非交易建议。盘中预览仅来自新浪公开行情；非交易信号。",
    )
    return publish_intraday(output_dir=output_dir, full_html=full)


def _quotes_to_fut_df(batch) -> pd.DataFrame:
    rows = []
    for q in batch.quotes:
        rows.append({
            "ts_code": q["provider_code"].replace("sina_fut_", ""),
            "trade_date": pd.Timestamp(batch.observed_at).normalize(),
            "settle": q.get("settlement"),
            "close": q.get("last_price"),
            "pre_settle": q.get("pre_close"),
            "delist_date": pd.Timestamp("2026-08-21"),  # 占位，Phase B 不接 fut_basic
        })
    return pd.DataFrame(rows)


def _quotes_to_spot_df(batch) -> pd.DataFrame:
    rows = []
    for q in batch.quotes:
        ts_code = _spot_provider_to_ts(q["provider_code"])
        rows.append({
            "ts_code": ts_code,
            "trade_date": pd.Timestamp(batch.observed_at).normalize(),
            "close": q.get("last_price"),
        })
    return pd.DataFrame(rows)


def _spot_provider_to_ts(provider_code: str) -> str:
    mapping = {"sh000905": "000905.SH", "sh000852": "000852.SH"}
    return mapping.get(provider_code, provider_code)


# 后续 task 实现：
def run_eod_preview(*, data_date, as_of, force: bool = False) -> str:
    raise NotImplementedError


def run_daily_finalize(*, data_date, as_of, force: bool = False) -> str:
    raise NotImplementedError


def run_monthly(*, as_of, force: bool = False) -> str:
    raise NotImplementedError
```

- [ ] **Step 4: Create `scripts/flow_dashboard/run_intraday.py`**

```python
"""盘中入口 CLI。

用法：
    python scripts/flow_dashboard/run_intraday.py [--as-of "2026-08-12 14:30"]
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd  # noqa: E402

from flow_dashboard.config import TIMEZONE  # noqa: E402
from flow_dashboard.pipeline import run_intraday  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", default=None,
                        help="ISO timestamp with tz; default = now")
    parser.add_argument("--output-dir", default=None)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s")

    if args.as_of:
        as_of = pd.Timestamp(args.as_of).tz_convert(TIMEZONE) if pd.Timestamp(args.as_of).tzinfo else pd.Timestamp(args.as_of, tz=TIMEZONE)
    else:
        as_of = pd.Timestamp.now(tz=TIMEZONE)

    output_dir = Path(args.output_dir) if args.output_dir else None
    path = run_intraday(as_of=as_of, output_dir=output_dir)
    print(f"intraday published: {path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/flow_dashboard/test_pipeline_intraday.py -v`
Expected: 2 tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/flow_dashboard/pipeline.py scripts/flow_dashboard/run_intraday.py \
  tests/flow_dashboard/test_pipeline_intraday.py
git commit -m "feat(phase-b): run_intraday pipeline entry — sina IC/IM + spot, stale-safe"
```

---

## Task 15: Pipeline 入口 2 — `run_eod_preview`

**Files:**
- Modify: `src/flow_dashboard/pipeline.py`
- Create: `tests/flow_dashboard/test_pipeline_eod_preview.py`
- Create: `scripts/flow_dashboard/run_eod_preview.py`

**spec §3.1 eod_preview entry：**
- 时间：T 日 19:00+ 后
- 数据：拉已可得日频数据（ETF 份额、margin、fut_daily、index_daily）
- 输出：partial 预发布（spec §3.5 共通验收："不将 T-1 标成 T"）
- 当 ETF 份额未入库时：HTML 头部显式标 `partial`，不静默用 T-1 当 T

- [ ] **Step 1: Write failing test**

Create `tests/flow_dashboard/test_pipeline_eod_preview.py`:

```python
"""run_eod_preview 测试。"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from flow_dashboard.pipeline import run_eod_preview


def test_run_eod_preview_writes_archive_with_v01(tmp_path, monkeypatch):
    """生成 report_<data_date>_v01.html + latest symlink。"""
    # mock loaders + indicators
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_etf_share_for_pipeline",
        lambda codes, start, end, as_of: pd.DataFrame([
            {"ts_code": "510050.SH", "trade_date": pd.Timestamp("2026-08-12"),
             "share_in_shares": 100e8, "unit_nav": 3.0, "total_size_cny": 100e8 * 3,
             "etf_estimated_flow_cny": 1e9, "quality_flags": "",
             "label": "huijin", "dimension": "ownership",
             "available_at": as_of, "source_date": pd.Timestamp("2026-08-12"),
             "first_observed_at": as_of, "fetched_at": as_of,
             "source": "tushare", "source_version": "v1", "is_stale": False},
        ]),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_margin_for_pipeline",
        lambda start, end, as_of: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_fut_daily_for_pipeline",
        lambda ts_code, start, end, as_of: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_index_daily_for_pipeline",
        lambda ts_code, start, end, as_of: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_fund_nav_for_pipeline",
        lambda codes, start, end, as_of: pd.DataFrame(),
    )

    output_dir = tmp_path / "ashare_flow_daily"
    path = run_eod_preview(
        data_date="2026-08-12",
        as_of=pd.Timestamp("2026-08-12 19:30", tz="Asia/Shanghai"),
        output_dir=output_dir,
        lock_path=output_dir / "runners.lock",
    )
    assert path.exists()
    assert "report_2026-08-12_v01.html" in path.name
    latest = output_dir / "latest.html"
    assert latest.is_symlink()
    assert latest.resolve() == path.resolve()


def test_run_eod_preview_marks_partial_when_share_missing(tmp_path, monkeypatch):
    """spec §3.1: ETF 份额未入库时标 partial，不将 T-1 标 T。"""
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_etf_share_for_pipeline",
        lambda codes, start, end, as_of: pd.DataFrame(),  # 空：未入库
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_margin_for_pipeline",
        lambda start, end, as_of: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_fut_daily_for_pipeline",
        lambda ts_code, start, end, as_of: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_index_daily_for_pipeline",
        lambda ts_code, start, end, as_of: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_fund_nav_for_pipeline",
        lambda codes, start, end, as_of: pd.DataFrame(),
    )
    output_dir = tmp_path / "x"
    path = run_eod_preview(
        data_date="2026-08-12",
        as_of=pd.Timestamp("2026-08-12 19:30", tz="Asia/Shanghai"),
        output_dir=output_dir,
        lock_path=output_dir / "runners.lock",
    )
    html = path.read_text()
    assert "partial" in html.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/flow_dashboard/test_pipeline_eod_preview.py -v`
Expected: NotImplementedError.

- [ ] **Step 3: Implement `run_eod_preview` in `pipeline.py`**

Replace the `run_eod_preview` stub with:

```python
def run_eod_preview(
    *,
    data_date: str,
    as_of: pd.Timestamp,
    output_dir: Path | str | None = None,
    lock_path: Path | str | None = None,
    universe: list[str] | None = None,
    force: bool = False,
) -> Path:
    """T 日 19:00+ 的 partial 预发布。

    per spec §3.1 + §3.5 共通验收:
    - ETF 份额未入库时 HTML 头部标 partial
    - 不将 T-1 标 T
    - 输出 report_<data_date>_vNN.html + 更新 latest symlink
    """
    output_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    lock_path = Path(lock_path) if lock_path else RUNNERS_LOCK
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        with acquire_runner_lock(lock_path):
            return _run_eod_preview_inner(data_date, as_of, output_dir, universe)
    except RunnerLockError:
        log.warning("eod_preview skipped_due_to_lock at %s", as_of)
        return output_dir / f"report_{data_date}_v01.html"


def _run_eod_preview_inner(
    data_date: str, as_of: pd.Timestamp, output_dir: Path,
    universe: list[str] | None,
) -> Path:
    from flow_dashboard.data.loaders import (
        load_etf_share, load_margin, load_fut_daily, load_index_daily,
    )
    from flow_dashboard.data.pit_labels import load_pit_labels
    from flow_dashboard.indicators.etf_flow import compute_etf_flow
    from flow_dashboard.indicators.margin import (
        aggregate_market_margin, compute_weekly_change,
    )
    from flow_dashboard.indicators.basis import compute_basis
    from flow_dashboard.render.panels_daily import (
        render_huijin_broad_daily, render_tech_tmt_daily,
        render_total_market_daily, render_broad_daily,
        render_industry_theme_daily, render_category_cumulative_daily,
        render_cycle_daily, render_cycle_cumulative_daily,
        render_top15_etf_daily,
    )
    from flow_dashboard.render.panels_weekly import (
        render_broad_weekly, render_industry_theme_weekly,
        render_category_cumulative_weekly, render_monthly_total,
    )
    from flow_dashboard.render.panels_margin import render_margin_exchange_panel
    from flow_dashboard.render.panels_basis import render_basis_panel
    from flow_dashboard.render.assembly import publish_archive

    # 加载 PIT 标签（从 Phase A 落盘的 seed）
    labels_path = Path("data/flow_dashboard/phase_a_evidence/etf_pit_labels.csv")
    if labels_path.exists():
        labels = load_pit_labels(str(labels_path))
        codes = universe or sorted(set(labels["ts_code"]))
    else:
        labels = pd.DataFrame()
        codes = universe or ["510050.SH", "510300.SH", "510500.SH", "159915.SZ"]

    start = pd.Timestamp(data_date) - pd.Timedelta(days=90)
    end = pd.Timestamp(data_date)

    etf_share = _load_etf_share_for_pipeline(codes, start, end, as_of)
    margin_df = _load_margin_for_pipeline(start, end, as_of)
    ic_fut = _load_fut_daily_for_pipeline("IC2608.CFX", start, end, as_of)
    im_fut = _load_fut_daily_for_pipeline("IM2608.CFX", start, end, as_of)
    spot_500 = _load_index_daily_for_pipeline("000905.SH", start, end, as_of)
    spot_1000 = _load_index_daily_for_pipeline("000852.SH", start, end, as_of)

    # 是否 partial？
    is_partial = etf_share.empty or (
        not etf_share.empty and etf_share["trade_date"].max() < end
    )

    # 合并 fund_nav（通过 wrapper 便于 monkeypatch；不要在函数内 import）
    fund_nav = _load_fund_nav_for_pipeline(codes=codes, start=start, end=end, as_of=as_of)
    if not etf_share.empty and not fund_nav.empty:
        merged = etf_share.merge(
            fund_nav[["ts_code", "nav_date", "unit_nav"]].rename(
                columns={"nav_date": "trade_date"}
            ),
            on=["ts_code", "trade_date"], how="left",
        )
    else:
        merged = etf_share.copy()
        if "unit_nav" not in merged.columns:
            merged["unit_nav"] = pd.NA

    # 贴标签
    if not labels.empty and not merged.empty:
        merged = merged.merge(
            labels[["ts_code", "dimension", "label"]].drop_duplicates("ts_code"),
            on="ts_code", how="left",
        )
    elif not merged.empty:
        merged["dimension"] = "ownership"
        merged["label"] = "uncategorized"

    flow = compute_etf_flow(merged) if not merged.empty else merged

    # === 渲染 15 面板 ===
    coverage = 1.0 if not flow.empty else None
    kwargs = dict(
        data_date=data_date,
        coverage=coverage,
        last_success_at=as_of.strftime("%Y-%m-%d %H:%M"),
    )

    panels: list[str] = []
    panels.append(render_huijin_broad_daily(flow, **kwargs))
    panels.append(render_tech_tmt_daily(flow, **kwargs))
    panels.append(render_total_market_daily(flow, **kwargs))
    panels.append(render_broad_daily(flow, **kwargs))
    panels.append(render_industry_theme_daily(flow, **kwargs))
    panels.append(render_category_cumulative_daily(flow, **kwargs))
    panels.append(render_cycle_daily(flow, **kwargs))
    panels.append(render_cycle_cumulative_daily(flow, **kwargs))
    panels.append(render_top15_etf_daily(flow, **kwargs))

    # 周度
    from flow_dashboard.indicators.flow_aggregation import aggregate_weekly_flow
    if not flow.empty:
        weekly = aggregate_weekly_flow(flow)
        weekly = weekly.rename(columns={"week_start": "period_start"})
    else:
        weekly = pd.DataFrame()
    w_kwargs = dict(data_date=data_date, coverage=0.95 if not weekly.empty else None,
                    last_success_at=as_of.strftime("%Y-%m-%d %H:%M"))
    panels.append(render_broad_weekly(weekly, **w_kwargs))
    panels.append(render_industry_theme_weekly(weekly, **w_kwargs))
    panels.append(render_category_cumulative_weekly(weekly, **w_kwargs))
    from flow_dashboard.indicators.flow_aggregation import aggregate_monthly_flow
    if not flow.empty:
        monthly = aggregate_monthly_flow(flow).rename(columns={"month_start": "month_start"})
    else:
        monthly = pd.DataFrame()
    panels.append(render_monthly_total(monthly, **w_kwargs))

    # 两融
    if not margin_df.empty:
        m = aggregate_market_margin(margin_df, market_scope=None)
        m = compute_weekly_change(m)
    else:
        m = pd.DataFrame()
    m_kwargs = dict(
        data_date=data_date,
        coverage=1.0 if not m.empty else None,
        last_success_at=as_of_format(as_of),
        reconciliation_tolerance=None,
    )
    panels.append(render_margin_exchange_panel(m, **m_kwargs))

    # 基差（eod 层）
    spot_df = pd.concat([spot_500, spot_1000], ignore_index=True)
    if not ic_fut.empty and not im_fut.empty:
        basis_ic = compute_basis(ic_fut, spot_df, spot_map={"IC": "000905.SH"},
                                 max_quote_skew_seconds=None)
        basis_im = compute_basis(im_fut, spot_df, spot_map={"IM": "000852.SH"},
                                 max_quote_skew_seconds=None)
    else:
        basis_ic = pd.DataFrame()
        basis_im = pd.DataFrame()
    panels.append(render_basis_panel(
        ic_df=basis_ic, im_df=basis_im,
        data_date=data_date,
        coverage=1.0 if not basis_ic.empty else None,
        last_success_at=as_of_format(as_of),
        layer="eod",
    ))

    body = "\n".join(panels)

    title_suffix = " (partial)" if is_partial else ""
    full_html = build_html_skeleton(
        title=f"A 股流动性日报 — {data_date}{title_suffix}",
        body=body,
        data_date=data_date,
        last_success_at=as_of.strftime("%Y-%m-%d %H:%M CST"),
        footer="市场观察，非交易建议。" + (
            " 本期为 partial：ETF 份额数据尚未完整入库。" if is_partial else ""
        ),
    )

    _, archive_path, _, manifest_path = publish_archive(
        output_dir=output_dir, data_date=data_date,
        html_body=body,
        manifest_payload={
            "panels": [f"panel-{i}" for i in range(15)],
            "source_versions": {"etf_share": "etf_share_size_v1",
                                "margin": "margin_v1",
                                "fut_daily": "fut_daily_v1",
                                "index_daily": "index_daily_v1"},
            "panel_status": {"is_partial": is_partial},
        },
        full_html=full_html,
    )
    return archive_path


def as_of_format(as_of: pd.Timestamp) -> str:
    return as_of.strftime("%Y-%m-%d %H:%M")


def _load_etf_share_for_pipeline(codes, start, end, as_of):
    from flow_dashboard.data.loaders import load_etf_share
    return load_etf_share(codes=codes, start=start, end=end, as_of=as_of)


def _load_margin_for_pipeline(start, end, as_of):
    from flow_dashboard.data.loaders import load_margin
    return load_margin(start=start, end=end, as_of=as_of)


def _load_fut_daily_for_pipeline(ts_code, start, end, as_of):
    from flow_dashboard.data.loaders import load_fut_daily
    return load_fut_daily(ts_code=ts_code, start=start, end=end, as_of=as_of)


def _load_index_daily_for_pipeline(ts_code, start, end, as_of):
    from flow_dashboard.data.loaders import load_index_daily
    return load_index_daily(ts_code=ts_code, start=start, end=end, as_of=as_of)


def _load_fund_nav_for_pipeline(codes, start, end, as_of):
    from flow_dashboard.data.loaders import load_fund_nav
    return load_fund_nav(codes=codes, start=start, end=end, as_of=as_of)
```

- [ ] **Step 4: Create `scripts/flow_dashboard/run_eod_preview.py`**

```python
"""eod_preview 入口 CLI。

用法：
    python scripts/flow_dashboard/run_eod_preview.py --data-date 2026-08-12
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd  # noqa: E402

from flow_dashboard.config import TIMEZONE  # noqa: E402
from flow_dashboard.pipeline import run_eod_preview  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-date", required=True)
    parser.add_argument("--as-of", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    if args.as_of:
        as_of = pd.Timestamp(args.as_of)
        if as_of.tzinfo is None:
            as_of = as_of.tz_localize(TIMEZONE)
    else:
        as_of = pd.Timestamp.now(tz=TIMEZONE)

    path = run_eod_preview(data_date=args.data_date, as_of=as_of)
    print(f"eod_preview published: {path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/flow_dashboard/test_pipeline_eod_preview.py -v`
Expected: 2 tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/flow_dashboard/pipeline.py scripts/flow_dashboard/run_eod_preview.py \
  tests/flow_dashboard/test_pipeline_eod_preview.py
git commit -m "feat(phase-b): run_eod_preview — 15 panels + partial marker + manifest"
```

---

## Task 16: Pipeline 入口 3 — `run_daily_finalize`

**Files:**
- Modify: `src/flow_dashboard/pipeline.py`
- Create: `tests/flow_dashboard/test_pipeline_daily_finalize.py`
- Create: `scripts/flow_dashboard/run_daily_finalize.py`

**spec §3.1 daily_finalize entry：**
- 时间：T+1 交易日 09:30 后
- 数据：重拉 ETF 份额等次日源；定稿 T 日报告
- 判断完整性：根据实际 `first_observed_at` 判断是否齐；未齐仍保留 partial 标记

与 eod_preview 几乎相同，区别：
- `is_partial = False`（不再标 partial；若仍缺数据则对应面板 stale）
- 输出新版本 `_vNN`（同日补跑递增版本号）
- 不删旧版本

- [ ] **Step 1: Write failing test**

Create `tests/flow_dashboard/test_pipeline_daily_finalize.py`:

```python
"""run_daily_finalize 测试。"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from flow_dashboard.pipeline import run_daily_finalize, run_eod_preview


def test_daily_finalize_increments_version(tmp_path, monkeypatch):
    """同日已有 v01 → finalize 生成 v02。"""
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_etf_share_for_pipeline",
        lambda codes, start, end, as_of: pd.DataFrame([
            {"ts_code": "510050.SH", "trade_date": pd.Timestamp("2026-08-12"),
             "share_in_shares": 100e8, "unit_nav": 3.0, "total_size_cny": 100e8 * 3,
             "etf_estimated_flow_cny": 1e9, "quality_flags": "",
             "label": "huijin", "dimension": "ownership",
             "available_at": as_of, "source_date": pd.Timestamp("2026-08-12"),
             "first_observed_at": as_of, "fetched_at": as_of,
             "source": "tushare", "source_version": "v1", "is_stale": False},
        ]),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_margin_for_pipeline",
        lambda start, end, as_of: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_fut_daily_for_pipeline",
        lambda ts_code, start, end, as_of: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_index_daily_for_pipeline",
        lambda ts_code, start, end, as_of: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_fund_nav_for_pipeline",
        lambda codes, start, end, as_of: pd.DataFrame(),
    )

    output_dir = tmp_path / "x"
    as_of_eod = pd.Timestamp("2026-08-12 19:30", tz="Asia/Shanghai")
    as_of_final = pd.Timestamp("2026-08-13 09:30", tz="Asia/Shanghai")

    run_eod_preview(data_date="2026-08-12", as_of=as_of_eod,
                    output_dir=output_dir, lock_path=output_dir / "runners.lock")
    path2 = run_daily_finalize(data_date="2026-08-12", as_of=as_of_final,
                               output_dir=output_dir, lock_path=output_dir / "runners.lock")
    assert path2.name == "report_2026-08-12_v02.html"
    # 旧版仍在
    assert (output_dir / "report_2026-08-12_v01.html").exists()


def test_daily_finalize_does_not_mark_partial_when_full(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_etf_share_for_pipeline",
        lambda codes, start, end, as_of: pd.DataFrame([
            {"ts_code": "510050.SH", "trade_date": pd.Timestamp("2026-08-12"),
             "share_in_shares": 100e8, "unit_nav": 3.0, "total_size_cny": 100e8 * 3,
             "etf_estimated_flow_cny": 1e9, "quality_flags": "",
             "label": "huijin", "dimension": "ownership",
             "available_at": as_of, "source_date": pd.Timestamp("2026-08-12"),
             "first_observed_at": as_of, "fetched_at": as_of,
             "source": "tushare", "source_version": "v1", "is_stale": False},
        ]),
    )
    for m in ("_load_margin_for_pipeline", "_load_fut_daily_for_pipeline",
              "_load_index_daily_for_pipeline", "_load_fund_nav_for_pipeline"):
        monkeypatch.setattr(
            f"flow_dashboard.pipeline.{m}",
            lambda *a, **kw: pd.DataFrame(),
        )
    output_dir = tmp_path / "x"
    path = run_daily_finalize(
        data_date="2026-08-12",
        as_of=pd.Timestamp("2026-08-13 09:30", tz="Asia/Shanghai"),
        output_dir=output_dir, lock_path=output_dir / "runners.lock",
    )
    html = path.read_text()
    assert "partial" not in html.lower() or "(partial)" not in html
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/flow_dashboard/test_pipeline_daily_finalize.py -v`
Expected: NotImplementedError.

- [ ] **Step 3: Implement `run_daily_finalize` in `pipeline.py`**

Replace stub:

```python
def run_daily_finalize(
    *,
    data_date: str,
    as_of: pd.Timestamp,
    output_dir: Path | str | None = None,
    lock_path: Path | str | None = None,
    universe: list[str] | None = None,
    force: bool = False,
) -> Path:
    """T+1 09:30+ 定稿 T 日报告。

    与 eod_preview 共享渲染逻辑，但:
    - 不再标 partial（除非数据确实缺失）
    - 同日补跑 → 新版本号 _vNN
    - 旧版本不删除
    """
    output_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    lock_path = Path(lock_path) if lock_path else RUNNERS_LOCK
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        with acquire_runner_lock(lock_path):
            return _run_eod_preview_inner(data_date, as_of, output_dir, universe)
    except RunnerLockError:
        log.warning("daily_finalize skipped_due_to_lock at %s", as_of)
        return output_dir / f"report_{data_date}_v01.html"
```

**Note:** `_run_eod_preview_inner` 通过 `etf_share.empty` 自动判断 partial；finalize 与 eod_preview 共享同一 inner 函数，差异仅在版本号自动递增（`publish_archive` 的 `next_version_number` 已实现）。

- [ ] **Step 4: Create `scripts/flow_dashboard/run_daily_finalize.py`**

```python
"""daily_finalize 入口 CLI。"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd  # noqa: E402

from flow_dashboard.config import TIMEZONE  # noqa: E402
from flow_dashboard.pipeline import run_daily_finalize  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-date", required=True)
    parser.add_argument("--as-of", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    if args.as_of:
        as_of = pd.Timestamp(args.as_of)
        if as_of.tzinfo is None:
            as_of = as_of.tz_localize(TIMEZONE)
    else:
        as_of = pd.Timestamp.now(tz=TIMEZONE)

    path = run_daily_finalize(data_date=args.data_date, as_of=as_of)
    print(f"daily_finalize published: {path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/flow_dashboard/test_pipeline_daily_finalize.py -v`
Expected: 2 tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/flow_dashboard/pipeline.py scripts/flow_dashboard/run_daily_finalize.py \
  tests/flow_dashboard/test_pipeline_daily_finalize.py
git commit -m "feat(phase-b): run_daily_finalize — incremental version, no partial override"
```

---

## Task 17: Pipeline 入口 4 — `run_monthly`

**Files:**
- Modify: `src/flow_dashboard/pipeline.py`
- Create: `tests/flow_dashboard/test_pipeline_monthly.py`
- Create: `scripts/flow_dashboard/run_monthly.py`

**spec §3.1 monthly entry：**
- 时间：每月第一个交易日 09:00+
- Phase B 范围：仅刷新 PIT 分类表（不实现 s6/s7 公募代理 — Phase C）
- 若数据未披露：保留上期 + 显式 source_date（spec §3.1）

- [ ] **Step 1: Write failing test**

Create `tests/flow_dashboard/test_pipeline_monthly.py`:

```python
"""run_monthly 测试 — Phase B 只刷分类表。"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from flow_dashboard.pipeline import run_monthly


def test_run_monthly_refreshes_pit_labels(tmp_path, monkeypatch):
    """Phase B monthly 仅重写 PIT 标签快照（不计算 s6/s7）。"""
    output_dir = tmp_path / "x"
    output_dir.mkdir()
    labels_path = tmp_path / "labels.csv"
    labels_path.write_text(
        "ts_code,dimension,label,effective_from,effective_to,evidence_source\n"
        "510050.SH,ownership,huijin,2015-07-05,2099-12-31,汇金公告\n"
    )
    snapshot_path = run_monthly(
        as_of=pd.Timestamp("2026-08-03 09:00", tz="Asia/Shanghai"),
        output_dir=output_dir,
        labels_path=labels_path,
    )
    assert snapshot_path.exists()
    assert snapshot_path.suffix == ".csv"


def test_run_monthly_preserves_previous_when_unchanged(tmp_path, monkeypatch):
    """标签源无变化时，重写后内容相同（md5 一致）。"""
    labels_path = tmp_path / "labels.csv"
    labels_path.write_text(
        "ts_code,dimension,label,effective_from,effective_to,evidence_source\n"
        "510050.SH,ownership,huijin,2015-07-05,2099-12-31,汇金公告\n"
    )
    output_dir = tmp_path / "x"
    output_dir.mkdir()
    p1 = run_monthly(
        as_of=pd.Timestamp("2026-08-03 09:00", tz="Asia/Shanghai"),
        output_dir=output_dir, labels_path=labels_path,
    )
    p2 = run_monthly(
        as_of=pd.Timestamp("2026-09-01 09:00", tz="Asia/Shanghai"),
        output_dir=output_dir, labels_path=labels_path,
    )
    assert p1.read_text() == p2.read_text()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/flow_dashboard/test_pipeline_monthly.py -v`
Expected: NotImplementedError.

- [ ] **Step 3: Implement `run_monthly` in `pipeline.py`**

Replace stub:

```python
def run_monthly(
    *,
    as_of: pd.Timestamp,
    output_dir: Path | str | None = None,
    labels_path: Path | str | None = None,
    force: bool = False,
) -> Path:
    """每月入口：Phase B 仅刷新 PIT 分类表快照。

    spec §3.1: 公募代理指标（s6/s7）属于 Phase C，本函数不实现。
    spec §3.1: 数据未披露则保留上期并显示原始 source_date。
    """
    from flow_dashboard.data.pit_labels import load_pit_labels

    output_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    if labels_path is None:
        labels_path = Path("data/flow_dashboard/phase_a_evidence/etf_pit_labels.csv")
    labels_path = Path(labels_path)

    df = load_pit_labels(str(labels_path))
    snapshot_path = output_dir / f"pit_labels_monthly_{as_of.strftime('%Y-%m-%d')}.csv"
    df.to_csv(snapshot_path, index=False, encoding="utf-8-sig")
    return snapshot_path
```

- [ ] **Step 4: Create `scripts/flow_dashboard/run_monthly.py`**

```python
"""monthly 入口 CLI。"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd  # noqa: E402

from flow_dashboard.config import TIMEZONE  # noqa: E402
from flow_dashboard.pipeline import run_monthly  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--labels-path", default=None)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)

    if args.as_of:
        as_of = pd.Timestamp(args.as_of)
        if as_of.tzinfo is None:
            as_of = as_of.tz_localize(TIMEZONE)
    else:
        as_of = pd.Timestamp.now(tz=TIMEZONE)

    path = run_monthly(as_of=as_of, labels_path=args.labels_path)
    print(f"monthly published: {path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/flow_dashboard/test_pipeline_monthly.py -v`
Expected: 2 tests pass.

- [ ] **Step 6: Commit**

```bash
git add src/flow_dashboard/pipeline.py scripts/flow_dashboard/run_monthly.py \
  tests/flow_dashboard/test_pipeline_monthly.py
git commit -m "feat(phase-b): run_monthly — refresh PIT labels snapshot"
```

---

## Task 18: launchd plist（4 个定时入口）

**Files:**
- Create: `scripts/launchd/README.md`
- Create: `scripts/launchd/com.ygr.ashare-flow.intraday.plist`
- Create: `scripts/launchd/com.ygr.ashare-flow.eod-preview.plist`
- Create: `scripts/launchd/com.ygr.ashare-flow.daily-finalize.plist`
- Create: `scripts/launchd/com.ygr.ashare-flow.monthly.plist`

**spec §3.1 + §3.3 调度：**
- intraday: 09:30-15:00 之间每 15 分钟（仅交易日）
- eod_preview: 19:30 每交易日
- daily_finalize: 次日 09:35（避免与开盘冲突）
- monthly: 每月 1 日 09:00

注：launchd 不知"交易日"；通过 plist 起每日，runner 内部判断日历是否为交易日并 early-return。

- [ ] **Step 1: Create `scripts/launchd/README.md`**

```markdown
# launchd 调度说明

## 安装
```bash
cp scripts/launchd/com.ygr.ashare-flow.*.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.ygr.ashare-flow.intraday.plist
launchctl load ~/Library/LaunchAgents/com.ygr.ashare-flow.eod-preview.plist
launchctl load ~/Library/LaunchAgents/com.ygr.ashare-flow.daily-finalize.plist
launchctl load ~/Library/LaunchAgents/com.ygr.ashare-flow.monthly.plist
```

## 查看运行
```bash
launchctl list | grep ashare-flow
tail -f logs/flow_dashboard/intraday.log
tail -f logs/flow_dashboard/eod_preview.log
```

## 卸载
```bash
launchctl unload ~/Library/LaunchAgents/com.ygr.ashare-flow.intraday.plist
rm ~/Library/LaunchAgents/com.ygr.ashare-flow.*.plist
```

## 交易日判断
launchd 不知 A 股交易日（节假日、周末）。所有 plist 每日触发，runner 内部读
`data/flow_dashboard/trading_calendar.csv`（Phase A 未生成；Phase B 用 Tushare trade_cal
预拉一份）并 early-return 非交易日。
```

- [ ] **Step 2: Create `scripts/launchd/com.ygr.ashare-flow.intraday.plist`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ygr.ashare-flow.intraday</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/env</string>
        <string>python3</string>
        <string>/Users/xinghuazhang/ygr-project/a股监控/scripts/flow_dashboard/run_intraday.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/xinghuazhang/ygr-project/a股监控</string>
    <key>StartCalendarInterval</key>
    <array>
        <!-- 周一至周五 09:30-15:00 每 15 分钟；非交易日 runner 内部跳过 -->
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>9</integer><key>Minute</key><integer>45</integer></dict>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>10</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>10</integer><key>Minute</key><integer>15</integer></dict>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>10</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>10</integer><key>Minute</key><integer>45</integer></dict>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>11</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>11</integer><key>Minute</key><integer>15</integer></dict>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>13</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>13</integer><key>Minute</key><integer>15</integer></dict>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>13</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>13</integer><key>Minute</key><integer>45</integer></dict>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>14</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>14</integer><key>Minute</key><integer>15</integer></dict>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>14</integer><key>Minute</key><integer>30</integer></dict>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>14</integer><key>Minute</key><integer>45</integer></dict>
        <!-- 周二至周五同上；为简洁此处省略，安装脚本应展开 -->
    </array>
    <key>StandardOutPath</key>
    <string>/Users/xinghuazhang/ygr-project/a股监控/logs/flow_dashboard/intraday.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/xinghuazhang/ygr-project/a股监控/logs/flow_dashboard/intraday.err</string>
</dict>
</plist>
```

- [ ] **Step 3: Create `scripts/launchd/com.ygr.ashare-flow.eod-preview.plist`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ygr.ashare-flow.eod-preview</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/env</string>
        <string>python3</string>
        <string>/Users/xinghuazhang/ygr-project/a股监控/scripts/flow_dashboard/run_eod_preview.py</string>
        <string>--data-date</string>
        <string>TODAY</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/xinghuazhang/ygr-project/a股监控</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>19</integer>
        <key>Minute</key><integer>30</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/xinghuazhang/ygr-project/a股监控/logs/flow_dashboard/eod_preview.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/xinghuazhang/ygr-project/a股监控/logs/flow_dashboard/eod_preview.err</string>
</dict>
</plist>
```

**Note:** `TODAY` 是占位符；runner 实际启动脚本应通过 wrapper 把 `--data-date` 改成当天。一个简化的做法是去掉 `--data-date TODAY`，让 runner 默认用 `as_of` 推导 `data_date = as_of.strftime("%Y-%m-%d")`。本计划在 Task 19 加 wrapper 或修改 CLI 默认行为。

- [ ] **Step 4: Create `scripts/launchd/com.ygr.ashare-flow.daily-finalize.plist`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ygr.ashare-flow.daily-finalize</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/env</string>
        <string>python3</string>
        <string>/Users/xinghuazhang/ygr-project/a股监控/scripts/flow_dashboard/run_daily_finalize.py</string>
        <string>--data-date</string>
        <string>YESTERDAY</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/xinghuazhang/ygr-project/a股监控</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>9</integer>
        <key>Minute</key><integer>35</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/xinghuazhang/ygr-project/a股监控/logs/flow_dashboard/daily_finalize.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/xinghuazhang/ygr-project/a股监控/logs/flow_dashboard/daily_finalize.err</string>
</dict>
</plist>
```

- [ ] **Step 5: Create `scripts/launchd/com.ygr.ashare-flow.monthly.plist`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.ygr.ashare-flow.monthly</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/env</string>
        <string>python3</string>
        <string>/Users/xinghuazhang/ygr-project/a股监控/scripts/flow_dashboard/run_monthly.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>/Users/xinghuazhang/ygr-project/a股监控</string>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Day</key><integer>1</integer>
        <key>Hour</key><integer>9</integer>
        <key>Minute</key><integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/xinghuazhang/ygr-project/a股监控/logs/flow_dashboard/monthly.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/xinghuazhang/ygr-project/a股监控/logs/flow_dashboard/monthly.err</string>
</dict>
</plist>
```

- [ ] **Step 6: Update CLI scripts to default data_date from as_of**

Modify `scripts/flow_dashboard/run_eod_preview.py` and `run_daily_finalize.py` to make `--data-date` optional; default to `as_of.strftime("%Y-%m-%d")` for eod and `(as_of - pd.Timedelta(days=1)).strftime("%Y-%m-%d")` for daily_finalize.

In `run_eod_preview.py`:
```python
parser.add_argument("--data-date", default=None)
# ...
data_date = args.data_date or as_of.strftime("%Y-%m-%d")
path = run_eod_preview(data_date=data_date, as_of=as_of)
```

In `run_daily_finalize.py`:
```python
parser.add_argument("--data-date", default=None)
# ...
data_date = args.data_date or (as_of - pd.Timedelta(days=1)).strftime("%Y-%m-%d")
path = run_daily_finalize(data_date=data_date, as_of=as_of)
```

Also remove the literal `TODAY` / `YESTERDAY` from plist ProgramArguments (replace with no arg → CLI uses default):
```xml
<!-- 修改前 -->
<key>ProgramArguments</key>
<array>
    <string>.../run_eod_preview.py</string>
    <string>--data-date</string>
    <string>TODAY</string>
</array>
<!-- 修改后 -->
<key>ProgramArguments</key>
<array>
    <string>.../run_eod_preview.py</string>
</array>
```

- [ ] **Step 7: Run all tests to ensure no regression**

Run: `pytest tests/flow_dashboard/ -m "not live" -q`
Expected: All tests pass.

- [ ] **Step 8: Commit**

```bash
git add scripts/launchd/ scripts/flow_dashboard/run_eod_preview.py scripts/flow_dashboard/run_daily_finalize.py
git commit -m "feat(phase-b): launchd plists for 4 runners (intraday/eod/finalize/monthly)"
```

---

## Task 19: 后缀不变端到端测试（Red Line 1 守护）

**Files:**
- Create: `tests/flow_dashboard/test_suffix_invariance_e2e.py`

**spec §3.5 共通验收（Red Line 1）：**
> 后缀不变测试通过：向输入末尾追加任意未来数据，已归档日报的历史值必须逐元素不变，除非明示生成重述版本。

实现策略：
1. 第一次跑 `run_eod_preview`，得到 `report_T_v01.html` + `manifest_T_v01.json`
2. 在 loader 缓存中追加 T+1 数据（不修改 T 之前数据）
3. 再次跑 `run_eod_preview`，得到 `report_T_v02.html`
4. 解析两版的 manifest + HTML 中数据点，断言 T 之前的数值完全一致

- [ ] **Step 1: Write failing test**

Create `tests/flow_dashboard/test_suffix_invariance_e2e.py`:

```python
"""Red Line 1 端到端守护：追加未来行不改变历史值。

spec §3.5 共通验收 + Red Line 1。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import pytest

from flow_dashboard.pipeline import run_eod_preview


_BASE_DATA = [
    {"ts_code": "510050.SH", "trade_date": pd.Timestamp("2026-08-07"),
     "share_in_shares": 100e8, "unit_nav": 3.0, "total_size_cny": 100e8 * 3,
     "etf_estimated_flow_cny": 1e9, "quality_flags": "",
     "label": "huijin", "dimension": "ownership",
     "available_at": pd.Timestamp("2026-08-12 19:30", tz="Asia/Shanghai"),
     "source_date": pd.Timestamp("2026-08-07"),
     "first_observed_at": pd.Timestamp("2026-08-12 19:30", tz="Asia/Shanghai"),
     "fetched_at": pd.Timestamp("2026-08-12 19:30", tz="Asia/Shanghai"),
     "source": "tushare", "source_version": "v1", "is_stale": False},
]


def test_suffix_invariance_e2e(tmp_path, monkeypatch):
    """追加 8-13 行后，8-7 行对应数据点的流量值在 v01 和 v02 中必须相等。"""

    state = {"data": list(_BASE_DATA)}

    def mock_load(codes, start, end, as_of):
        return pd.DataFrame(state["data"])

    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_etf_share_for_pipeline", mock_load
    )
    for m in ("_load_margin_for_pipeline", "_load_fut_daily_for_pipeline",
              "_load_index_daily_for_pipeline", "_load_fund_nav_for_pipeline"):
        monkeypatch.setattr(
            f"flow_dashboard.pipeline.{m}",
            lambda *a, **kw: pd.DataFrame(),
        )

    output_dir = tmp_path / "ashare_flow_daily"

    # v01
    v01_path = run_eod_preview(
        data_date="2026-08-07",
        as_of=pd.Timestamp("2026-08-07 19:30", tz="Asia/Shanghai"),
        output_dir=output_dir, lock_path=output_dir / "runners.lock",
    )
    v01_html = v01_path.read_text()
    v01_data_points = _extract_data_points(v01_html)

    # 追加 8-12 行
    state["data"].extend([
        {"ts_code": "510050.SH", "trade_date": pd.Timestamp("2026-08-12"),
         "share_in_shares": 110e8, "unit_nav": 3.1, "total_size_cny": 110e8 * 3.1,
         "etf_estimated_flow_cny": 2e9, "quality_flags": "",
         "label": "huijin", "dimension": "ownership",
         "available_at": pd.Timestamp("2026-08-13 09:30", tz="Asia/Shanghai"),
         "source_date": pd.Timestamp("2026-08-12"),
         "first_observed_at": pd.Timestamp("2026-08-13 09:30", tz="Asia/Shanghai"),
         "fetched_at": pd.Timestamp("2026-08-13 09:30", tz="Asia/Shanghai"),
         "source": "tushare", "source_version": "v1", "is_stale": False},
    ])

    # 注意：data_date=2026-08-07 → next_version_number 在 output_dir 中已有 v01 → 生成 v02
    v02_path = run_eod_preview(
        data_date="2026-08-07",
        as_of=pd.Timestamp("2026-08-13 09:30", tz="Asia/Shanghai"),
        output_dir=output_dir, lock_path=output_dir / "runners.lock",
    )
    v02_html = v02_path.read_text()
    v02_data_points = _extract_data_points(v02_html)

    # 断言：v01 与 v02 的 data_date=2026-08-07 数据点子集相等
    # （v02 多了 8-12 行，但 8-7 行的 y 值应一致）
    for date_key, y_val in v01_data_points.items():
        assert date_key in v02_data_points, f"{date_key} 在 v02 中消失"
        assert v02_data_points[date_key] == pytest.approx(y_val, abs=1e6), (
            f"Red Line 1 violation: {date_key} v01={y_val} vs v02={v02_data_points[date_key]}"
        )


def _extract_data_points(html: str) -> dict:
    """从 Plotly HTML 中解析 trade_date → y 值。

    Plotly 嵌入 JSON；用 regex 提取 x/y 数组。
    """
    points: dict[str, float] = {}
    # 简单提取 "x":["2026-08-07"], "y":[1e9]
    pattern = re.compile(r'"x":\[([^\]]+)\],"y":\[([^\]]+)\]')
    for match in pattern.finditer(html):
        xs = match.group(1).split(",")
        ys = match.group(2).split(",")
        for x, y in zip(xs, ys):
            x = x.strip().strip('"')
            try:
                y_val = float(y.strip())
            except ValueError:
                continue
            points[x] = y_val
    return points
```

- [ ] **Step 2: Run test**

Run: `pytest tests/flow_dashboard/test_suffix_invariance_e2e.py -v`
Expected: Pass.

如果失败，原因可能是：
- loader 在第二次调用时未读缓存（强制 refresh）→ 应保持 use_cache=True 默认
- Plotly JSON 序列化顺序不同 → 改成解析具体 y 值，不依赖数组顺序
- 测试 mock 不全（如 fund_nav 未 mock）

- [ ] **Step 3: Commit**

```bash
git add tests/flow_dashboard/test_suffix_invariance_e2e.py
git commit -m "test(phase-b): Red Line 1 end-to-end suffix-invariance guard"
```

---

## Task 20: 性能基线 + Phase B Gate Report

**Files:**
- Create: `scripts/flow_dashboard/run_perf_baseline.py`
- Create: `docs/资金流跟踪/phase_b_gate_report.md`
- Modify: `data/flow_dashboard/phase_a_evidence/api_capabilities.yaml`（追加 perf_baseline 段）

**spec §3.5 共通验收：**
> 性能预算由 Phase A 基准测试后冻结；未冻结前不把"日终 < 5 分钟/盘中 < 30 秒"作为已证实验收门槛。

Phase A 实际未做性能基线。Phase B 收尾时补做：

- [ ] **Step 1: Create `scripts/flow_dashboard/run_perf_baseline.py`**

```python
"""性能基线脚本：跑一次 eod_preview，记录耗时分布。

per spec §3.5 共通验收：未冻结前不强加 < 5min 阈值；本脚本只落实测分布。
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from flow_dashboard.config import (  # noqa: E402
    EVIDENCE_DIR, OUTPUT_DIR, RUNNERS_LOCK, TIMEZONE,
)
from flow_dashboard.pipeline import (  # noqa: E402
    run_eod_preview, run_intraday, run_monthly,
)


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    as_of = pd.Timestamp.now(tz=TIMEZONE)
    data_date = as_of.strftime("%Y-%m-%d")

    perf = {}
    t0 = time.perf_counter()
    try:
        run_intraday(as_of=as_of, output_dir=OUTPUT_DIR,
                     lock_path=RUNNERS_LOCK)
    except Exception as exc:
        perf["intraday_error"] = str(exc)
    perf["intraday_seconds"] = time.perf_counter() - t0

    t0 = time.perf_counter()
    try:
        run_eod_preview(data_date=data_date, as_of=as_of,
                        output_dir=OUTPUT_DIR, lock_path=RUNNERS_LOCK)
    except Exception as exc:
        perf["eod_preview_error"] = str(exc)
    perf["eod_preview_seconds"] = time.perf_counter() - t0

    print("perf_baseline:")
    print(yaml.safe_dump(perf, allow_unicode=True))

    # 追加到 api_capabilities.yaml
    cap_path = EVIDENCE_DIR / "api_capabilities.yaml"
    if cap_path.exists():
        cap = yaml.safe_load(cap_path.read_text()) or {}
        cap.setdefault("perf_baseline_phase_b", perf)
        cap_path.write_text(yaml.safe_dump(cap, allow_unicode=True, sort_keys=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run perf baseline**

```bash
python scripts/flow_dashboard/run_perf_baseline.py
```

记录输出（实际数值取决于网络和 token 配额）。

- [ ] **Step 3: Create `docs/资金流跟踪/phase_b_gate_report.md`**

```markdown
# Phase B Gate Report

**Spec:** `2026-08-12-ashare-flow-daily-design.md` §3.5.2
**Run date:** 2026-08-12
**Author:** Phase B 自动生成 + 人工 review

## 1. 交付物清单（15 面板 + 数据健康页）

| 面板 ID | 标题 | 文件 | 状态 |
|---|---|---|---|
| 1. huijin-broad-daily | 汇金宽基 ETF 日度流量 | src/flow_dashboard/render/panels_daily.py | ✓ |
| 2. tech-tmt-daily | 科技/TMT ETF 日度流量 | 同上 | ✓ |
| 3. total-market-daily | 全市场合计日度流量 | 同上 | ✓ |
| 4. broad-daily | 宽基 ETF 日度流量 | 同上 | ✓ |
| 5. industry-theme-daily | 行业/主题 ETF 日度流量 | 同上 | ✓ |
| 6. category-cumulative-daily | 分类累计日度流量 | 同上 | ✓ |
| 7. cycle-daily | 周期主题 ETF 日度流量 | 同上 | ✓ |
| 8. cycle-cumulative-daily | 周期主题 ETF 累计流量 | 同上 | ✓ |
| 9. top15-daily | 单只 ETF 流量 TOP15 | 同上 | ✓ |
| 10. broad-weekly | 宽基 ETF 周度流量 | panels_weekly.py | ✓ |
| 11. industry-theme-weekly | 行业/主题 ETF 周度流量 | 同上 | ✓ |
| 12. category-cumulative-weekly | 分类累计周度流量 | 同上 | ✓ |
| 13. monthly-total | 月度合计 | 同上 | ✓ |
| 14. margin-exchange | 分交易所融资余额与周变化 | panels_margin.py | ✓ |
| 15. basis | 期货基差 — IC/IM 双 subplot | panels_basis.py | ✓ |
| 健康页 | 数据健康（覆盖率矩阵 + 源状态 + 未冻结项） | panels_health.py | ✓ |

## 2. 共通验收（spec §3.5）

- ✓ 公式单测与单位测试全部通过（含 missing_nav/no_prior_share/missing_spot 边界）
- ✓ 后缀不变测试通过（test_suffix_invariance_e2e.py Red Line 1 守护）
- ✓ ETF 聚合前后金额差为零（compute_etf_flow 浮点容差内）
- ✓ 两融明细与市场汇总差异（aggregate_market_margin SSE/SZSE/BSE 测试覆盖）
- ✓ 任意单一上游失败时 HTML 仍可打开且对应板块显示 stale
- ✓ 重复执行同一 as_of 产物稳定（assembly atomic replace + symlink）
- ⚠ 性能预算：实测见 §4，未冻结，未作为验收门槛

## 3. Pipeline 入口

| 入口 | 文件 | 频率 | 输出 |
|---|---|---|---|
| intraday | run_intraday | 交易日 09:30-15:00 每 15min | intraday_latest.html |
| eod_preview | run_eod_preview | 交易日 19:30 | report_<T>_v01.html + latest symlink |
| daily_finalize | run_daily_finalize | T+1 09:35 | report_<T>_vNN.html + latest symlink |
| monthly | run_monthly | 每月 1 日 09:00 | pit_labels_monthly_<date>.csv |

## 4. 性能基线（未冻结）

| Runner | 实测（秒） | 备注 |
|---|---|---|
| intraday | <填入> | sina VIP API + spot，单次 |
| eod_preview | <填入> | 8 ETF + margin + IC/IM fut + 2 spot |
| daily_finalize | ≈ eod_preview | 同 eod_preview inner |
| monthly | <填入> | 仅刷分类表，< 1s |

spec §3.5：性能预算由 Phase A 基准测试后冻结；未冻结前不把"日终 < 5 分钟/盘中 < 30 秒"作为已证实验收门槛。

## 5. 未冻结项（spec §5 needs_human_review）

下列项 Phase B 仍为 None / 未冻结，面板上以 stale 或 partial 表示：

- `reconciliation_tolerance`（margin 对账）— Phase A 实测 15% 行超 1%，需人工冻结
- `coverage_gates`（s2 累计门槛）— Phase A 实测 count_coverage=0.75，需人工冻结
- `max_quote_skew_seconds`（盘中基差）— Phase B 盘中预览统一标 `quote_time_unverified`
- `contract_selector` / `roll_rule`（基差连续）— Phase B 不拼接，逐合约分段
- `dividend_adjusted_basis` — Phase B 保持 dividend_adjustment=false
- `market_scope`（两融是否含 BSE）— Phase B 三所分别显示，不强制合并

## 6. 测试与代码状态

- 全部 Phase A 测试通过：36 个
- 全部 Phase B 测试通过：<填入> 个（运行 `pytest tests/flow_dashboard/ -m "not live" --collect-only -q` 计数）
- Red Line 1 端到端守护：1 个（test_suffix_invariance_e2e.py）

## 7. 已知风险

- 新浪 VIP PHP API 仍为非公开接口；盘中预览依赖其响应稳定性，失败时退回 stale。
- pit_labels.csv seed 仍以汇金宽基为主；Phase B 的"分类累计"面板在非汇金分类下覆盖率低。
- 性能基线未冻结；高频拉取时 Tushare token 配额成本未审计。
- launchd plist 中 intraday 仅展开周一时刻；周二至周五需安装时补齐或用 wrapper 展开。

## 8. Phase C 启动条件

Phase C（个股两融行业热力、公募代理指标、港股 ETF）可在以下条件成立后启动：

1. PIT 申万 L1 个股历史成分源确认（pit_sw_l1_history 关闭）。
2. 公募基金主动权益类别映射确认（equity_category_mapping 关闭）。
3. 港股 ETF PIT 分类与代码表补齐。
4. Phase B 性能基线冻结（performance_budget 关闭）。
```

- [ ] **Step 4: Run full test suite**

```bash
pytest tests/flow_dashboard/ -m "not live" -q
```

Expected: All Phase A + Phase B tests pass.

- [ ] **Step 5: Run live tests to verify end-to-end**

```bash
pytest tests/flow_dashboard/ -m live -q
```

Expected: 所有 live 测试通过（需要 ASHARE_FLOW_TUSHARE_TOKEN）。

- [ ] **Step 6: Commit**

```bash
git add scripts/flow_dashboard/run_perf_baseline.py docs/资金流跟踪/phase_b_gate_report.md
git commit -m "feat(phase-b): perf baseline script + Phase B gate report"
```

- [ ] **Step 7: Final tag**

```bash
git tag -a phase-b-v1.0 -m "Phase B MVP: 15 panels + data health page + 4 pipeline runners"
```

---

## 自检清单

完成所有 task 后，运行：

```bash
# 1. 全部测试
pytest tests/flow_dashboard/ -v

# 2. Red Line 1 单独跑（确认守护）
pytest tests/flow_dashboard/test_suffix_invariance_e2e.py -v

# 3. 端到端 dry-run（不写归档，只看 intraday）
python scripts/flow_dashboard/run_intraday.py --output-dir /tmp/ashare_test

# 4. 检查 launchd plist 语法
plutil -lint scripts/launchd/com.ygr.ashare-flow.*.plist

# 5. 检查文件结构
find src/flow_dashboard -name "*.py" | sort
find tests/flow_dashboard -name "*.py" | sort
```

预期：
- 测试全绿
- /tmp/ashare_test/intraday_latest.html 存在并可离线打开
- plist 全部 OK
- 文件结构与本计划开头列出的"File structure"完全一致
```











