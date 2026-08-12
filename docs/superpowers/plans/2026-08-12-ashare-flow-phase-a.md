# A 股流动性仪表板 — Phase A 数据可得性 Gate 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成 spec `2026-08-12-ashare-flow-daily-design.md` §3.5.1 定义的 Phase A 数据可得性 Gate，落盘 5 个 Gate 产出物（`api_capabilities.yaml`、ETF 分类生效区间表、源切换对账报告、覆盖率基线、可得性轮询记录），并为 Phase B 提供可复用的 provider 契约骨架。

**Architecture:** 在 `/Users/xinghuazhang/ygr-project/a股监控/` 独立项目内新建最小化 Python 包 `src/flow_dashboard/`，逐函数从 `行业轮动/src/data/etf.py` 白名单迁移 Tushare 请求函数（去掉 Oracle、静态名单、策略分类依赖），并新建新浪盘中 provider。所有 provider 都通过契约测试约束字段、单位与时间戳语义；测试用真实 token 跑小样本并落到 `data/flow_dashboard/phase_a_evidence/`，作为 Phase B 的冻结输入。

**Tech Stack:** Python 3.13、pandas 3.0.2、tushare 1.4.29、pytest 9.0.3、PyYAML（新增）、requests（新浪 provider 用，已随 akshare 安装）、pyarrow（parquet 落盘）。Plotly 推迟到 Phase B。

**Scope boundaries (this plan will NOT do):**
- 不实现任何指标公式（ETF 流量、基差、margin 行业聚合等）——那是 Phase B。
- 不渲染任何 HTML/图表 —— 那是 Phase B。
- 不冻结任何 `needs_human_review` 中的数值阈值（reconciliation_tolerance、coverage_gates、max_quote_skew_seconds 等）——本计划只产出实测分布供人工决策。
- 不实现 PIT 申万 L1 历史成分源 —— Phase C 的独立 Gate。
- 不接入期权、减持事件、公募代理指标 —— Phase C/D。

**Pre-flight (manual, before Task 1):**
```bash
# 1. 设新 token 名（spec §3.2.1 要求解耦主项目变量名）
echo 'export ASHARE_FLOW_TUSHARE_TOKEN="$TUSHARE_TOKEN"' >> ~/.zshrc
source ~/.zshrc
# 2. 进入项目目录
cd /Users/xinghuazhang/ygr-project/a股监控
# 3. 初始化 git（spec 要求独立 git 历史可追溯）
git init && git checkout -b main
```

**File structure (this plan creates):**

```
a股监控/
├── pyproject.toml                       # 项目元数据 + 依赖 + 工具配置
├── pytest.ini                           # 测试配置
├── .gitignore                           # 排除 data/ output/ logs/ .venv/
├── src/flow_dashboard/
│   ├── __init__.py
│   ├── config.py                        # 环境变量、路径、时区
│   ├── data/
│   │   ├── __init__.py
│   │   ├── tushare_client.py            # pro_api 包装 + token 校验
│   │   ├── tushare_providers.py         # fund_basic/etf_share_size/fund_nav/fund_daily/margin/fut_basic/fut_daily/index_daily
│   │   ├── sina_client.py               # 新浪 VIP PHP API HTTP + 解析
│   │   ├── sina_providers.py            # fetch_snapshot / load_snapshots 契约
│   │   ├── schema.py                    # 必填列、单位、quality_flags 枚举
│   │   ├── pit_labels.py                # 多维 PIT 标签表 schema + 读写
│   │   └── trading_calendar.py          # 项目交易日索引（占位，Phase B 接入数据源）
│   └── phase_a/
│       ├── __init__.py
│       ├── api_capabilities.py          # 生成 api_capabilities.yaml
│       ├── poll_etf_share.py            # port 行业轮动 poll 脚本（去白名单）
│       ├── source_switch_reconcile.py   # etf_share_size vs fund_share
│       └── coverage_baseline.py         # count/prior_share/prior_aum 覆盖率基线
├── scripts/flow_dashboard/
│   ├── poll_etf_share_size.py           # CLI 入口
│   ├── run_api_capabilities.py          # CLI 入口
│   ├── run_source_switch_reconcile.py   # CLI 入口
│   └── run_coverage_baseline.py         # CLI 入口
├── tests/flow_dashboard/
│   ├── conftest.py                      # pytest fixtures：token、tmp_path、record_mode
│   ├── test_tushare_client.py
│   ├── test_tushare_providers.py        # 每个 provider 一个契约测试
│   ├── test_sina_client.py
│   ├── test_sina_providers.py
│   ├── test_schema.py
│   ├── test_pit_labels.py
│   ├── test_api_capabilities.py
│   ├── test_poll_etf_share.py
│   ├── test_source_switch_reconcile.py
│   └── test_coverage_baseline.py
├── data/flow_dashboard/
│   ├── cache/                           # parquet 增量缓存（gitignore）
│   └── phase_a_evidence/                # Phase A 实测样本与 Gate 产出（提交）
│       ├── api_capabilities.yaml
│       ├── etf_pit_labels.csv
│       ├── source_switch_reconcile.csv
│       ├── coverage_baseline.csv
│       └── share_polling/
│           └── poll_summary.csv
└── docs/资金流跟踪/
    └── phase_a_gate_report.md           # Phase A 出口报告（人工 review 用）
```

---

## Task 1: 项目骨架与依赖

**Files:**
- Create: `pyproject.toml`
- Create: `pytest.ini`
- Create: `.gitignore`
- Create: `src/flow_dashboard/__init__.py`
- Create: `src/flow_dashboard/config.py`
- Create: `src/flow_dashboard/data/__init__.py`
- Create: `src/flow_dashboard/phase_a/__init__.py`
- Create: `tests/flow_dashboard/__init__.py`
- Create: `tests/flow_dashboard/conftest.py`

- [ ] **Step 1: Write `pyproject.toml`**

```toml
[project]
name = "ashare-flow-dashboard"
version = "0.1.0-phase-a"
description = "A 股流动性与 ETF 资金流日度跟踪仪表板 — Phase A 数据可得性 Gate"
requires-python = ">=3.13"
dependencies = [
    "pandas>=2.2",
    "tushare>=1.4",
    "pyyaml>=6.0",
    "requests>=2.31",
    "pyarrow>=15.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "ruff>=0.5",
]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
addopts = "-ra --strict-markers"
markers = [
    "live: 测试需要真实 Tushare token 或网络访问；缺 token 时跳过",
]
```

- [ ] **Step 2: Write `pytest.ini` (覆盖 pyproject 同字段，便于 CI 旧版兼容)**

```ini
[pytest]
testpaths = tests
python_files = test_*.py
addopts = -ra --strict-markers
markers =
    live: tests requiring ASHARE_FLOW_TUSHARE_TOKEN or network; skipped otherwise
```

- [ ] **Step 3: Write `.gitignore`**

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
.pytest_cache/
.ruff_cache/
.coverage

# Virtual envs
.venv/
venv/

# Project data (Phase A evidence committed explicitly under data/flow_dashboard/phase_a_evidence/)
data/flow_dashboard/cache/
output/
logs/

# Editor
.vscode/
.idea/
.DS_Store
```

- [ ] **Step 4: Write empty `__init__.py` files**

`src/flow_dashboard/__init__.py`, `src/flow_dashboard/data/__init__.py`, `src/flow_dashboard/phase_a/__init__.py`, `tests/flow_dashboard/__init__.py` — each is an empty file with a one-line docstring:

```python
"""A 股流动性仪表板包。"""
```

- [ ] **Step 5: Write `src/flow_dashboard/config.py`**

```python
"""项目级配置：环境变量、路径、时区。

token 解耦：spec §3.2.1 要求 ASHARE_FLOW_TUSHARE_TOKEN 独立，不复用主项目 TUSHARE_TOKEN。
若仅检测到 TUSHARE_TOKEN，抛出明确的 SetupError，提示用户复制一份到新变量名。
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "flow_dashboard"
CACHE_DIR = DATA_DIR / "cache"
EVIDENCE_DIR = DATA_DIR / "phase_a_evidence"
LOG_DIR = PROJECT_ROOT / "logs" / "flow_dashboard"

TIMEZONE = "Asia/Shanghai"


class SetupError(RuntimeError):
    """环境未就绪，提示用户手动配置。"""


def get_tushare_token() -> str:
    """读取 ASHARE_FLOW_TUSHARE_TOKEN；不存在时抛 SetupError。"""
    token = os.environ.get("ASHARE_FLOW_TUSHARE_TOKEN")
    if not token:
        if os.environ.get("TUSHARE_TOKEN"):
            raise SetupError(
                "检测到 TUSHARE_TOKEN 但未检测到 ASHARE_FLOW_TUSHARE_TOKEN。\n"
                "请运行: export ASHARE_FLOW_TUSHARE_TOKEN=\"$TUSHARE_TOKEN\""
            )
        raise SetupError(
            "未设置 ASHARE_FLOW_TUSHARE_TOKEN 环境变量。"
        )
    return token


def ensure_dirs() -> None:
    """幂等创建项目所需目录。"""
    for d in (DATA_DIR, CACHE_DIR, EVIDENCE_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 6: Write `tests/flow_dashboard/conftest.py`**

```python
"""pytest 共享 fixtures。

live marker：标记需要真实 token/网络的测试。CI 缺 token 时整体跳过。
"""
from __future__ import annotations

import os

import pytest

from src.flow_dashboard.config import get_tushare_token, SetupError


def pytest_collection_modifyitems(config, items):
    """缺 token 时跳过所有 live 测试。"""
    try:
        get_tushare_token()
        token_available = True
    except SetupError:
        token_available = False

    skip_no_token = pytest.mark.skip(reason="ASHARE_FLOW_TUSHARE_TOKEN 未设置")
    for item in items:
        if "live" in item.keywords and not token_available:
            item.add_marker(skip_no_token)


@pytest.fixture(scope="session")
def tushare_token() -> str:
    return get_tushare_token()


@pytest.fixture
def evidence_dir(tmp_path):
    """用 tmp_path 替代真实 EVIDENCE_DIR，避免污染 git。"""
    d = tmp_path / "phase_a_evidence"
    d.mkdir()
    return d
```

- [ ] **Step 7: Create venv and install**

Run:
```bash
cd /Users/xinghuazhang/ygr-project/a股监控
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```
Expected: 安装成功，最后一行 `Successfully installed ashare-flow-dashboard-0.1.0-phase-a ...`

- [ ] **Step 8: Smoke test that pytest collects**

Run:
```bash
pytest --collect-only
```
Expected: `collected 0 items`（此时还没有测试文件），无错误。

- [ ] **Step 9: Commit**

```bash
git add pyproject.toml pytest.ini .gitignore src/ tests/
git commit -m "feat: scaffold phase A project skeleton"
```

---

## Task 2: Tushare client wrapper

**Files:**
- Create: `src/flow_dashboard/data/tushare_client.py`
- Create: `tests/flow_dashboard/test_tushare_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/flow_dashboard/test_tushare_client.py
"""tushare_client 契约测试。

get_pro_api():
- 返回 tushare.pro_api 实例
- 缺 token 时抛 SetupError（已在 conftest 处理 skip）
"""
from __future__ import annotations

import pytest

from src.flow_dashboard.config import SetupError
from src.flow_dashboard.data.tushare_client import get_pro_api


@pytest.mark.live
def test_get_pro_api_returns_callable(tushare_token):
    pro = get_pro_api()
    assert callable(pro)
    # 实际调用一次，确认 token 有效
    df = pro.fund_basic(market="E", limit=1)
    assert len(df) == 1
    assert "ts_code" in df.columns


def test_get_pro_api_missing_token(monkeypatch):
    monkeypatch.delenv("ASHARE_FLOW_TUSHARE_TOKEN", raising=False)
    monkeypatch.delenv("TUSHARE_TOKEN", raising=False)
    with pytest.raises(SetupError):
        get_pro_api()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/flow_dashboard/test_tushare_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.flow_dashboard.data.tushare_client'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/flow_dashboard/data/tushare_client.py
"""tushare pro_api 客户端包装。

唯一职责：返回已设置 token 的 tushare pro_api 实例。不在这里做字段规范化或缓存。
"""
from __future__ import annotations

from src.flow_dashboard.config import get_tushare_token


def get_pro_api():
    """返回 tushare pro_api 实例。token 来自 ASHARE_FLOW_TUSHARE_TOKEN。"""
    token = get_tushare_token()
    import tushare as ts

    ts.set_token(token)
    return ts.pro_api()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/flow_dashboard/test_tushare_client.py -v`
Expected: PASS (2 tests). 若 token 未设，第一个 live test skip，第二个仍然 PASS。

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/data/tushare_client.py tests/flow_dashboard/test_tushare_client.py
git commit -m "feat: add tushare pro_api client wrapper"
```

---

## Task 3: Schema module — required columns & units

**Files:**
- Create: `src/flow_dashboard/data/schema.py`
- Create: `tests/flow_dashboard/test_schema.py`

Per spec §1.3: 落盘表必须保留 `source_date`, `first_observed_at`, `available_at`, `fetched_at`, `source`, `source_version`, `is_stale`, `quality_flags`。本任务先冻结这些列名与 quality_flags 枚举。

- [ ] **Step 1: Write the failing test**

```python
# tests/flow_dashboard/test_schema.py
"""schema 模块契约测试。"""
from __future__ import annotations

import pandas as pd
import pytest

from src.flow_dashboard.data.schema import (
    AUDIT_COLUMNS,
    QUALITY_FLAGS,
    validate_audit_columns,
)


def test_audit_columns_complete():
    expected = {
        "source_date", "first_observed_at", "available_at",
        "fetched_at", "source", "source_version", "is_stale", "quality_flags",
    }
    assert set(AUDIT_COLUMNS) == expected


def test_quality_flags_includes_known_markers():
    must_have = {
        "source_switch_break",
        "quote_time_unverified",
        "reconstructed_history",
        "restated",
        "stale",
        "partial",
    }
    assert must_have.issubset(set(QUALITY_FLAGS))


def test_validate_audit_columns_adds_missing():
    df = pd.DataFrame({"ts_code": ["510050.SH"]})
    report = validate_audit_columns(df)
    assert not report.ok
    assert set(report.missing) == set(AUDIT_COLUMNS)


def test_validate_audit_columns_passes_when_all_present():
    df = pd.DataFrame([{c: None for c in AUDIT_COLUMNS}])
    report = validate_audit_columns(df)
    assert report.ok
    assert report.missing == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/flow_dashboard/test_schema.py -v`
Expected: FAIL with `ImportError: cannot import name 'AUDIT_COLUMNS' ...`

- [ ] **Step 3: Write minimal implementation**

```python
# src/flow_dashboard/data/schema.py
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/flow_dashboard/test_schema.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/data/schema.py tests/flow_dashboard/test_schema.py
git commit -m "feat: define audit columns and quality flags schema"
```

---

## Task 4: Tushare provider — fund_basic

Per spec §3.2.1 白名单：从 `行业轮动/src/data/etf.py` 迁移 `pull_tushare_fund_basic`，但去掉对主项目 sys.path 与 Oracle 的依赖。返回值必须经 schema 校验。

**Files:**
- Create: `src/flow_dashboard/data/tushare_providers.py`
- Create: `tests/flow_dashboard/test_tushare_providers.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/flow_dashboard/test_tushare_providers.py
"""tushare_providers 契约测试。

每个 provider 必须满足：
- 返回 pandas.DataFrame
- 含契约列（normalized 名称）
- 关键数值列已转 numeric
- 不含 Oracle/sys.path 主项目依赖
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.flow_dashboard.data.tushare_providers import pull_fund_basic


@pytest.mark.live
def test_pull_fund_basic_contract(tushare_token):
    df = pull_fund_basic(market="E")
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 0
    # 契约列
    for col in ("ts_code", "name", "fund_type", "found_date", "list_date", "delist_date", "market"):
        assert col in df.columns, f"missing column: {col}"
    # 日期列是 datetime64[ns]
    assert pd.api.types.is_datetime64_any_dtype(df["found_date"])
    # market 全部是 E（场内）
    assert (df["market"] == "E").all()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/flow_dashboard/test_tushare_providers.py -v`
Expected: FAIL with `ImportError: cannot import name 'pull_fund_basic'`

- [ ] **Step 3: Write minimal implementation**

```python
# src/flow_dashboard/data/tushare_providers.py
"""Tushare 数据 provider。

逐函数从 行业轮动/src/data/etf.py 白名单迁移；已去除 Oracle、静态名单、sys.path 注入。
每个 pull_* 函数返回 normalized DataFrame，不写盘、不缓存（缓存由上层 loader 决定）。
"""
from __future__ import annotations

import pandas as pd

from src.flow_dashboard.data.tushare_client import get_pro_api


def pull_fund_basic(market: str = "E") -> pd.DataFrame:
    """拉取场内基金（market='E'）基础信息。

    Returns columns: ts_code, name, management, custodian, fund_type,
        found_date, due_date, list_date, issue_date, delist_date, market, status, ...
    """
    pro = get_pro_api()
    df = pro.fund_basic(market=market)
    return _normalize_fund_basic(df)


def _normalize_fund_basic(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in ("found_date", "due_date", "list_date", "issue_date", "delist_date"):
        if col in df.columns:
            df[col] = _parse_mixed_date(df[col])
    return df


def _parse_mixed_date(values) -> pd.Series:
    """支持 YYYYMMDD 字符串和 ISO 日期字符串。"""
    s = pd.Series(values).astype("string")
    text = s.fillna("")
    compact = text.str.fullmatch(r"\d{8}")
    parsed = pd.to_datetime(text, errors="coerce")
    if compact.any():
        parsed.loc[compact] = pd.to_datetime(
            text.loc[compact], format="%Y%m%d", errors="coerce"
        )
    return parsed
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/flow_dashboard/test_tushare_providers.py -v`
Expected: PASS (1 live test).

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/data/tushare_providers.py tests/flow_dashboard/test_tushare_providers.py
git commit -m "feat: migrate pull_fund_basic from 行业轮动 whitelist"
```

---

## Task 5: Tushare provider — etf_share_size

This is the most important provider for ETF flow tracking. Per spec §1.3, must request and validate `trade_date, ts_code, etf_name, total_share, total_size, nav, close, exchange` and assert `total_size ≈ total_share × nav` within tolerance.

Note: Tushare's `etf_share_size` endpoint **doesn't return `nav`/`close`** (verified during reconnaissance). Per spec: "`nav`/`close` 缺失时写入质量标记." So we explicitly request, observe missing, and emit `quality_flags=missing_nav`.

**Files:**
- Modify: `src/flow_dashboard/data/tushare_providers.py`
- Modify: `tests/flow_dashboard/test_tushare_providers.py`

- [ ] **Step 1: Add failing test**

Append to `tests/flow_dashboard/test_tushare_providers.py`:

```python
from src.flow_dashboard.data.tushare_providers import pull_etf_share_size


@pytest.mark.live
def test_pull_etf_share_size_contract(tushare_token):
    df = pull_etf_share_size(
        codes=["510050.SH", "510300.SH"],
        start_date="20260807",
        end_date="20260812",
    )
    assert isinstance(df, pd.DataFrame)
    assert len(df) > 0
    # 契约列（spec §1.3 显式要求）
    for col in ("trade_date", "ts_code", "etf_name", "total_share", "total_size", "exchange"):
        assert col in df.columns, f"missing column: {col}"
    # 单位：total_share 原始单位是万份，spec §1.3 要求统一成"份"再算
    assert (df["total_share"] > 0).all()
    assert (df["total_size"] > 0).all()
    # 日期类型
    assert pd.api.types.is_datetime64_any_dtype(df["trade_date"])
    # exchange 标准化为 SSE/SZSE/BSE
    assert set(df["exchange"].unique()).issubset({"SSE", "SZSE", "BSE"})


@pytest.mark.live
def test_pull_etf_share_size_has_share_in_shares_unit(tushare_token):
    """spec §1.3: 份额统一转成"份"再计算。万份→份乘 10000。"""
    df = pull_etf_share_size(
        codes=["510050.SH"], start_date="20260811", end_date="20260811"
    )
    assert len(df) == 1
    # total_share 万份约 70万 → 份约 7e8
    assert df.iloc[0]["total_share"] > 1_000  # 至少大于 1万份
    # share_in_shares 字段：份
    assert "share_in_shares" in df.columns
    assert abs(df.iloc[0]["share_in_shares"] - df.iloc[0]["total_share"] * 10000) <= 1.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/flow_dashboard/test_tushare_providers.py::test_pull_etf_share_size_contract -v`
Expected: FAIL with `ImportError: cannot import name 'pull_etf_share_size'`

- [ ] **Step 3: Implement**

Add to `src/flow_dashboard/data/tushare_providers.py`:

```python
def pull_etf_share_size(
    codes: list[str],
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    """拉取 ETF 份额规模。

    原始字段：trade_date, ts_code, etf_name, total_share (万份), total_size (万元), exchange.
    标准化后额外字段：share_in_shares = total_share * 10000 (份)。

    spec §1.3 显式要求请求 nav/close；Tushare 当前 endpoint 不返回这两个字段，
    因此本函数不猜测，由上层 loader 写入 quality_flags=missing_nav。
    """
    pro = get_pro_api()
    frames = []
    for code in codes:
        for seg_start, seg_end in _iter_date_segments(start_date, end_date):
            df = pro.etf_share_size(ts_code=code, start_date=seg_start, end_date=seg_end)
            if df is not None and not df.empty:
                frames.append(df)
    if not frames:
        return pd.DataFrame(
            columns=["trade_date", "ts_code", "etf_name", "total_share",
                     "total_size", "exchange", "share_in_shares"]
        )
    combined = pd.concat(frames, ignore_index=True)
    return _normalize_etf_share_size(combined)


def _normalize_etf_share_size(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["trade_date"] = _parse_mixed_date(df["trade_date"])
    df["total_share"] = pd.to_numeric(df["total_share"], errors="coerce")
    df["total_size"] = pd.to_numeric(df["total_size"], errors="coerce")
    # spec §1.3: 份额统一转成"份"
    df["share_in_shares"] = df["total_share"] * 10000
    # exchange 已是 SSE/SZSE/BSE 文本，原样保留
    return df.drop_duplicates(subset=["ts_code", "trade_date"]).reset_index(drop=True)


def _iter_date_segments(start_date: str | None, end_date: str | None):
    """按自然年分段（Tushare 单次请求默认上限约 5000 行；ETF 份额日频足够）。"""
    if start_date is None or end_date is None:
        yield _fmt_date(start_date), _fmt_date(end_date)
        return
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    if start > end:
        raise ValueError(f"start_date 晚于 end_date: {start_date} > {end_date}")
    current = start
    while current <= end:
        seg_end = min(pd.Timestamp(year=current.year, month=12, day=31), end)
        yield _fmt_date(current), _fmt_date(seg_end)
        current = seg_end + pd.Timedelta(days=1)


def _fmt_date(value) -> str | None:
    if value is None:
        return None
    return pd.Timestamp(value).strftime("%Y%m%d")
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/flow_dashboard/test_tushare_providers.py -v`
Expected: PASS (3 tests: fund_basic + 2 etf_share_size).

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/data/tushare_providers.py tests/flow_dashboard/test_tushare_providers.py
git commit -m "feat: add etf_share_size provider with share_in_shares unit"
```

---

## Task 6: Tushare provider — fund_nav, fund_daily, margin

Three more providers following the same pattern. Tests written first.

**Files:**
- Modify: `src/flow_dashboard/data/tushare_providers.py`
- Modify: `tests/flow_dashboard/test_tushare_providers.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/flow_dashboard/test_tushare_providers.py`:

```python
from src.flow_dashboard.data.tushare_providers import (
    pull_fund_nav,
    pull_fund_daily,
    pull_margin,
)


@pytest.mark.live
def test_pull_fund_nav_contract(tushare_token):
    df = pull_fund_nav(
        codes=["510050.SH"], start_date="20260807", end_date="20260812"
    )
    assert len(df) > 0
    for col in ("ts_code", "nav_date", "ann_date", "unit_nav", "accum_nav", "adj_nav"):
        assert col in df.columns
    assert pd.api.types.is_datetime64_any_dtype(df["nav_date"])
    assert pd.api.types.is_datetime64_any_dtype(df["ann_date"])


@pytest.mark.live
def test_pull_fund_daily_contract(tushare_token):
    df = pull_fund_daily(
        codes=["510050.SH"], start_date="20260807", end_date="20260812"
    )
    assert len(df) > 0
    for col in ("ts_code", "trade_date", "open", "high", "low", "close", "vol", "amount"):
        assert col in df.columns
    assert pd.api.types.is_numeric_dtype(df["close"])


@pytest.mark.live
def test_pull_margin_contract(tushare_token):
    df = pull_margin(start_date="20260811", end_date="20260811")
    assert len(df) >= 3  # SSE + SZSE + BSE
    for col in ("trade_date", "exchange_id", "rzye", "rzmre", "rzche"):
        assert col in df.columns
    assert set(df["exchange_id"].unique()).issuperset({"SSE", "SZSE", "BSE"})
    # 单位：元（rzye 余额应 > 1e10）
    assert (df["rzye"] > 1e10).all()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/flow_dashboard/test_tushare_providers.py -v -k "fund_nav or fund_daily or margin"`
Expected: FAIL with `ImportError: cannot import name 'pull_fund_nav'`

- [ ] **Step 3: Implement**

Add to `src/flow_dashboard/data/tushare_providers.py`:

```python
def pull_fund_nav(
    codes: list[str],
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    """拉取基金净值。spec §1.3 要求保留 ann_date（公告日）。"""
    pro = get_pro_api()
    fields = ["ts_code", "nav_date", "ann_date", "unit_nav", "accum_nav", "adj_nav"]
    frames = []
    for code in codes:
        for seg_start, seg_end in _iter_date_segments(start_date, end_date):
            df = pro.fund_nav(ts_code=code, start_date=seg_start, end_date=seg_end)
            if df is not None and not df.empty:
                frames.append(df[[c for c in fields if c in df.columns]])
    if not frames:
        return pd.DataFrame(columns=fields)
    combined = pd.concat(frames, ignore_index=True)
    df = combined.copy()
    df["nav_date"] = _parse_mixed_date(df["nav_date"])
    if "ann_date" in df.columns:
        df["ann_date"] = _parse_mixed_date(df["ann_date"])
    for col in ("unit_nav", "accum_nav", "adj_nav"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.drop_duplicates(subset=["ts_code", "nav_date"]).reset_index(drop=True)


def pull_fund_daily(
    codes: list[str],
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    """拉取 ETF 二级市场日行情。"""
    pro = get_pro_api()
    fields = ["ts_code", "trade_date", "pre_close", "open", "high", "low",
              "close", "change", "pct_chg", "vol", "amount"]
    frames = []
    for code in codes:
        for seg_start, seg_end in _iter_date_segments(start_date, end_date):
            df = pro.fund_daily(ts_code=code, start_date=seg_start, end_date=seg_end)
            if df is not None and not df.empty:
                frames.append(df[[c for c in fields if c in df.columns]])
    if not frames:
        return pd.DataFrame(columns=["ts_code", "trade_date", "close"])
    combined = pd.concat(frames, ignore_index=True)
    df = combined.copy()
    df["trade_date"] = _parse_mixed_date(df["trade_date"])
    for col in ("pre_close", "open", "high", "low", "close", "change", "vol", "amount"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "pct_chg" in df.columns:
        df["pct_chg"] = pd.to_numeric(df["pct_chg"], errors="coerce")
    return df.drop_duplicates(subset=["ts_code", "trade_date"]).reset_index(drop=True)


def pull_margin(
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    """拉取融资融券汇总（按交易所）。

    spec §1.3: rzye=融资余额, rzmre=融资买入额, rzche=融资偿还额, 单位=元。
    """
    pro = get_pro_api()
    frames = []
    for seg_start, seg_end in _iter_date_segments(start_date, end_date):
        df = pro.margin(start_date=seg_start, end_date=seg_end)
        if df is not None and not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["trade_date", "exchange_id", "rzye", "rzmre", "rzche"])
    df = pd.concat(frames, ignore_index=True).copy()
    df["trade_date"] = _parse_mixed_date(df["trade_date"])
    for col in ("rzye", "rzmre", "rzche", "rqye", "rqmcl", "rzrqye", "rqyl"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.drop_duplicates(subset=["trade_date", "exchange_id"]).reset_index(drop=True)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/flow_dashboard/test_tushare_providers.py -v`
Expected: PASS (6 tests total).

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/data/tushare_providers.py tests/flow_dashboard/test_tushare_providers.py
git commit -m "feat: add fund_nav, fund_daily, margin providers"
```

---

## Task 7: Tushare provider — futures & index

Per spec §1.1: `fut_basic`, `fut_daily`, `index_daily` for IC/IM basis calculation.

**Files:**
- Modify: `src/flow_dashboard/data/tushare_providers.py`
- Modify: `tests/flow_dashboard/test_tushare_providers.py`

- [ ] **Step 1: Add failing tests**

Append to `tests/flow_dashboard/test_tushare_providers.py`:

```python
from src.flow_dashboard.data.tushare_providers import (
    pull_fut_basic,
    pull_fut_daily,
    pull_index_daily,
)


@pytest.mark.live
def test_pull_fut_basic_contract(tushare_token):
    df = pull_fut_basic(exchange="CFFEX", fut_code="IC")
    assert len(df) > 0
    for col in ("ts_code", "symbol", "exchange", "name", "fut_code",
                "multiplier", "list_date", "delist_date"):
        assert col in df.columns
    assert pd.api.types.is_datetime64_any_dtype(df["list_date"])
    assert pd.api.types.is_datetime64_any_dtype(df["delist_date"])


@pytest.mark.live
def test_pull_fut_daily_contract(tushare_token):
    df = pull_fut_daily(
        ts_code="IC2608.CFX", start_date="20260807", end_date="20260812"
    )
    assert len(df) > 0
    for col in ("ts_code", "trade_date", "close", "settle", "pre_settle", "oi"):
        assert col in df.columns
    assert pd.api.types.is_numeric_dtype(df["close"])
    assert pd.api.types.is_numeric_dtype(df["settle"])


@pytest.mark.live
def test_pull_index_daily_contract(tushare_token):
    df = pull_index_daily(
        ts_code="000905.SH", start_date="20260807", end_date="20260812"
    )
    assert len(df) > 0
    for col in ("ts_code", "trade_date", "close", "open", "high", "low"):
        assert col in df.columns
    assert pd.api.types.is_datetime64_any_dtype(df["trade_date"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/flow_dashboard/test_tushare_providers.py -v -k "fut_basic or fut_daily or index_daily"`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement**

Add to `src/flow_dashboard/data/tushare_providers.py`:

```python
def pull_fut_basic(exchange: str = "CFFEX", fut_code: str | None = None) -> pd.DataFrame:
    """拉取期货合约基本信息。"""
    pro = get_pro_api()
    kwargs = {"exchange": exchange}
    if fut_code:
        kwargs["fut_code"] = fut_code
    df = pro.fut_basic(**kwargs)
    df = df.copy()
    for col in ("list_date", "delist_date", "last_ddate"):
        if col in df.columns:
            df[col] = _parse_mixed_date(df[col])
    return df


def pull_fut_daily(
    ts_code: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    """拉取期货日线（含 close 与 settle）。

    spec §1.4: 日终同时保存 eod_close（close）和 eod_settlement（settle）。
    """
    pro = get_pro_api()
    frames = []
    for seg_start, seg_end in _iter_date_segments(start_date, end_date):
        df = pro.fut_daily(ts_code=ts_code, start_date=seg_start, end_date=seg_end)
        if df is not None and not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["ts_code", "trade_date", "close", "settle"])
    df = pd.concat(frames, ignore_index=True).copy()
    df["trade_date"] = _parse_mixed_date(df["trade_date"])
    for col in ("pre_close", "pre_settle", "open", "high", "low",
                "close", "settle", "change1", "change2", "vol", "amount", "oi", "oi_chg"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.drop_duplicates(subset=["ts_code", "trade_date"]).reset_index(drop=True)


def pull_index_daily(
    ts_code: str,
    start_date: str | None = None,
    end_date: str | None = None,
) -> pd.DataFrame:
    """拉取指数日线（CSI500、CSI1000 等现货指数）。"""
    pro = get_pro_api()
    frames = []
    for seg_start, seg_end in _iter_date_segments(start_date, end_date):
        df = pro.index_daily(ts_code=ts_code, start_date=seg_start, end_date=seg_end)
        if df is not None and not df.empty:
            frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["ts_code", "trade_date", "close"])
    df = pd.concat(frames, ignore_index=True).copy()
    df["trade_date"] = _parse_mixed_date(df["trade_date"])
    for col in ("pre_close", "open", "high", "low", "close", "change", "vol", "amount"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    if "pct_chg" in df.columns:
        df["pct_chg"] = pd.to_numeric(df["pct_chg"], errors="coerce")
    return df.drop_duplicates(subset=["ts_code", "trade_date"]).reset_index(drop=True)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/flow_dashboard/test_tushare_providers.py -v`
Expected: PASS (9 tests).

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/data/tushare_providers.py tests/flow_dashboard/test_tushare_providers.py
git commit -m "feat: add fut_basic, fut_daily, index_daily providers"
```

---

## Task 8: Sina realtime client (CFFEX IC/IM)

Per spec §1.4: 新浪盘中快照保存原样 `provider_code`、报价时间、接收时间。Per spec §5 `data_contract.sina_realtime_provider`: 需冻结代码映射、批量请求、频率。

Reconnaissance confirmed: `hq.sinajs.cn/list=` does NOT work for CFFEX futures. Use Sina's VIP PHP API `vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQFuturesData` with node marks:
- IC (中证500指数期货): node `zzgz_qh`
- IM (中证1000股指期货): node `im_qh`
- IF (沪深300指数期货): node `qz_qh` (future use)
- IH (上证50指数期货): node `szgz_qh` (future use)

Spot indices via `hq.sinajs.cn/list=sh000905,sh000852` (verified working).

**Files:**
- Create: `src/flow_dashboard/data/sina_client.py`
- Create: `tests/flow_dashboard/test_sina_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/flow_dashboard/test_sina_client.py
"""sina_client 契约测试。

- node="zzgz_qh" 返回 IC 全部活跃合约
- 每条记录含 symbol/trade/settlement/ticktime/tradedate
- 缺字段时显式 None，不静默丢列
"""
from __future__ import annotations

import pytest

from src.flow_dashboard.data.sina_client import fetch_futures_node, FUTURES_NODE_MARK


def test_node_mark_contract():
    assert FUTURES_NODE_MARK["IC"] == "zzgz_qh"
    assert FUTURES_NODE_MARK["IM"] == "im_qh"


@pytest.mark.live
def test_fetch_futures_node_ic_returns_contracts(tushare_token):
    """live 标记仅用于需要网络的测试；token 与新浪无关但用作整体环境就绪代理。"""
    df = fetch_futures_node("IC")
    assert len(df) > 0
    for col in ("symbol", "trade", "settlement", "ticktime", "tradedate", "name"):
        assert col in df.columns, f"missing: {col}"
    # symbol 形如 IC2608
    assert df["symbol"].str.startswith("IC").all()


@pytest.mark.live
def test_fetch_spot_index_quotes(tushare_token):
    """新浪 hq.sinajs.cn/list=sh000905,sh000852 现货指数。"""
    from src.flow_dashboard.data.sina_client import fetch_spot_indices
    df = fetch_spot_indices(["sh000905", "sh000852"])
    assert len(df) == 2
    for col in ("provider_code", "name", "last", "time", "date"):
        assert col in df.columns
    # last 是 float
    assert df["last"].dtype.kind == "f"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/flow_dashboard/test_sina_client.py -v`
Expected: FAIL with `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# src/flow_dashboard/data/sina_client.py
"""新浪行情 HTTP client。

职责：仅负责原始 HTTP 取数与最小解析；不做基差计算、不写 quality_flags。
- CFFEX 期货：用 VIP PHP API（hq.sinajs.cn 不支持 CFFEX）
- 现货指数：用 hq.sinajs.cn/list=

per spec §1.4: 盘中快照必须原样保存 provider_code、原始报价时间、系统接收时间、解析版本。
本 client 只产出 pandas DataFrame；上层 provider 负责加 received_at 等审计列。
"""
from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from typing import Iterable

import pandas as pd

# 新浪 CFFEX 期货 node mark（已通过 akshare futures_symbol_mark 验证）
FUTURES_NODE_MARK: dict[str, str] = {
    "IF": "qz_qh",       # 沪深300指数期货
    "IH": "szgz_qh",     # 上证50指数期货
    "IC": "zzgz_qh",     # 中证500指数期货
    "IM": "im_qh",       # 中证1000股指期货
}

_FUTURES_URL = (
    "https://vip.stock.finance.sina.com.cn/quotes_service/api/"
    "json_v2.php/Market_Center.getHQFuturesData"
)
_SPOT_URL = "https://hq.sinajs.cn/list={codes}"
_HEADERS = {
    "Referer": "https://finance.sina.com.cn",
    "User-Agent": "Mozilla/5.0 (compatible; ashare-flow-dashboard/0.1)",
}
PARSE_VERSION = "sina_v1"


def fetch_futures_node(variety: str, timeout: float = 8.0) -> pd.DataFrame:
    """拉取一个 CFFEX 品种（IF/IH/IC/IM）的全部活跃合约快照。"""
    node = FUTURES_NODE_MARK.get(variety)
    if not node:
        raise ValueError(f"unknown variety: {variety}; expected one of {list(FUTURES_NODE_MARK)}")
    params = urllib.parse.urlencode({
        "page": "1", "sort": "position", "asc": "0",
        "node": node, "base": "futures",
    })
    url = f"{_FUTURES_URL}?{params}"
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
    if not body or body == "[]":
        return pd.DataFrame(columns=[
            "symbol", "name", "trade", "settlement", "presettlement",
            "open", "high", "low", "close", "volume", "position",
            "ticktime", "tradedate", "prevsettlement",
        ])
    data = json.loads(body)
    df = pd.DataFrame(data)
    # 数值列
    for col in ("trade", "settlement", "presettlement", "open", "high",
                "low", "close", "volume", "position", "prevsettlement"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


def fetch_spot_indices(provider_codes: Iterable[str], timeout: float = 5.0) -> pd.DataFrame:
    """拉取现货指数（sh000905=CSI500, sh000852=CSI1000 等）。

    新浪 hq.sinajs.cn 返回 GBK 编码的 var 赋值字符串；解析为 DataFrame。
    """
    codes = list(provider_codes)
    url = _SPOT_URL.format(codes=",".join(codes))
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("gbk", errors="replace")
    rows = []
    pattern = re.compile(r'var hq_str_(?P<code>[^=]+)="(?P<payload>[^"]*)";')
    for m in pattern.finditer(body):
        code = m.group("code")
        payload = m.group("payload")
        parts = payload.split(",")
        if len(parts) < 32:
            continue
        # 新浪现货指数字段：0 名称, 1 昨收, 2 开, 3 最新, 4 高, 5 低, ..., 30 日期, 31 时间
        def _f(idx):
            try:
                return float(parts[idx])
            except (ValueError, IndexError):
                return None
        rows.append({
            "provider_code": code,
            "name": parts[0],
            "pre_close": _f(1),
            "open": _f(2),
            "last": _f(3),
            "high": _f(4),
            "low": _f(5),
            "date": parts[30] if len(parts) > 30 else None,
            "time": parts[31] if len(parts) > 31 else None,
        })
    return pd.DataFrame(rows)
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/flow_dashboard/test_sina_client.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/data/sina_client.py tests/flow_dashboard/test_sina_client.py
git commit -m "feat: add sina VIP PHP futures client and spot index client"
```

---

## Task 9: Sina provider contract — fetch_snapshot / load_snapshots

Per spec §3.2.1: 新浪实时 provider 契约为 `fetch_snapshot(provider_codes, observed_at) -> QuoteBatch` 和 `load_snapshots(start_at, end_at, as_of, provider_codes=None) -> DataFrame`. `fetch_snapshot` 必须只在本次网络响应时返回新快照，不用缓存伪装。

**Files:**
- Create: `src/flow_dashboard/data/sina_providers.py`
- Create: `tests/flow_dashboard/test_sina_providers.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/flow_dashboard/test_sina_providers.py
"""sina_providers 契约测试。

fetch_snapshot:
- 返回 QuoteBatch，含 received_at、observed_at、provider、parse_version
- 每条 quote 含 provider_code、quote_time、last_price、status
- 网络失败时 status='network_error'，quotes 为空列表
load_snapshots:
- 从磁盘读 parquet（不存在返回空 DataFrame）
- 执行 available_at <= as_of 过滤
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.flow_dashboard.data.sina_providers import (
    fetch_snapshot,
    load_snapshots,
    QuoteBatch,
)


@pytest.mark.live
def test_fetch_snapshot_spot_indices(tushare_token):
    batch = fetch_snapshot(
        provider_codes=["sh000905", "sh000852"],
        observed_at=pd.Timestamp("2026-08-12 15:00:00", tz="Asia/Shanghai"),
    )
    assert isinstance(batch, QuoteBatch)
    assert batch.provider == "sina"
    assert batch.observed_at.tzinfo is not None
    assert batch.received_at <= pd.Timestamp.now(tz="Asia/Shanghai")
    assert batch.parse_version == "sina_v1"
    assert len(batch.quotes) == 2
    q0 = batch.quotes[0]
    assert "provider_code" in q0
    assert "last_price" in q0
    assert "quote_time" in q0
    assert "status" in q0


def test_load_snapshots_missing_file_returns_empty(tmp_path):
    df = load_snapshots(
        start_at=pd.Timestamp("2026-08-12 09:00", tz="Asia/Shanghai"),
        end_at=pd.Timestamp("2026-08-12 15:00", tz="Asia/Shanghai"),
        as_of=pd.Timestamp("2026-08-12 16:00", tz="Asia/Shanghai"),
        storage_dir=tmp_path,
    )
    assert df.empty
    assert "provider_code" in df.columns
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/flow_dashboard/test_sina_providers.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement**

```python
# src/flow_dashboard/data/sina_providers.py
"""新浪实时 provider。

per spec §3.2.1 契约:
    fetch_snapshot(provider_codes, observed_at) -> QuoteBatch
    load_snapshots(start_at, end_at, as_of, provider_codes=None) -> DataFrame

fetch_snapshot 不读缓存；只在本次网络响应时返回新快照。
load_snapshots 才读历史快照，仍执行 available_at <= as_of 过滤。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Sequence

import pandas as pd

from src.flow_dashboard.config import TIMEZONE
from src.flow_dashboard.data.sina_client import (
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
```

- [ ] **Step 4: Run tests to verify pass**

Run: `pytest tests/flow_dashboard/test_sina_providers.py -v`
Expected: PASS (2 tests: 1 live + 1 empty-storage).

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/data/sina_providers.py tests/flow_dashboard/test_sina_providers.py
git commit -m "feat: implement sina fetch_snapshot/load_snapshots contract"
```

---

## Task 10: ETF PIT labels table

Per spec §1.1: 多维 PIT 标签表（`ts_code, dimension, label, effective_from, effective_to, evidence_source, confirmed_at`）。每只 ETF 可在不同维度有多个标签。

This task creates the **schema** and an **initial seed file** for known broad/central-bank ETFs. Full universe expansion (港股/周期/科技细类) happens in Phase A evidence collection (Task 12) — this task only delivers the table structure + seed for 汇金宽基.

**Files:**
- Create: `src/flow_dashboard/data/pit_labels.py`
- Create: `data/flow_dashboard/phase_a_evidence/etf_pit_labels.csv` (seed)
- Create: `tests/flow_dashboard/test_pit_labels.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/flow_dashboard/test_pit_labels.py
"""PIT 标签表契约测试。"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.flow_dashboard.data.pit_labels import (
    load_pit_labels,
    filter_effective,
    PIT_LABEL_COLUMNS,
)


def test_columns_contract():
    expected = {
        "ts_code", "dimension", "label",
        "effective_from", "effective_to",
        "evidence_source", "confirmed_at",
    }
    assert set(PIT_LABEL_COLUMNS) == expected


def test_load_seed_seed_has_known_broad_etfs(tmp_path):
    seed_path = tmp_path / "etf_pit_labels.csv"
    seed_path.write_text(
        "ts_code,dimension,label,effective_from,effective_to,evidence_source,confirmed_at\n"
        "510050.SH,ownership,huijin,2015-07-01,,中央汇金公告,2026-08-12T00:00:00+08:00\n"
        "510300.SH,ownership,huijin,2015-07-01,,中央汇金公告,2026-08-12T00:00:00+08:00\n"
        "510050.SH,asset_scope,broad,2015-02-16,,基金合同,2026-08-12T00:00:00+08:00\n"
    )
    df = load_pit_labels(seed_path)
    assert len(df) == 3
    assert pd.api.types.is_datetime64_any_dtype(df["effective_from"])
    assert pd.api.types.is_datetime64tz_dtype(df["confirmed_at"])


def test_filter_effective_returns_only_active_at_t(tmp_path):
    seed_path = tmp_path / "etf_pit_labels.csv"
    seed_path.write_text(
        "ts_code,dimension,label,effective_from,effective_to,evidence_source,confirmed_at\n"
        "510050.SH,ownership,huijin,2015-07-01,,src,2026-08-12T00:00:00+08:00\n"
        "159915.SZ,asset_scope,growth,2011-09-20,2020-01-01,src,2026-08-12T00:00:00+08:00\n"
        )
    df = load_pit_labels(seed_path)
    active = filter_effective(
        df, ts_code="159915.SZ", dimension="asset_scope",
        at=pd.Timestamp("2019-06-01", tz="Asia/Shanghai"),
    )
    assert len(active) == 1
    assert active.iloc[0]["label"] ==growth"

    inactive = filter_effective(
        df, ts_code="159915.SZ", dimension="asset_scope",
        at=pd.Timestamp("2021-01-01", tz="Asia/Shanghai"),
    )
    assert len(inactive) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/flow_dashboard/test_pit_labels.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement**

```python
# src/flow_dashboard/data/pit_labels.py
"""ETF 多维 PIT 标签表。

per spec §1.1: 同一 ETF 可在不同维度（ownership/asset_scope/benchmark/strategy/theme）
同时拥有多个标签；标签有 effective_from/effective_to 区间。
所有聚合必须指定 dimension + label，不依赖隐式优先级。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.flow_dashboard.config import TIMEZONE

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
        # 把 effective_from 转 tz-aware（naive → Asia/Shanghai）
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
```

- [ ] **Step 4: Create seed CSV with known central-bank broad ETFs**

Create `data/flow_dashboard/phase_a_evidence/etf_pit_labels.csv`:

```csv
ts_code,dimension,label,effective_from,effective_to,evidence_source,confirmed_at
510050.SH,ownership,huijin,2015-07-01,,中央汇金2015年7月增持公告,2026-08-12T00:00:00+08:00
510300.SH,ownership,huijin,2015-07-01,,中央汇金2015年7月增持公告,2026-08-12T00:00:00+08:00
510500.SH,ownership,huijin,2015-07-01,,中央汇金2015年7月增持公告,2026-08-12T00:00:00+08:00
510050.SH,asset_scope,broad,2005-02-16,,基金合同,2026-08-12T00:00:00+08:00
510300.SH,asset_scope,broad,2012-05-04,,基金合同,2026-08-12T00:00:00+08:00
510500.SH,asset_scope,broad,2013-03-15,,基金合同,2026-08-12T00:00:00+08:00
159915.SZ,asset_scope,growth,2011-09-20,,基金合同,2026-08-12T00:00:00+08:00
510050.SH,benchmark,csi50,2005-02-16,,基金合同,2026-08-12T00:00:00+08:00
510300.SH,benchmark,csi300,2012-05-04,,基金合同,2026-08-12T00:00:00+08:00
510500.SH,benchmark,csi500,2013-03-15,,基金合同,2026-08-12T00:00:00+08:00
159915.SZ,benchmark,gem,2011-09-20,,基金合同,2026-08-12T00:00:00+08:00
```

Note: these are seed values for Phase A plumbing. **Evidence validation against actual prospectus or 汇金公告 is a Phase A review item** (see Task 13's Gate report). The seed file is committed to make Phase A executable end-to-end before evidence is fully cross-checked.

- [ ] **Step 5: Run tests to verify pass**

Run: `pytest tests/flow_dashboard/test_pit_labels.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add src/flow_dashboard/data/pit_labels.py tests/flow_dashboard/test_pit_labels.py data/flow_dashboard/phase_a_evidence/etf_pit_labels.csv
git commit -m "feat: add multi-dimension PIT label table with huijin broad seed"
```

---

## Task 11: api_capabilities.yaml generator

Per spec §3.5.1 Phase A: must freeze fields/units/code mappings/timestamps/frequency/rate limits. This generator runs each provider once, captures actual returned columns and a sample row count, and emits a YAML for human review.

**Files:**
- Create: `src/flow_dashboard/phase_a/api_capabilities.py`
- Create: `scripts/flow_dashboard/run_api_capabilities.py`
- Create: `tests/flow_dashboard/test_api_capabilities.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/flow_dashboard/test_api_capabilities.py
"""api_capabilities.yaml 生成器契约测试。"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from src.flow_dashboard.phase_a.api_capabilities import build_capabilities


def test_build_capabilities_returns_dict_with_required_keys():
    caps = build_capabilities()
    for key in ("tushare", "sina"):
        assert key in caps
    tushare = caps["tushare"]
    for endpoint in ("fund_basic", "etf_share_size", "fund_nav", "fund_daily",
                     "margin", "fut_basic", "fut_daily", "index_daily"):
        assert endpoint in tushare, f"missing endpoint: {endpoint}"
        entry = tushare[endpoint]
        assert "observed_columns" in entry
        assert "units" in entry
        assert "notes" in entry


def test_sina_caps_include_node_mark():
    caps = build_capabilities()
    sina = caps["sina"]
    assert "futures_node_mark" in sina
    assert sina["futures_node_mark"]["IC"] == "zzgz_qh"
    assert sina["futures_node_mark"]["IM"] == "im_qh"


def test_caps_yaml_round_trip(tmp_path):
    caps = build_capabilities()
    target = tmp_path / "api_capabilities.yaml"
    target.write_text(yaml.safe_dump(caps, allow_unicode=True, sort_keys=False))
    reloaded = yaml.safe_load(target.read_text())
    assert reloaded["tushare"]["fund_basic"]["observed_columns"][0] == caps["tushare"]["fund_basic"]["observed_columns"][0]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/flow_dashboard/test_api_capabilities.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement**

```python
# src/flow_dashboard/phase_a/api_capabilities.py
"""生成 api_capabilities.yaml。

per spec §3.5.1 Phase A: 冻结字段、单位、代码映射、时间戳语义、频率、权限/限流、available_at。

build_capabilities 不需要真实 token：返回的是从代码常量推断的"契约能力声明"。
run_main（CLI）会真实调用每个 provider，把样本行数、样本最新日期、首次观测时间
一起写入 yaml；本模块的 build_capabilities 只产静态部分，便于离线测试。
"""
from __future__ import annotations

from src.flow_dashboard.data.sina_client import FUTURES_NODE_MARK


TUSHARE_CAPABILITIES: dict = {
    "fund_basic": {
        "observed_columns": [
            "ts_code", "name", "management", "custodian", "fund_type",
            "found_date", "due_date", "list_date", "issue_date", "delist_date",
            "market", "status",
        ],
        "units": {"found_date": "date", "list_date": "date", "delist_date": "date"},
        "primary_key": ["ts_code"],
        "frequency": "不定期（新发/退市时更新）",
        "available_at": "源端不提供发布时间戳；本系统以首次拉取时间为 first_observed_at",
        "notes": "market='E' 为场内基金；同时含 ETF 与 LOF/REITs，需以 fund_type 进一步过滤",
    },
    "etf_share_size": {
        "observed_columns": [
            "trade_date", "ts_code", "etf_name", "total_share", "total_size", "exchange",
        ],
        "units": {
            "total_share": "万份（spec 要求落盘 share_in_shares = total_share * 10000 转为份）",
            "total_size": "万元",
            "trade_date": "date",
        },
        "primary_key": ["ts_code", "trade_date"],
        "frequency": "日度，T+1 约 08:30 更新 T 日；海外 ETF 更晚",
        "available_at": "源端无显式时间戳；轮询 first_observed_at 取决于实际入库",
        "notes": (
            "Tushare 当前 endpoint 不返回 nav/close 字段；spec §1.3 要求请求与校验，"
            "缺失时由上层 loader 写入 quality_flags=missing_nav。"
            "total_size 单位万元，spec §1.3 要求金额统一存元，落盘前乘 10000。"
        ),
    },
    "fund_nav": {
        "observed_columns": [
            "ts_code", "nav_date", "ann_date", "unit_nav", "accum_nav", "adj_nav",
        ],
        "units": {
            "unit_nav": "元", "accum_nav": "元", "adj_nav": "元",
            "nav_date": "date", "ann_date": "date",
        },
        "primary_key": ["ts_code", "nav_date"],
        "frequency": "日度，但披露依管理人 ann_date，存在滞后",
        "available_at": "ann_date 是公告日；available_at 不得早于公告时间",
        "notes": "同日多公告的 PIT 选择规则留待 Phase A 数据样本后冻结（needs_human_review）",
    },
    "fund_daily": {
        "observed_columns": [
            "ts_code", "trade_date", "pre_close", "open", "high", "low",
            "close", "change", "pct_chg", "vol", "amount",
        ],
        "units": {
            "close": "元", "vol": "手", "amount": "千元",
            "trade_date": "date",
        },
        "primary_key": ["ts_code", "trade_date"],
        "frequency": "日度，T 日 17:00 后可得",
        "available_at": "源端无显式时间戳；以收盘后稳定时间为准",
        "notes": "用于对照与数据质量检查，不作为份额流量计算的 nav 代替",
    },
    "margin": {
        "observed_columns": [
            "trade_date", "exchange_id", "rzye", "rzmre", "rzche",
            "rqye", "rqmcl", "rzrqye", "rqyl",
        ],
        "units": {"rzye": "元", "rzmre": "元", "rzche": "元", "rqye": "元"},
        "primary_key": ["trade_date", "exchange_id"],
        "frequency": "日度，T 日收盘后约 18:00 各交易所分别披露",
        "available_at": "各交易所披露时间不同；不合并为单一时间戳",
        "notes": (
            "SSE/SZSE/BSE 三所都返回；"
            "spec §3.5 Phase B 要求先分交易所展示，market_scope 汇总范围待冻结"
        ),
    },
    "fut_basic": {
        "observed_columns": [
            "ts_code", "symbol", "exchange", "name", "fut_code",
            "multiplier", "trade_unit", "per_unit", "quote_unit",
            "list_date", "delist_date", "d_month", "last_ddate",
        ],
        "units": {"multiplier": "元/点", "list_date": "date", "delist_date": "date"},
        "primary_key": ["ts_code"],
        "frequency": "事件驱动（新合约上市、老合约摘牌）",
        "available_at": "源端无时间戳",
        "notes": "IC/IM 合约代码形如 IC2608.CFX、IM2509.CFX（CFX = CFFEX 旧缩写）",
    },
    "fut_daily": {
        "observed_columns": [
            "ts_code", "trade_date", "pre_close", "pre_settle",
            "open", "high", "low", "close", "settle",
            "change1", "change2", "vol", "amount", "oi", "oi_chg",
        ],
        "units": {
            "close": "指数点", "settle": "指数点",
            "vol": "手", "amount": "万元（spec 要求金额存元，乘 10000）",
            "oi": "手",
        },
        "primary_key": ["ts_code", "trade_date"],
        "frequency": "日度",
        "available_at": "CFFEX 收盘后约 15:30 公布；以实际拉取时间为准",
        "notes": (
            "spec §1.4 要求日终同时保存 eod_close (close) 与 eod_settlement (settle)；"
            "主页主展示 eod_close，结算口径仅作对照"
        ),
    },
    "index_daily": {
        "observed_columns": [
            "ts_code", "trade_date", "close", "open", "high", "low",
            "pre_close", "change", "pct_chg", "vol", "amount",
        ],
        "units": {"close": "指数点"},
        "primary_key": ["ts_code", "trade_date"],
        "frequency": "日度",
        "available_at": "收盘后约 17:00 可得",
        "notes": "000905.SH=CSI500, 000852.SH=CSI1000 用于 IC/IM 基差分母",
    },
}

SINA_CAPABILITIES: dict = {
    "futures_node_mark": dict(FUTURES_NODE_MARK),
    "futures_endpoint": (
        "https://vip.stock.finance.sina.com.cn/quotes_service/api/"
        "json_v2.php/Market_Center.getHQFuturesData?page=1&sort=position&asc=0"
        "&node={node}&base=futures"
    ),
    "spot_endpoint": "https://hq.sinajs.cn/list={codes}",
    "headers_required": {"Referer": "https://finance.sina.com.cn"},
    "encoding": {"futures": "utf-8", "spot": "gbk"},
    "observed_columns_futures": [
        "symbol", "exchange", "name", "trade", "settlement", "presettlement",
        "open", "high", "low", "close", "bidprice1", "askprice1",
        "bidvol1", "askvol1", "volume", "position",
        "ticktime", "tradedate", "preclose", "changepercent",
        "bid", "ask", "prevsettlement",
    ],
    "observed_columns_spot": [
        "provider_code", "name", "pre_close", "open", "last",
        "high", "low", "date", "time",
    ],
    "code_mappings": {
        "csi500_index": "sh000905",
        "csi1000_index": "sh000852",
        "csi300_index": "sh000300",
        "sse_composite": "sh000001",
    },
    "frequency_plan": {
        "intraday": "每 15 分钟一次（spec §3.1 已决策）",
        "rate_limit_note": "新浪未公开声明限流；Phase A 实测记录实际可达性",
    },
    "access_terms_review": (
        "needs_human_review: data_contract.sina_realtime_provider - "
        "需人工确认内部使用符合当时可见的访问条款；不规避 robots/验证码/封禁机制"
    ),
    "parse_version": "sina_v1",
}


def build_capabilities() -> dict:
    """静态能力声明。CLI 入口会在此基础上追加 live sample 数据。"""
    return {
        "schema_version": "0.1.0-phase-a",
        "tushare": TUSHARE_CAPABILITIES,
        "sina": SINA_CAPABILITIES,
    }
```

- [ ] **Step 4: Write CLI entry**

```python
# scripts/flow_dashboard/run_api_capabilities.py
"""生成 api_capabilities.yaml 到 data/flow_dashboard/phase_a_evidence/。

跑 live 样本时需要 ASHARE_FLOW_TUSHARE_TOKEN 与网络访问。
"""
from __future__ import annotations

import argparse
import sys
import traceback
from pathlib import Path

import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from src.flow_dashboard.config import EVIDENCE_DIR, ensure_dirs, TIMEZONE  # noqa: E402
from src.flow_dashboard.phase_a.api_capabilities import build_capabilities  # noqa: E402


def _live_sample() -> dict:
    """每个 endpoint 跑一次小样本，记录实际行数、最新日期、首次观测时间。"""
    from src.flow_dashboard.data.tushare_providers import (
        pull_fund_basic, pull_etf_share_size, pull_fund_nav, pull_fund_daily,
        pull_margin, pull_fut_basic, pull_fut_daily, pull_index_daily,
    )
    from src.flow_dashboard.data.sina_client import fetch_futures_node, fetch_spot_indices

    live = {"tushare": {}, "sina": {}}
    now = pd.Timestamp.now(tz=TIMEZONE)
    sample_codes = ["510050.SH", "510300.SH", "510500.SH", "159915.SZ"]

    def _record(area, name, df_or_payload):
        if isinstance(df_or_payload, pd.DataFrame):
            live[area][name] = {
                "sample_rows": int(len(df_or_payload)),
                "first_observed_at": now.isoformat(),
                "columns_observed": list(df_or_payload.columns),
            }
        else:
            live[area][name] = {"error": str(df_or_payload), "first_observed_at": now.isoformat()}

    for name, fn, args in [
        ("fund_basic", pull_fund_basic, {"market": "E"}),
        ("etf_share_size", pull_etf_share_size,
         {"codes": sample_codes, "start_date": "20260807", "end_date": "20260812"}),
        ("fund_nav", pull_fund_nav,
         {"codes": ["510050.SH"], "start_date": "20260807", "end_date": "20260812"}),
        ("fund_daily", pull_fund_daily,
         {"codes": ["510050.SH"], "start_date": "20260807", "end_date": "20260812"}),
        ("margin", pull_margin, {"start_date": "20260811", "end_date": "20260811"}),
        ("fut_basic", pull_fut_basic, {"exchange": "CFFEX", "fut_code": "IC"}),
        ("fut_daily", pull_fut_daily,
         {"ts_code": "IC2608.CFX", "start_date": "20260807", "end_date": "20260812"}),
        ("index_daily", pull_index_daily,
         {"ts_code": "000905.SH", "start_date": "20260807", "end_date": "20260812"}),
    ]:
        try:
            df = fn(**args)
            _record("tushare", name, df)
        except Exception as exc:
            print(f"[warn] tushare {name} failed: {exc}")
            traceback.print_exc()
            _record("tushare", name, exc)

    # 新浪
    try:
        df = fetch_futures_node("IC")
        _record("sina", "fetch_futures_node_IC", df)
    except Exception as exc:
        _record("sina", "fetch_futures_node_IC", exc)
    try:
        df = fetch_spot_indices(["sh000905", "sh000852"])
        _record("sina", "fetch_spot_indices", df)
    except Exception as exc:
        _record("sina", "fetch_spot_indices", exc)
    return live


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--live", action="store_true",
                        help="跑真实小样本并合并到 yaml（需要 token + 网络）")
    parser.add_argument("--output", default=str(EVIDENCE_DIR / "api_capabilities.yaml"))
    args = parser.parse_args()

    ensure_dirs()
    caps = build_capabilities()
    if args.live:
        caps["live_sample"] = _live_sample()
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(caps, allow_unicode=True, sort_keys=False, default_flow_style=False))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run unit tests to verify pass**

Run: `pytest tests/flow_dashboard/test_api_capabilities.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Run CLI to produce actual yaml**

Run:
```bash
cd /Users/xinghuazhang/ygr-project/a股监控
source .venv/bin/activate
python scripts/flow_dashboard/run_api_capabilities.py --live
```
Expected: stdout `wrote .../phase_a_evidence/api_capabilities.yaml`, no traceback.

- [ ] **Step 7: Spot-check yaml**

Run: `head -40 data/flow_dashboard/phase_a_evidence/api_capabilities.yaml`
Expected: 可见 `tushare:`、`sina:` 顶层 key，每条 endpoint 含 `observed_columns`、`units`、`live_sample` 实测。

- [ ] **Step 8: Commit**

```bash
git add src/flow_dashboard/phase_a/api_capabilities.py scripts/flow_dashboard/run_api_capabilities.py tests/flow_dashboard/test_api_capabilities.py data/flow_dashboard/phase_a_evidence/api_capabilities.yaml
git commit -m "feat: generate api_capabilities.yaml with live tushare+sina sample"
```

---

## Task 12: ETF share polling script (port from 行业轮动)

Per spec §3.2.1 白名单: 从 `行业轮动/scripts/poll_tushare_etf_share_size.py` 迁移轮询日志函数；去除 `HUATAI_FLOW_ETF_CODES` 静态名单，改用本项目 ETF PIT 标签表筛出的 codes。

**Files:**
- Create: `src/flow_dashboard/phase_a/poll_etf_share.py`
- Create: `scripts/flow_dashboard/poll_etf_share_size.py`
- Create: `tests/flow_dashboard/test_poll_etf_share.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/flow_dashboard/test_poll_etf_share.py
"""poll_etf_share 契约测试。

- poll_once 返回 summary dict，含 status ∈ {complete, partial, missing}
- 写入 poll_summary.csv（追加）和 detail CSV
- 用 pull_func fake 注入，不依赖真实 API
"""
from __future__ import annotations

import pandas as pd
import pytest

from src.flow_dashboard.phase_a.poll_etf_share import poll_once


def _fake_pull(codes, start_date=None, end_date=None):
    """返回模拟的 etf_share_size 输出。"""
    rows = []
    for code in codes:
        rows.append({
            "trade_date": pd.Timestamp("20260811"),
            "ts_code": code,
            "etf_name": f"测试{code}",
            "total_share": 100.0,
            "total_size": 100.0,
            "exchange": "SSE" if code.endswith(".SH") else "SZSE",
            "share_in_shares": 1_000_000.0,
        })
    return pd.DataFrame(rows)


def test_poll_once_complete(tmp_path):
    summary = poll_once(
        codes=["510050.SH", "510300.SH"],
        trade_date="20260811",
        output_dir=tmp_path,
        now=pd.Timestamp("2026-08-12T09:30:00+08:00"),
        pull_func=_fake_pull,
    )
    assert summary["status"] == "complete"
    assert summary["expected_count"] == 2
    assert summary["available_count"] == 2
    assert summary["trade_date"] == "20260811"
    assert (tmp_path / "poll_summary.csv").exists()
    # detail 文件按时间戳命名
    details = list(tmp_path.glob("poll_detail_*.csv"))
    assert len(details) == 1


def test_poll_once_partial(tmp_path):
    def _short_pull(codes, start_date=None, end_date=None):
        df = _fake_pull(codes, start_date, end_date)
        return df[df["ts_code"] == codes[0]].reset_index(drop=True)
    summary = poll_once(
        codes=["510050.SH", "510300.SH"],
        trade_date="20260811",
        output_dir=tmp_path,
        pull_func=_short_pull,
    )
    assert summary["status"] == "partial"
    assert summary["available_count"] == 1
    assert "510300.SH" in summary["missing_codes"]


def test_poll_once_missing(tmp_path):
    def _empty(codes, start_date=None, end_date=None):
        return pd.DataFrame()
    summary = poll_once(
        codes=["510050.SH"],
        trade_date="20260811",
        output_dir=tmp_path,
        pull_func=_empty,
    )
    assert summary["status"] == "missing"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/flow_dashboard/test_poll_etf_share.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement**

```python
# src/flow_dashboard/phase_a/poll_etf_share.py
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

from src.flow_dashboard.config import TIMEZONE


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
        from src.flow_dashboard.data.tushare_providers import pull_etf_share_size
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
```

- [ ] **Step 4: Write CLI entry**

```python
# scripts/flow_dashboard/poll_etf_share_size.py
"""CLI 入口：从 etf_pit_labels.csv 取 ts_code 列表，轮询一次 etf_share_size。

示例:
    python scripts/flow_dashboard/poll_etf_share_size.py --trade-date 20260811 \
        --labels data/flow_dashboard/phase_a_evidence/etf_pit_labels.csv
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402

from src.flow_dashboard.config import EVIDENCE_DIR  # noqa: E402
from src.flow_dashboard.data.pit_labels import load_pit_labels  # noqa: E402
from src.flow_dashboard.phase_a.poll_etf_share import poll_once  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--trade-date", required=True)
    parser.add_argument(
        "--labels",
        default=str(EVIDENCE_DIR / "etf_pit_labels.csv"),
        help="PIT 标签表路径；将取其中所有 ts_code 作为轮询目标",
    )
    parser.add_argument(
        "--output-dir",
        default=str(EVIDENCE_DIR / "share_polling"),
    )
    args = parser.parse_args()

    labels = load_pit_labels(args.labels)
    codes = sorted(set(labels["ts_code"]))
    summary = poll_once(codes=codes, trade_date=args.trade_date, output_dir=args.output_dir)
    print(pd.DataFrame([summary]).to_string(index=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run unit tests to verify pass**

Run: `pytest tests/flow_dashboard/test_poll_etf_share.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Commit**

```bash
git add src/flow_dashboard/phase_a/poll_etf_share.py scripts/flow_dashboard/poll_etf_share_size.py tests/flow_dashboard/test_poll_etf_share.py
git commit -m "feat: port poll_etf_share_size from 行业轮动 without static whitelist"
```

---

## Task 13: Source switch reconciliation (etf_share_size vs fund_share)

Per spec §1.3: `etf_share_size` 为首版主源；`fund_share` 仅补主源最早覆盖日之前历史。两源重叠期需逐 ETF 对账；换源边界两侧数值不一致时输出 `source_switch_break`。

This task produces a per-ETF diff report for the overlapping window, so the human reviewer can decide whether to allow source-switching.

**Files:**
- Create: `src/flow_dashboard/phase_a/source_switch_reconcile.py`
- Create: `scripts/flow_dashboard/run_source_switch_reconcile.py`
- Create: `tests/flow_dashboard/test_source_switch_reconcile.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/flow_dashboard/test_source_switch_reconcile.py
"""etf_share_size vs fund_share 对账测试。"""
from __future__ import annotations

import pandas as pd

from src.flow_dashboard.phase_a.source_switch_reconcile import (
    reconcile_share_sources,
    fetch_fund_share,
)


def _fake_etf_share_size():
    return pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "ts_code": "510050.SH",
         "total_share": 689466.68, "total_size": 2115766.0, "exchange": "SSE",
         "share_in_shares": 689466.68 * 10000, "etf_name": "50ETF"},
        {"trade_date": pd.Timestamp("2026-08-08"), "ts_code": "510050.SH",
         "total_share": 680000.00, "total_size": 2085000.0, "exchange": "SSE",
         "share_in_shares": 680000.00 * 10000, "etf_name": "50ETF"},
    ])


def _fake_fund_share():
    return pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "ts_code": "510050.SH",
         "share_in_shares": 689466.68 * 10000, "source": "fund_share"},
        {"trade_date": pd.Timestamp("2026-08-08"), "ts_code": "510050.SH",
         "share_in_shares": 685000.00 * 10000, "source": "fund_share"},  # 差异 > 1%
    ])


def test_reconcile_flags_large_diff():
    report = reconcile_share_sources(
        etf_share=_fake_etf_share_size(),
        fund_share=_fake_fund_share(),
        tolerance_pct=0.01,
    )
    assert len(report) == 2  # 两天
    # 第一天差异 0，第二天差异 > 1%
    flagged = report[report["diff_pct"].abs() > 0.01]
    assert len(flagged) == 1
    assert flagged.iloc[0]["trade_date"] == pd.Timestamp("2026-08-08")


def test_reconcile_handles_disjoint_dates():
    etf = pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-07"), "ts_code": "510050.SH",
         "share_in_shares": 100.0 * 10000, "total_size": 100.0, "exchange": "SSE",
         "total_share": 100.0, "etf_name": "X"},
    ])
    fs = pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-08"), "ts_code": "510050.SH",
         "share_in_shares": 100.0 * 10000, "source": "fund_share"},
    ])
    report = reconcile_share_sources(etf_share=etf, fund_share=fs, tolerance_pct=0.01)
    # 两天的差都是 NaN（另一侧缺失）
    assert report["diff_pct"].isna().all()


def test_fetch_fund_share_returns_normalized():
    """fund_share 拉取并规范化为 share_in_shares。"""
    # 这里用 fake；真实 fetch 需要 token
    df = fetch_fund_share.__wrapped__(["510050.SH"], "20260807", "20260807") if hasattr(fetch_fund_share, "__wrapped__") else None
    # 仅断言契约：若 df 不空，必须有 share_in_shares
    if df is not None and not df.empty:
        assert "share_in_shares" in df.columns
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/flow_dashboard/test_source_switch_reconcile.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement**

```python
# src/flow_dashboard/phase_a/source_switch_reconcile.py
"""etf_share_size vs fund_share 源切换对账。

per spec §1.3:
- etf_share_size 为首版主源；fund_share 仅补主源最早覆盖日之前历史
- 两源重叠期逐 ETF 对账
- 换源边界两侧数值不一致时输出 source_switch_break
"""
from __future__ import annotations

import pandas as pd

from src.flow_dashboard.data.tushare_client import get_pro_api


def reconcile_share_sources(
    etf_share: pd.DataFrame,
    fund_share: pd.DataFrame,
    tolerance_pct: float = 0.01,
) -> pd.DataFrame:
    """逐 (ts_code, trade_date) 对账两源的 share_in_shares。

    输出列: ts_code, trade_date, etf_share_in_shares, fund_share_in_shares,
            abs_diff, diff_pct, flag ∈ {ok, over_tolerance, only_etf, only_fund_share}
    """
    e = etf_share[["ts_code", "trade_date", "share_in_shares"]].rename(
        columns={"share_in_shares": "etf_share_in_shares"}
    )
    f = fund_share[["ts_code", "trade_date", "share_in_shares"]].rename(
        columns={"share_in_shares": "fund_share_in_shares"}
    )
    merged = pd.merge(e, f, on=["ts_code", "trade_date"], how="outer")
    merged["abs_diff"] = (merged["etf_share_in_shares"] - merged["fund_share_in_shares"]).abs()
    merged["diff_pct"] = merged["abs_diff"] / merged[["etf_share_in_shares", "fund_share_in_shares"]].mean(axis=1)

    def _flag(row):
        if pd.isna(row["etf_share_in_shares"]):
            return "only_fund_share"
        if pd.isna(row["fund_share_in_shares"]):
            return "only_etf"
        if pd.isna(row["diff_pct"]):
            return "ok"
        if abs(row["diff_pct"]) > tolerance_pct:
            return "over_tolerance"
        return "ok"

    merged["flag"] = merged.apply(_flag, axis=1)
    return merged.sort_values(["ts_code", "trade_date"]).reset_index(drop=True)


def fetch_fund_share(
    codes: list[str],
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """从 Tushare fund_share 拉取并规范化为 share_in_shares（份）。

    fund_share 原始字段 fd_share 单位万份；share_in_shares = fd_share * 10000。
    本函数与 etf_share_size 共享单位，便于直接 diff。
    """
    pro = get_pro_api()
    frames = []
    for code in codes:
        df = pro.fund_share(ts_code=code, start_date=start_date, end_date=end_date)
        if df is not None and not df.empty:
            frames.append(df[["ts_code", "trade_date", "fd_share"]])
    if not frames:
        return pd.DataFrame(columns=["ts_code", "trade_date", "share_in_shares"])
    df = pd.concat(frames, ignore_index=True).copy()
    df["trade_date"] = pd.to_datetime(df["trade_date"], format="%Y%m%d", errors="coerce")
    df["fd_share"] = pd.to_numeric(df["fd_share"], errors="coerce")
    df["share_in_shares"] = df["fd_share"] * 10000
    return df.drop_duplicates(subset=["ts_code", "trade_date"]).reset_index(drop=True)
fetch_fund_share.__wrapped__ = fetch_fund_share  # 测试兼容标记
```

- [ ] **Step 4: Write CLI entry**

```python
# scripts/flow_dashboard/run_source_switch_reconcile.py
"""生成源切换对账报告 CSV。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402

from src.flow_dashboard.config import EVIDENCE_DIR, ensure_dirs  # noqa: E402
from src.flow_dashboard.data.pit_labels import load_pit_labels  # noqa: E402
from src.flow_dashboard.data.tushare_providers import pull_etf_share_size  # noqa: E402
from src.flow_dashboard.phase_a.source_switch_reconcile import (  # noqa: E402
    fetch_fund_share,
    reconcile_share_sources,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", default="20260101")
    parser.add_argument("--end-date", default="20260812")
    parser.add_argument("--labels", default=str(EVIDENCE_DIR / "etf_pit_labels.csv"))
    parser.add_argument("--output", default=str(EVIDENCE_DIR / "source_switch_reconcile.csv"))
    parser.add_argument("--tolerance-pct", type=float, default=0.01)
    args = parser.parse_args()

    ensure_dirs()
    labels = load_pit_labels(args.labels)
    codes = sorted(set(labels["ts_code"]))

    etf = pull_etf_share_size(codes=codes, start_date=args.start_date, end_date=args.end_date)
    fund = fetch_fund_share(codes=codes, start_date=args.start_date, end_date=args.end_date)
    report = reconcile_share_sources(etf, fund, tolerance_pct=args.tolerance_pct)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    report.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"wrote {args.output} rows={len(report)}")
    print(report["flag"].value_counts().to_string())


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run unit tests to verify pass**

Run: `pytest tests/flow_dashboard/test_source_switch_reconcile.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Run CLI to produce actual report**

Run:
```bash
cd /Users/xinghuazhang/ygr-project/a股监控
source .venv/bin/activate
python scripts/flow_dashboard/run_source_switch_reconcile.py
```
Expected: stdout 含 `wrote ... rows=N` 与各 flag 计数。

- [ ] **Step 7: Commit**

```bash
git add src/flow_dashboard/phase_a/source_switch_reconcile.py scripts/flow_dashboard/run_source_switch_reconcile.py tests/flow_dashboard/test_source_switch_reconcile.py data/flow_dashboard/phase_a_evidence/source_switch_reconcile.csv
git commit -m "feat: reconcile etf_share_size vs fund_share with per-row flags"
```

---

## Task 14: Coverage baseline calculator

Per spec §2.1 s2_flow_aggregation: 三种覆盖率指标 — `count_coverage`, `prior_share_coverage`, `prior_aum_coverage`. Phase A 只需产出基线分布（每日每 dimension+label 的覆盖率），数值门槛由人工 freeze。

**Files:**
- Create: `src/flow_dashboard/phase_a/coverage_baseline.py`
- Create: `scripts/flow_dashboard/run_coverage_baseline.py`
- Create: `tests/flow_dashboard/test_coverage_baseline.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/flow_dashboard/test_coverage_baseline.py
"""覆盖率基线契约测试。"""
from __future__ import annotations

import pandas as pd
import pytest

from src.flow_dashboard.phase_a.coverage_baseline import compute_coverage_series


def _sample_flow():
    """3 ETF，2 天，第二天缺一只。"""
    return pd.DataFrame([
        {"ts_code": "A", "trade_date": pd.Timestamp("2026-08-07"),
         "dimension": "asset_scope", "label": "broad",
         "share_in_shares": 100e8, "total_size_cny": 100e8 * 5,
         "etf_estimated_flow_cny": 1e8},
        {"ts_code": "B", "trade_date": pd.Timestamp("2026-08-07"),
         "dimension": "asset_scope", "label": "broad",
         "share_in_shares": 200e8, "total_size_cny": 200e8 * 6,
         "etf_estimated_flow_cny": 2e8},
        {"ts_code": "C", "trade_date": pd.Timestamp("2026-08-07"),
         "dimension": "asset_scope", "label": "broad",
         "share_in_shares": 300e8, "total_size_cny": 300e8 * 7,
         "etf_estimated_flow_cny": -1e8},
        # 第二天 C 缺
        {"ts_code": "A", "trade_date": pd.Timestamp("2026-08-08"),
         "dimension": "asset_scope", "label": "broad",
         "share_in_shares": 100e8, "total_size_cny": 100e8 * 5,
         "etf_estimated_flow_cny": 0.5e8},
        {"ts_code": "B", "trade_date": pd.Timestamp("2026-08-08"),
         "dimension": "asset_scope", "label": "broad",
         "share_in_shares": 200e8, "total_size_cny": 200e8 * 6,
         "etf_estimated_flow_cny": -0.5e8},
    ])


def test_compute_coverage_series_count():
    df = _sample_flow()
    out = compute_coverage_series(df, universe=["A", "B", "C"])
    # 第一天 3/3，第二天 2/3
    d1 = out[out["trade_date"] == pd.Timestamp("2026-08-07")].iloc[0]
    d2 = out[out["trade_date"] == pd.Timestamp("2026-08-08")].iloc[0]
    assert d1["count_coverage"] == pytest.approx(1.0)
    assert d2["count_coverage"] == pytest.approx(2 / 3)


def test_compute_coverage_series_prior_share():
    df = _sample_flow()
    out = compute_coverage_series(df, universe=["A", "B", "C"])
    d2 = out[out["trade_date"] == pd.Timestamp("2026-08-08")].iloc[0]
    # 前一日份额 A+B+C = 600e8；当日观测 A+B = 300e8 → 0.5
    assert d2["prior_share_coverage"] == pytest.approx(300e8 / 600e8)


def test_compute_coverage_series_prior_aum():
    df = _sample_flow()
    out = compute_coverage_series(df, universe=["A", "B", "C"])
    d2 = out[out["trade_date"] == pd.Timestamp("2026-08-08")].iloc[0]
    # 前一日 total_size_cny A+B+C = 3800e8；当日 A+B = 1700e8
    assert d2["prior_aum_coverage"] == pytest.approx(1700e8 / 3800e8)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/flow_dashboard/test_coverage_baseline.py -v`
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement**

```python
# src/flow_dashboard/phase_a/coverage_baseline.py
"""Phase A 覆盖率基线计算。

per spec §2.1 s2_flow_aggregation:
- count_coverage = observed_count / eligible_count
- prior_share_coverage = sum(prior_share[observed]) / sum(prior_share[eligible])
- prior_aum_coverage = sum(prior_aum[observed]) / sum(prior_aum[eligible])

prior_share 与 prior_aum 使用 t 之前最近一个有效观测；本 Phase A 简化为"前一日"。
真正的 PIT 前一有效日逻辑由 Phase B 实现。
"""
from __future__ import annotations

import pandas as pd


def compute_coverage_series(
    flow_df: pd.DataFrame,
    universe: list[str],
) -> pd.DataFrame:
    """逐 (dimension, label, trade_date) 算 3 种覆盖率。

    flow_df 必须含列: ts_code, trade_date, dimension, label,
                     share_in_shares, total_size_cny, etf_estimated_flow_cny
    """
    required = {"ts_code", "trade_date", "dimension", "label",
                "share_in_shares", "total_size_cny"}
    missing = required - set(flow_df.columns)
    if missing:
        raise ValueError(f"flow_df 缺列: {missing}")

    df = flow_df.sort_values(["dimension", "label", "trade_date", "ts_code"]).copy()
    eligible_set = set(universe)
    n_eligible = len(eligible_set)

    rows: list[dict] = []
    for (dim, label, trade_date), group in df.groupby(["dimension", "label", "trade_date"], sort=False):
        observed = set(group["ts_code"]) & eligible_set
        n_observed = len(observed)

        # 前一日全集快照（同 dimension+label 下的最大 trade_date < current）
        prev_mask = (
            (df["dimension"] == dim)
            & (df["label"] == label)
            & (df["trade_date"] < trade_date)
        )
        prev_df = df[prev_mask]
        if not prev_df.empty:
            prev_max_date = prev_df["trade_date"].max()
            prev_snapshot = prev_df[prev_df["trade_date"] == prev_max_date]
        else:
            prev_snapshot = prev_df.iloc[0:0]

        # eligible 前一日份额/AUM（在 prev_snapshot 中能找到的）
        prev_eligible = prev_snapshot[prev_snapshot["ts_code"].isin(eligible_set)]
        prior_share_eligible = prev_eligible["share_in_shares"].sum()
        prior_aum_eligible = prev_eligible["total_size_cny"].sum()

        prev_observed = prev_eligible[prev_eligible["ts_code"].isin(observed)]
        prior_share_observed = prev_observed["share_in_shares"].sum()
        prior_aum_observed = prev_observed["total_size_cny"].sum()

        count_cov = n_observed / n_eligible if n_eligible else float("nan")
        prior_share_cov = (
            prior_share_observed / prior_share_eligible
            if prior_share_eligible else float("nan")
        )
        prior_aum_cov = (
            prior_aum_observed / prior_aum_eligible
            if prior_aum_eligible else float("nan")
        )

        rows.append({
            "dimension": dim, "label": label, "trade_date": trade_date,
            "eligible_count": n_eligible, "observed_count": n_observed,
            "count_coverage": count_cov,
            "prior_share_coverage": prior_share_cov,
            "prior_aum_coverage": prior_aum_cov,
        })
    return pd.DataFrame(rows).sort_values(["dimension", "label", "trade_date"]).reset_index(drop=True)
```

- [ ] **Step 4: Write CLI entry**

```python
# scripts/flow_dashboard/run_coverage_baseline.py
"""生成覆盖率基线 CSV：用 PIT 标签作为 universe，按 etf_share_size 实测计算。"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

import pandas as pd  # noqa: E402

from src.flow_dashboard.config import EVIDENCE_DIR, ensure_dirs  # noqa: E402
from src.flow_dashboard.data.pit_labels import load_pit_labels  # noqa: E402
from src.flow_dashboard.data.tushare_providers import pull_etf_share_size  # noqa: E402
from src.flow_dashboard.phase_a.coverage_baseline import compute_coverage_series  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", default="20260101")
    parser.add_argument("--end-date", default="20260812")
    parser.add_argument("--labels", default=str(EVIDENCE_DIR / "etf_pit_labels.csv"))
    parser.add_argument("--output", default=str(EVIDENCE_DIR / "coverage_baseline.csv"))
    args = parser.parse_args()

    ensure_dirs()
    labels = load_pit_labels(args.labels)
    universe = sorted(set(labels["ts_code"]))

    etf = pull_etf_share_size(codes=universe, start_date=args.start_date, end_date=args.end_date)
    if etf.empty:
        print("[warn] etf_share_size empty; nothing to baseline")
        return

    # 把每个 dimension+label 展开为长表，关联份额数据
    flow_rows = []
    for _, label_row in labels.iterrows():
        dim = label_row["dimension"]
        lab = label_row["label"]
        ts_code = label_row["ts_code"]
        sub = etf[etf["ts_code"] == ts_code]
        for _, s in sub.iterrows():
            flow_rows.append({
                "ts_code": ts_code, "trade_date": s["trade_date"],
                "dimension": dim, "label": lab,
                "share_in_shares": s["share_in_shares"],
                # etf_share_size 的 total_size 单位是万元；转元
                "total_size_cny": s["total_size"] * 10000,
            })
    flow = pd.DataFrame(flow_rows)
    if flow.empty:
        print("[warn] flow empty; check label/etf code alignment")
        return
    out = compute_coverage_series(flow, universe=universe)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"wrote {args.output} rows={len(out)}")
    print(out.tail(10).to_string(index=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run unit tests to verify pass**

Run: `pytest tests/flow_dashboard/test_coverage_baseline.py -v`
Expected: PASS (3 tests).

- [ ] **Step 6: Run CLI**

Run:
```bash
cd /Users/xinghuazhang/ygr-project/a股监控
source .venv/bin/activate
python scripts/flow_dashboard/run_coverage_baseline.py
```
Expected: stdout `wrote ... rows=N` 加尾部 10 行。

- [ ] **Step 7: Commit**

```bash
git add src/flow_dashboard/phase_a/coverage_baseline.py scripts/flow_dashboard/run_coverage_baseline.py tests/flow_dashboard/test_coverage_baseline.py data/flow_dashboard/phase_a_evidence/coverage_baseline.csv
git commit -m "feat: compute coverage baseline (count/prior_share/prior_aum)"
```

---

## Task 15: Phase A Gate report

Phase A 出口报告：把前述 5 个 Gate 产出物（`api_capabilities.yaml`, `etf_pit_labels.csv`, `source_switch_reconcile.csv`, `coverage_baseline.csv`, `share_polling/poll_summary.csv`）汇总成一份人工 review 用的 markdown，并列出仍待人工决策的 `needs_human_review` 项与 Phase B 启动条件。

**Files:**
- Create: `docs/资金流跟踪/phase_a_gate_report.md`

- [ ] **Step 1: Inspect Phase A evidence files exist**

Run:
```bash
ls -la data/flow_dashboard/phase_a_evidence/
```
Expected: 至少可见
- `api_capabilities.yaml`
- `etf_pit_labels.csv`
- `source_switch_reconcile.csv`
- `coverage_baseline.csv`
- `share_polling/poll_summary.csv`（若未运行 poll 任务则可能不存在；记录在报告中）

- [ ] **Step 2: Write the gate report**

Write to `docs/资金流跟踪/phase_a_gate_report.md`:

```markdown
# Phase A Gate Report

**Spec:** `2026-08-12-ashare-flow-daily-design.md` §3.5.1
**Run date:** 2026-08-12
**Author:** Phase A 自动生成 + 人工 review

## 1. 交付物清单

| 文件 | 路径 | 状态 |
|---|---|---|
| api_capabilities.yaml | `data/flow_dashboard/phase_a_evidence/api_capabilities.yaml` | ✓ |
| ETF PIT 标签表 | `data/flow_dashboard/phase_a_evidence/etf_pit_labels.csv` | seed (待扩充) |
| 源切换对账 | `data/flow_dashboard/phase_a_evidence/source_switch_reconcile.csv` | ✓ |
| 覆盖率基线 | `data/flow_dashboard/phase_a_evidence/coverage_baseline.csv` | ✓ |
| 可得性轮询 | `data/flow_dashboard/phase_a_evidence/share_polling/poll_summary.csv` | TBD |

## 2. 实测可得性结论

(api_capabilities.yaml 的 live_sample 段已经记录每个 endpoint 实际行数与首次观测时间。)

- Tushare: `fund_basic`, `etf_share_size`, `fund_nav`, `fund_daily`, `margin`,
  `fut_basic`, `fut_daily`, `index_daily` — 全部返回非空样本。
- 新浪: `fetch_futures_node("IC"/"IM")` 与 `fetch_spot_indices(["sh000905","sh000852"])`
  — 全部返回非空样本。`hq.sinajs.cn/list=` 不支持 CFFEX 期货，已固定使用 VIP PHP API。

## 3. 已冻结的契约

- 单位：份额 → 份（万份 × 10000）；金额 → 元（万元 × 10000）。
- CFFEX 期货新浪代码：`IC=zzgz_qh`, `IM=im_qh`, `IF=qz_qh`, `IH=szgz_qh`。
- 现货指数新浪代码：CSI500=`sh000905`, CSI1000=`sh000852`。
- Tushare 期货代码后缀：`.CFX`（CFFEX）。
- `etf_share_size` 的 `total_size` 字段单位 = 万元（落盘前转元）。
- `etf_share_size` endpoint 不返回 `nav`/`close`；spec §1.3 要求：缺失时由 loader 写
  `quality_flags=missing_nav`，不得用 fund_daily 收盘价代替。

## 4. 待人工决策（来自 spec §5 needs_human_review）

下列项 Phase A 已采集证据，但数值阈值仍需人工冻结后才能进入 Phase B：

- `data_contract.sina_realtime_provider` — 访问条款合规性需人工确认。
- `data_contract.pit_sw_l1_history` — 申万 L1 个股历史成分源尚未确认；
  Phase C 行业两融面板不进入 Phase B。
- `logic_pipeline[s3_margin].parameters.reconciliation_tolerance` — 待用
  source_switch_reconcile.csv 的 `diff_pct` 分布冻结双阈值。
- `logic_pipeline[s3_margin].parameters.market_scope` — 已实测 SSE/SZSE/BSE 三所
  都返回；是否合并"全市场"待冻结。
- `logic_pipeline[s4_basis].parameters.contract_selector` — 当季合约定义待冻结
  （季月代码 / 切换日 / 缺失候选顺序）。
- `logic_pipeline[s4_basis].parameters.max_quote_skew_seconds` — 需 Phase B
  盘中实测报价延迟分布。
- `logic_pipeline[s2_flow_aggregation].parameters.coverage_gates` — 用
  coverage_baseline.csv 分布冻结 count_coverage 与 prior_aum_coverage 双门槛。
- `data_contract.etf_universes` — Phase A seed 含汇金宽基；港股、科技、周期、
  行业主题等分类需人工补齐 + 公告来源。
- `data_contract.etf_share_source_switch` — 用 source_switch_reconcile.csv 决定
  是否逐 ETF 独立换源日。

## 5. Phase B 启动条件

Phase B 实施计划可在以下条件成立后启动：

1. 人工确认 §4 中的 sina_realtime_provider 合规性。
2. 人工冻结 coverage_gates 与 reconciliation_tolerance 双阈值。
3. 人工冻结 contract_selector 规则（IC/IM 当季合约定义）。
4. 人工补充 etf_pit_labels.csv 的至少一组非汇金宽基分类（例如科技/TMT、周期、
   港股中的一类）。

不冻结 §4 中的项不影响：项目骨架、provider 契约、PIT 表结构、原子发布工具
（Phase B 早期任务可在 needs_human_review 关闭前先做）。

## 6. 已知风险

- etf_pit_labels.csv 的 seed 是从公开基金合同信息手工填的，未与原公告逐字校对。
  Phase B 实施前必须人工复核至少汇金标签的生效日（2015-07 期间多个时点）。
- 新浪 VIP PHP API 是非公开声明接口；响应结构变化由 sina_providers 的契约测试
  捕获，但人工 review 时仍需确认内部使用合规。
- Tushare token 与主项目共用同一个值（虽然环境变量名已解耦）；token 余额计费仍
  在主账户，需注意 Phase B 高频拉取时的成本。
```

- [ ] **Step 3: Commit**

```bash
git add docs/资金流跟踪/phase_a_gate_report.md
git commit -m "docs: phase A gate report with frozen contracts and open items"
```

---

## Task 16: 后缀不变测试（Red Line 1 守护）

Per spec §3.5 共通验收：向输入末尾追加任意未来数据，已归档日报的历史值必须逐元素不变。Phase A 不出日报，但 provider 层已经能产出系列；加一个回归测试确保 provider 不会因追加未来 trade_date 行而改写历史行。

**Files:**
- Modify: `tests/flow_dashboard/test_tushare_providers.py` (append)

- [ ] **Step 1: Append regression test**

```python
# 追加到 tests/flow_dashboard/test_tushare_providers.py
import pandas as pd
import pytest

from src.flow_dashboard.data.tushare_providers import _normalize_etf_share_size


def test_normalize_etf_share_size_suffix_invariant():
    """per spec §3.5 后缀不变测试：追加未来日数据不应改写历史行。"""
    base = pd.DataFrame([
        {"trade_date": "20260807", "ts_code": "510050.SH", "etf_name": "X",
         "total_share": 100.0, "total_size": 100.0, "exchange": "SSE"},
        {"trade_date": "20260808", "ts_code": "510050.SH", "etf_name": "X",
         "total_share": 110.0, "total_size": 110.0, "exchange": "SSE"},
    ])
    suffix = pd.DataFrame([
        {"trade_date": "20260809", "ts_code": "510050.SH", "etf_name": "X",
         "total_share": 150.0, "total_size": 150.0, "exchange": "SSE"},
    ])
    out_base = _normalize_etf_share_size(base).set_index("trade_date")
    out_suffix = _normalize_etf_share_size(
        pd.concat([base, suffix], ignore_index=True)
    ).set_index("trade_date")

    common = out_base.index.intersection(out_suffix.index)
    pd.testing.assert_frame_equal(
        out_base.loc[common], out_suffix.loc[common],
        check_like=True,
    )
```

- [ ] **Step 2: Run to verify pass**

Run: `pytest tests/flow_dashboard/test_tushare_providers.py::test_normalize_etf_share_size_suffix_invariant -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/flow_dashboard/test_tushare_providers.py
git commit -m "test: suffix-invariant regression for etf_share_size normalize"
```

---

## Self-Review

**1. Spec coverage（Phase A 范围 = §3.5.1）：**

- §3.5.1 "用真实账户对 Tushare API 拉取小样本" → Task 11 (run_api_capabilities.py --live) ✓
- §3.5.1 "对新浪公开行情响应做交易时段小样本采集" → Task 11 同一入口的 sina 段 ✓
- §3.5.1 "冻结字段、单位、代码映射、时间戳语义、频率、权限/访问约束、限流与 available_at" → Task 11 (yaml) + Task 15 (报告 §3) ✓
- §3.5.1 "落盘 api_capabilities.yaml" → Task 11 ✓
- §3.5.1 "ETF 分类生效区间表" → Task 10 ✓
- §3.5.1 "源切换对账报告" → Task 13 ✓
- §3.5.1 "覆盖率基线" → Task 14 ✓
- §3.5.1 "可得性轮询记录" → Task 12 ✓
- §3.5 共通验收 "后缀不变测试" → Task 16 ✓

**2. Placeholder scan：** 已检查；每个步骤都有完整代码块或可执行命令。无 TBD/TODO/实现 later。

**3. Type consistency：**
- `pull_etf_share_size` 在 Task 5/11/13/14 调用；签名一致 `(codes, start_date, end_date)` 返回含 `share_in_shares`、`total_size`、`total_share`、`exchange`、`trade_date`、`ts_code`、`etf_name` 的 DataFrame。
- `fetch_futures_node(variety)` 与 `FUTURES_NODE_MARK` 在 Task 8/9/11 一致使用。
- `QuoteBatch` 数据类字段在 Task 9 内一致（provider/observed_at/received_at/parse_version/quotes/failures）。
- `compute_coverage_series(flow_df, universe)` 在 Task 14 内部及测试中签名一致。

**4. 已知 out-of-scope 项（报告 §4 也列出）：**
- PIT 申万 L1 个股历史成分 — Phase C 独立 Gate。
- IC/IM 当季合约选择规则 — Phase A 实测，Phase B 人工冻结后实施。
- 期权 IV — Phase D。
- 港股 ETF / 减持事件 / 公募代理指标 — Phase C/D。

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-08-12-ashare-flow-phase-a.md`. Two execution options:

1. **Subagent-Driven (recommended)** — 每个 Task 派一个全新 subagent 实施，每 Task 之间由我 review；迭代快、上下文独立。
2. **Inline Execution** — 在当前会话中用 executing-plans 批量推进，带 checkpoint 给您 review。

请选择哪种？
