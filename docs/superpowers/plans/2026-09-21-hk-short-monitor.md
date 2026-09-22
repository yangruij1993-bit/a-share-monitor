# 港股沽空监控（hk_short）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 flow_dashboard 上新增港股沽空监控模块：每日盘后拉取东财/HKEX/SFC 数据，纯规则状态引擎输出市场空头状态结论，前端以同页 tab 展示（A股资金流 | 港股沽空）。

**Architecture:** 新增 `data/hk_short/` 子包（HTTP 重试客户端 + 香港日历 + 三个数据源客户端 + 遵循现有 PIT 契约的 loaders，缓存落 parquet）；`indicators/hk_short_metrics.py`（纯函数指标）+ `indicators/hk_short_state.py`（§6.4 状态矩阵）；`render/panels_hk_short.py` 只从缓存确定性渲染；`theme.build_html_skeleton` 增加 tabs 支持；新 runner `com.ygr.hk-short.eod`（18:45）与 A股 runner 共用 `RUNNERS_LOCK`。

**Tech Stack:** Python 3 + pandas + requests + plotly（现有依赖，不新增第三方库；ListOfSecurities.xlsx 用标准库 zipfile+re 解析）。

**必读上下文（实施前通读）：**
- 设计文档：`docs/superpowers/specs/2026-09-21-hk-short-monitor-design.md`（§5 数据链路口径已冻结）
- 数据源验证：`docs/港股沽空/source-validation.md`（全部 URL/解析坑/对账数字的权威来源）
- 现有契约参照：`src/flow_dashboard/data/loaders.py`（缓存→增量→merge→PIT 模式）、`src/flow_dashboard/data/schema.py`（AUDIT_COLUMNS）、`src/flow_dashboard/render/assembly.py`（锁与发布）

**执行环境：** 在 worktree（建议分支 `feature/hk-short-monitor`）中实施，不在 main 上直接改。测试命令一律在仓库根目录运行：`python -m pytest tests/flow_dashboard/test_hk_xxx.py -v`。真实网络测试挂 `@pytest.mark.live`（默认 skip，conftest 已有逻辑）。

**关键口径（冻结，不得在实施中更改）：**
1. 市场层指标（加权 SSR、日/周沽空强度、20 日均值倍数）一律**股票口径**：Σ东财当日沽空金额 / Σ东财当日总成交金额。页面标注"股票口径，不含 ETF/ETP"。
2. ETF 干扰证据用 HKEX 全口径当日值（ETF 沽空额 / 全口径总额，阈值 30%）。
3. 个股 SSR = 卖空金额/成交额（金额口径），历史来自全市场逐证券日频数据（东财，股票口径）。
4. watch list ETF（2800/3033）卖空数据来自 HKEX dayquot；不足 60 个观测显示"样本不足"。
5. SFC `available_at = published_at`（响应 Last-Modified），绝不按报告期+N天倒推；宽限期 = position_date 后第 5 个香港交易日。
6. 东财"最新价"列是查询时点价，一律丢弃；历史价格只走 kline 接口。
7. HKEX dayquot 的 PREVIOUS DAY'S ADJUSTED 段在 T+1 抓取时覆盖 T-1 缓存（quality_flags="restated"）。

---

## 文件结构（全景）

```
src/flow_dashboard/
  config.py                                   # 修改：HK_* 配置
  data/hk_short/__init__.py                   # 新建空文件
  data/hk_short/http_client.py                # 重试 GET / 404 探测 / JSON 校验
  data/hk_short/hk_calendar.py                # 香港交易日历 + SFC 宽限期
  data/hk_short/em_client.py                  # 东财：sellshort 解析/翻页、kline、f84
  data/hk_short/hkex_client.py                # HKEX：dayquot/ashtmain 解析、LOS xlsx
  data/hk_short/sfc_client.py                 # SFC 周报 CSV（URL 候选探测）
  data/hk_short/loaders.py                    # 6 个 PIT loader（parquet 缓存）
  indicators/hk_short_metrics.py              # 纯函数指标
  indicators/hk_short_state.py                # §6.4 状态引擎
  render/panels_hk_short.py                   # 港股 tab 渲染（只读缓存）
  render/theme.py                             # 修改：tabs 支持
  pipeline.py                                 # 修改：tabs 集成 + report_date
  hk_short_pipeline.py                        # run_hk_short_eod 入口
scripts/flow_dashboard/run_hk_short_eod.py    # launchd runner
scripts/flow_dashboard/backfill_hk_short.py   # 一次性回补 CLI
scripts/launchd/com.ygr.hk-short.eod.plist    # 18:45 调度
tests/flow_dashboard/test_hk_calendar.py
tests/flow_dashboard/test_hk_http_client.py
tests/flow_dashboard/test_hk_em_client.py
tests/flow_dashboard/test_hk_hkex_client.py
tests/flow_dashboard/test_hk_sfc_client.py
tests/flow_dashboard/test_hk_loaders.py
tests/flow_dashboard/test_hk_metrics.py
tests/flow_dashboard/test_hk_state.py
tests/flow_dashboard/test_hk_theme_tabs.py
tests/flow_dashboard/test_hk_panels.py
tests/flow_dashboard/test_hk_pipeline.py
tests/flow_dashboard/test_hk_live.py          # @live 冒烟
```

缓存目录 `data/hk_short/cache/`（config 定义）：`em_sellshort_daily.parquet`、`em_days_covered.parquet`、`hkex_dayquot_daily.parquet`、`sfc_weekly.parquet`、`hk_kline.parquet`、`hk_shares.parquet`、`los_master.parquet`。

DataFrame 列契约（各任务必须一致）：

| 数据集 | 业务列（AUDIT 列之外） |
|---|---|
| em_sellshort | `code`(str,zfill5) `name` `trade_date` `short_shares` `short_avg_price` `short_amount` `turnover` `ssr_pct` |
| em_days_covered | `trade_date` `coverage`("full"/"partial") |
| hkex_dayquot | `code` `name` `trade_date` `short_shares` `short_amount` `total_shares_traded` `turnover` |
| sfc_weekly | `code` `name` `position_date` `short_shares` `short_amount_hkd` `published_at` |
| hk_kline | `secid` `trade_date` `open` `close` `high` `low` `volume` `amount` |
| hk_shares | `code` `total_shares` |
| los_master | `code` `name` `category` `sub_category` `effective_date` |

AUDIT 列（沿用 `schema.AUDIT_COLUMNS` 语义）：`source_date` `first_observed_at` `available_at` `fetched_at` `source` `source_version`（+ 可选 `quality_flags`）。PIT 过滤恒为 `available_at <= as_of`。

---

### Task 1: config.py 港股配置

**Files:**
- Modify: `src/flow_dashboard/config.py`（文件末尾追加）
- Test: `tests/flow_dashboard/test_hk_config.py`

- [ ] **Step 1: 写失败测试**

```python
"""hk_short 配置契约测试。"""
from flow_dashboard import config


def test_hk_watch_list_frozen():
    assert len(config.HK_WATCH_LIST) == 8
    codes = [c for _, c in config.HK_WATCH_LIST]
    assert codes == ["0700.HK", "9988.HK", "3690.HK", "1810.HK",
                     "0981.HK", "9992.HK", "2800.HK", "3033.HK"]


def test_hk_thresholds_frozen():
    t = config.HK_THRESHOLDS
    assert t["mkt_sfc_delta_bp"] == 3.0
    assert t["stock_sfc_delta_bp"] == 5.0
    assert t["weekly_intensity_high"] == 1.25
    assert t["ssr_pct_high"] == 80.0
    assert t["price_ret_bp"] == 100.0
    assert t["participation_high"] == 1.20
    assert t["etf_interference"] == 0.30
    assert t["ssr_pct_min_obs"] == 20
    assert t["ssr_pct_window"] == 60
    assert t["sfc_min_comparable"] == 100
    assert t["sfc_min_coverage"] == 0.80


def test_hk_cache_dir_and_secids():
    assert config.HK_SHORT_CACHE_DIR.name == "cache"
    assert config.HK_INDEX_SECIDS == {"HSI": "100.HSI", "HSTECH": "124.HSTECH"}
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/flow_dashboard/test_hk_config.py -v`
Expected: FAIL（AttributeError: HK_WATCH_LIST）

- [ ] **Step 3: 实现（config.py 末尾追加）**

```python
# ---------------------------------------------------------------------------
# 港股沽空监控（hk_short）— 设计 §5/§6.2 冻结口径
# ---------------------------------------------------------------------------
HK_SHORT_CACHE_DIR = DATA_DIR / "hk_short" / "cache"

# (名称, 代码)：watch list，设计 §4.3 用户确认 8 只
HK_WATCH_LIST: list[tuple[str, str]] = [
    ("腾讯控股", "0700.HK"),
    ("阿里巴巴-W", "9988.HK"),
    ("美团-W", "3690.HK"),
    ("小米集团-W", "1810.HK"),
    ("中芯国际", "0981.HK"),
    ("泡泡玛特", "9992.HK"),
    ("盈富基金", "2800.HK"),
    ("恒生科技ETF", "3033.HK"),
]

# 东财 secid：恒指/恒生科技用专门前缀，个股与 ETF 用 116.（源验证 §5）
HK_INDEX_SECIDS = {"HSI": "100.HSI", "HSTECH": "124.HSTECH"}


def _hk_secid(hk_code: str) -> str:
    """'0700.HK' -> '116.00700'。"""
    return f"116.{hk_code.split('.')[0].zfill(5)}"


# §6.2 首版冻结阈值。校准只能改这里的数值 + 对应测试，不得改状态优先级。
HK_THRESHOLDS = {
    "mkt_sfc_delta_bp": 3.0,        # 市场须申报淡仓比例变化 ±3bp
    "mkt_sfc_breadth_pos": 0.55,    # 淡仓上升证券占比 >=55%
    "mkt_sfc_breadth_neg": 0.45,    # 淡仓上升证券占比 <=45%
    "stock_sfc_delta_bp": 5.0,      # 个股淡仓占总股本比例变化 ±5bp
    "weekly_intensity_high": 1.25,  # 周沽空强度
    "ssr_pct_high": 80.0,           # SSR 60日历史分位
    "price_ret_bp": 100.0,          # 5日收益率 ±1%（bp）
    "participation_high": 1.20,     # 参与度倍数
    "etf_interference": 0.30,       # ETF 沽空额占全口径比例
    # 指标窗口
    "ssr_pct_min_obs": 20,
    "ssr_pct_window": 60,
    "daily_intensity_window": 20,
    "weekly_window_days": 5,
    "weekly_n_windows": 12,
    "sfc_min_comparable": 100,      # 可比证券数下限
    "sfc_min_coverage": 0.80,       # 可比集合市值覆盖率下限
    "corp_action_price_jump": 0.20, # 隐含价 WoW 跳变 >20% 视为公司行动嫌疑
    "sfc_grace_trading_days": 5,    # SFC 宽限期（香港交易日）
}

HK_EM_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
    "Referer": "https://quote.eastmoney.com",
}
HKEX_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"),
}
```

并在 `ensure_dirs()`（若存在该函数；否则在模块级已有目录创建处）追加一行 `HK_SHORT_CACHE_DIR.mkdir(parents=True, exist_ok=True)`。若 config 无 ensure_dirs，则跳过此步（loaders 自行 mkdir）。

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/flow_dashboard/test_hk_config.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/config.py tests/flow_dashboard/test_hk_config.py
git commit -m "feat(hk-short): frozen config - watch list, thresholds, secids, cache dir"
```

---

### Task 2: http_client.py 重试客户端

**Files:**
- Create: `src/flow_dashboard/data/hk_short/__init__.py`（空文件）
- Create: `src/flow_dashboard/data/hk_short/http_client.py`
- Test: `tests/flow_dashboard/test_hk_http_client.py`

背景（源验证 §1/§9）：东财 push2/hk 系接口存在间歇性空响应（rate limit），实测 sleep 5-8s 后重试成功；HKEX 对无 UA 请求可能 403；SFC 假日周候选 URL 404 是正常语义（不是错误）。

- [ ] **Step 1: 写失败测试**

```python
"""http_client：重试、404 探测、JSON 校验。"""
import json
import pytest

from flow_dashboard.data.hk_short import http_client


class _Resp:
    def __init__(self, status=200, text="", content=b"", headers=None):
        self.status_code = status
        self.text = text
        self.content = content
        self.headers = headers or {}
        self.ok = status < 400


def test_fetch_text_retries_on_empty_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, params=None, headers=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return _Resp(200, text="")  # 东财限流空响应
        return _Resp(200, text="<html>ok</html>")

    monkeypatch.setattr(http_client.requests, "get", fake_get)
    monkeypatch.setattr(http_client.time, "sleep", lambda s: None)
    out = http_client.fetch_text("http://x", max_retries=3, backoff_base=0)
    assert out == "<html>ok</html>"
    assert calls["n"] == 2


def test_fetch_text_raises_after_max_retries(monkeypatch):
    monkeypatch.setattr(http_client.requests, "get",
                        lambda *a, **k: _Resp(500, text="boom"))
    monkeypatch.setattr(http_client.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError):
        http_client.fetch_text("http://x", max_retries=2, backoff_base=0)


def test_try_get_returns_none_on_404(monkeypatch):
    monkeypatch.setattr(http_client.requests, "get",
                        lambda *a, **k: _Resp(404))
    assert http_client.try_get("http://x") is None


def test_try_get_returns_response_with_last_modified(monkeypatch):
    r = _Resp(200, text="a,b", content=b"a,b",
              headers={"Last-Modified": "Fri, 18 Sep 2026 07:41:00 GMT"})
    monkeypatch.setattr(http_client.requests, "get", lambda *a, **k: r)
    out = http_client.try_get("http://x")
    assert out is not None
    assert out.headers["Last-Modified"].startswith("Fri")


def test_fetch_json_validates_payload(monkeypatch):
    bad = _Resp(200, text=json.dumps({"rc": 0, "data": None}))
    good = _Resp(200, text=json.dumps({"rc": 0, "data": {"klines": ["x"]}}))
    seq = {"i": 0}

    def fake_get(*a, **k):
        seq["i"] += 1
        return bad if seq["i"] == 1 else good

    monkeypatch.setattr(http_client.requests, "get", fake_get)
    monkeypatch.setattr(http_client.time, "sleep", lambda s: None)
    j = http_client.fetch_json("http://x", validate=lambda j: j.get("data"))
    assert j["data"]["klines"] == ["x"]
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/flow_dashboard/test_hk_http_client.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

`src/flow_dashboard/data/hk_short/__init__.py`：空文件。

`src/flow_dashboard/data/hk_short/http_client.py`：

```python
"""带重试的 HTTP 客户端（东财限流 → 指数退避；SFC 候选 URL 404 = 正常探测）。

源验证 §1：东财 push2/hk 系接口间歇性空响应，实测 sleep 5-8s 后重试成功。
"""
from __future__ import annotations

import json
import logging
import time
from typing import Callable

import requests

log = logging.getLogger(__name__)


def fetch_text(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    max_retries: int = 3,
    backoff_base: float = 5.0,
    timeout: float = 90.0,
) -> str:
    """GET → 文本。空响应/5xx/网络错误重试，耗尽后抛 RuntimeError。"""
    last: Exception | str = "?"
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=timeout)
            if r.status_code == 200 and r.text.strip():
                return r.text
            last = f"status={r.status_code} len={len(r.text)}"
        except Exception as e:  # noqa: BLE001 — 网络错误统一重试
            last = e
        if attempt < max_retries:
            wait = backoff_base * (2 ** (attempt - 1))
            log.warning("fetch %s attempt %d failed (%s); backoff %.0fs",
                        url[:120], attempt, last, wait)
            time.sleep(wait)
    raise RuntimeError(f"fetch failed after {max_retries} retries: {url} last={last}")


def try_get(
    url: String_,
    *,
    headers: dict | None = None,
    max_retries: int = 3,
    backoff_base: float = 2.0,
    timeout: float = 90.0,
) -> requests.Response | None:
    """GET；404 → None（候选 URL 探测语义）；5xx/网络错误重试后抛错。"""
    last: Exception | str = "?"
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 200:
                return r
            if r.status_code == 404:
                return None
            last = f"status={r.status_code}"
        except Exception as e:  # noqa: BLE001
            last = e
        if attempt < max_retries:
            time.sleep(backoff_base * (2 ** (attempt - 1)))
    raise RuntimeError(f"try_get failed after {max_retries} retries: {url} last={last}")


def fetch_json(
    url: String_,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    max_retries: int = 3,
    backoff_base: float = 5.0,
    timeout: float = 90.0,
    validate: Callable[[dict], bool] | None = None,
) -> dict:
    """GET → JSON；validate 返回 False 视为失败并重试（东财 data:null 限流形态）。"""
    last: Exception | str = "?"
    for attempt in range(1, max_retries + 1):
        try:
            text = fetch_text(url, params=params, headers=headers,
                              max_retries=1, timeout=timeout)
            j = json.loads(text)
            if validate is not None and not validate(j):
                raise ValueError(f"payload validation failed: {text[:120]}")
            return j
        except Exception as e:  # noqa: BLE001
            last = e
        if attempt < max_retries:
            wait = backoff_base * (2 ** (attempt - 1))
            log.warning("fetch_json %s attempt %d failed (%s); backoff %.0fs",
                        url[:120], attempt, last, wait)
            time.sleep(wait)
    raise RuntimeError(f"fetch_json failed after {max_retries} retries: {url} last={last}")
```

注意：把上面两处 `url: String_` 改为 `url: str`（书写笔误防护——照抄时直接用 `str`）。

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/flow_dashboard/test_hk_http_client.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/data/hk_short/__init__.py src/flow_dashboard/data/hk_short/http_client.py tests/flow_dashboard/test_hk_http_client.py
git commit -m "feat(hk-short): retrying http client with 404-probe and json validation"
```

---

### Task 3: hk_calendar.py 香港交易日历

**Files:**
- Create: `src/flow_dashboard/data/hk_short/hk_calendar.py`
- Test: `tests/flow_dashboard/test_hk_calendar.py`

2026 假日来自公开日历（验证时检索）；4/4 清明为周日且补假安排未公布 → 不列入，偶发空抓取由 loader 容错。年份 >2026 回退为"仅周末过滤"并告警。

- [ ] **Step 1: 写失败测试**

```python
"""香港交易日历：周末/假日、宽限期、SFC position_date 枚举。"""
import pandas as pd

from flow_dashboard.data.hk_short import hk_calendar as cal


def test_weekend_and_holiday():
    assert not cal.is_hk_trading_day("2026-09-19")  # 周六
    assert not cal.is_hk_trading_day("2026-09-20")  # 周日
    assert not cal.is_hk_trading_day("2026-10-01")  # 国庆（HK 假日）
    assert not cal.is_hk_trading_day("2026-02-18")  # 农历新年
    assert cal.is_hk_trading_day("2026-09-18")      # 周五
    assert cal.is_hk_trading_day("2026-02-16")      # 新年假期前的周一


def test_latest_trading_day_on_or_before():
    # 周一 -> 上周五；假日 -> 前一交易日
    assert cal.latest_trading_day_on_or_before("2026-09-21") == pd.Timestamp("2026-09-18")
    assert cal.latest_trading_day_on_or_before("2026-10-01") == pd.Timestamp("2026-09-30")


def test_prev_trading_day():
    assert cal.prev_trading_day("2026-09-18") == pd.Timestamp("2026-09-17")
    assert cal.prev_trading_day("2026-02-17") == pd.Timestamp("2026-02-16")  # 跨农历假期


def test_next_trading_days_for_grace_period():
    # position_date=2026-09-11(周五) -> 后 5 个交易日 = 14,15,16,17,18
    days = cal.next_trk_days("2026-09-11", 5)
    assert [d.strftime("%m-%d") for d in days] == ["09-14", "09-15", "09-16", "09-17", "09-18"]


def test_grace_deadline_is_eod_of_5th_trading_day():
    d = cal.sfc_grace_deadline("2026-09-11")
    assert d == pd.Timestamp("2026-09-18 23:59:59")


def test_recent_sfc_position_dates():
    # 2026-09-21(周一) -> 最近一个已完成交易周的最后一个交易日是 09-18
    out = cal.recent_sfc_position_dates("2026-09-21", n=3)
    assert out[0] == pd.Timestamp("2026-09-18")
    assert out[1] == pd.Timestamp("2026-09-11")
    assert len(out) == 3
    # 周三 -> 本周五还没到，只能取上周五
    out2 = cal.recent_sfc_position_dates("2026-09-16", n=1)
    assert out2[0] == pd.Timestamp("2026-09-11")


def test_time_aware_semantics_pinned():
    # EOD runner 契约：带时间且当日为交易日 → 当日计入（Task 14 依赖）
    assert cal.latest_trading_day_on_or_before(
        pd.Timestamp("2026-09-21 18:45", tz="Asia/Shanghai")) == pd.Timestamp("2026-09-21")
    assert cal.latest_trading_day_on_or_before(
        pd.Timestamp("2026-09-18 16:10", tz="Asia/Shanghai")) == pd.Timestamp("2026-09-18")
    # 带时间但当日为假日 → 前一交易日
    assert cal.latest_trading_day_on_or_before(
        pd.Timestamp("2026-10-01 18:45", tz="Asia/Shanghai")) == pd.Timestamp("2026-09-30")
    # 复活节周（周五 04-03 受难日为假日）→ 最近已完成周取周四
    assert cal.recent_sfc_position_dates("2026-04-07", n=1)[0] == pd.Timestamp("2026-04-02")
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/flow_dashboard/test_hk_calendar.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

```python
"""香港交易日历（2026 假日硬编码）+ SFC 宽限期。

设计 §6.3：宽限期 = position_date 后第 5 个香港交易日（EOD）。
注意：2026-04-04 为复活节周六；清明 2026-04-05 为周日、补假未定 → 未列入；该周如遇空数据由 loader 容错。
年份 > 2026：假日表缺失，回退仅过滤周末并 log 告警（届时须更新假日表）。
"""
from __future__ import annotations

import logging

import pandas as pd

log = logging.getLogger(__name__)

HK_HOLIDAYS_2026 = {
    # 元旦
    "2026-01-01",
    # 农历年初二/三/四（首日 02-17 周二）
    "2026-02-17", "2026-02-18", "2026-02-19",
    # 耶稣受难日 / 复活节周一
    "2026-04-03", "2026-04-04", "2026-04-06",
    # 劳动节 / 佛诞 / 特区成立纪念日
    "2026-05-01", "2026-05-25", "2026-06-19", "2026-07-01",
    # 国庆 / 重阳
    "2026-10-01", "2026-10-19",
    # 圣诞 / 圣诞翌日
    "2026-12-25", "2026-12-28",
}

_warned = {"flag": False}


def _ts(d) -> pd.Timestamp:
    ts = pd.Timestamp(d)
    return ts.tz_localize(None) if ts.tzinfo is None else ts.tz_convert(None).normalize() if False else ts.tz_localize(None) if ts.tzinfo is None else ts


def _norm(d) -> pd.Timestamp:
    ts = pd.Timestamp(d)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("Asia/Shanghai").tz_localize(None)
    return ts.normalize()


def is_hk_trading_day(d) -> bool:
    ts = _norm(d)
    if ts.weekday() >= 5:
        return False
    if ts.year == 2026:
        return ts.strftime("%Y-%m-%d") not in HK_HOLIDAYS_2026
    if ts.year > 2026 and not _warned["flag"]:
        log.warning("HK holiday table only covers 2026; %s falls back to weekday-only", ts.date())
        _warned["flag"] = True
    return True


def latest_trading_day_on_or_before(d) -> pd.Timestamp:
    ts = _norm(d)
    while not is_hk_trading_day(ts):
        ts -= pd.Timedelta(days=1)
    return ts


def prev_trading_day(d) -> pd.Timestamp:
    return latest_trading_day_on_or_before(_norm(d) - pd.Timedelta(days=1))


def next_trk_days(d, n: int) -> list[pd.Timestamp]:
    """严格在 d 之后的 n 个香港交易日（升序）。"""
    out: list[pd.Timestamp] = []
    ts = _norm(d)
    while len(out) < n:
        ts += pd.Timedelta(days=1)
        if is_hk_trading_day(ts):
            out.append(ts.normalize())
    return out


def sfc_grace_deadline(position_date) -> pd.Timestamp:
    """position_date 后第 5 个香港交易日的 EOD（设计 §6.3）。"""
    days = next_trk_days(position_date, 5)
    return days[-1] + pd.Timedelta(hours=23, minutes=59, seconds=59)


def recent_sfc_position_dates(as_of, n: int = 8) -> list[pd.Timestamp]:
    """最近 n 个"已结束交易周"的最后一个香港交易日（降序）。

    本周若已过周五（含周末），其周五也计入；本周未到周五则从上周五开始。
    """
    ts = _norm(as_of)
    monday = ts - pd.Timedelta(days=ts.weekday())
    out: list[pd.Timestamp] = []
    for k in range(0, n):
        week_mon = monday - pd.Timedelta(weeks=k)
        week_sun = week_mon + pd.Timedelta(days=6)
        d = week_sun
        while d >= week_mon and not is_hk_trading_day(d):
            d -= pd.Timedelta(days=1)
        if d >= week_mon and d < ts:
            out.append(d.normalize())
    return out
```

注意：实现里删掉笔误函数 `_ts`（保留 `_norm` 即可）。

**勘误（c）：原参考代码与其验收测试自相矛盾，按测试为准修正了三处**（后续任务依赖这些契约，实施时不得回退）：
1. `latest_trading_day_on_or_before` 改为时间感知语义：纯日期（午夜）输入 = 问"当日开盘前"，当日不计入（周一 → 上周五）；带具体时间的时间戳且当日为交易日 → 当日计入。Task 14 EOD runner（18:45 带时间）与 Task 16 @live（now-1d 带时间）依赖"计入当日"；`prev_trading_day` 内部回溯依赖"不计入当日"。
2. `prev_trading_day` 独立实现为"严格早于 d 的最近交易日"（不再委托 latest_trading_day_on_or_before，否则跨午夜语义漂移）。
3. `recent_sfc_position_dates` 用 while 循环向更早交易周回溯直到取满 n 期（原 `for k in range(0, n)` 在本周五未到时只能产出 n-1 期，测试要求 len==3）。

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/flow_dashboard/test_hk_calendar.py -v`
Expected: 7 passed（6 个原测试 + 时间语义钉死测试，质量评审补）

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/data/hk_short/hk_calendar.py tests/flow_dashboard/test_hk_calendar.py
git commit -m "feat(hk-short): HK trading calendar with SFC grace period"
```

---

### Task 4: em_client.py 东财客户端

**Files:**
- Create: `src/flow_dashboard/data/hk_short/em_client.py`
- Test: `tests/flow_dashboard/test_hk_em_client.py`

源验证 §1/§5 要点：HTML 表格静态分页（`sellshort_{N}.html`，`&page=` 参数无效）；金额列万/亿后缀；「最新价」是查询时点价必须丢弃；kline 盘中调用返回未完成当日 K 线必须丢弃（16:10 HKT 后为准）；secid 恒指 `100.HSI`、恒生科技 `124.HSTECH`、个股/ETF `116.XXXXX`。

- [ ] **Step 1: 写失败测试**

```python
"""em_client：HTML 解析、万/亿金额、翻页发现、未完成K线丢弃。"""
import pandas as pd
import pytest

from flow_dashboard.data.hk_short import em_client

ROW_TMPL = (
    "<tr><td><span>{i}</span></td>"
    '<td><a href="/q/{code}.html">{code}</a></td>'
    '<td><a href="/q/{code}.html">{name}</a></td>'
    "<td><span>315.000</span></td>"          # 最新价（查询时点价，应被丢弃）
    "<td><span>{shares}</span></td>"          # 沽空数量
    "<td><span>313.221</span></td>"           # 沽空平均价
    "<td><span>{amt}</span></td>"             # 沽空金额
    "<td><span>{tov}</span></td>"             # 总成交金额
    "<td><span>{ssr}%</span></td>"
    "<td><span>2026-09-18</span></td></tr>"
)

HTML_2ROWS = (
    '<html><table><tbody>'
    + ROW_TMPL.format(i=1, code="00700", name="腾讯控股",
                      shares="2,033,300", amt="6.37亿", tov="36.94亿", ssr="17.25")
    + ROW_TMPL.format(i=2, code="09881", name="中芯国际",
                      shares="1,090,000", amt="7427.37万", tov="640508607", ssr="11.60")
    + "</tbody></table>"
    '<div class="pagerbox"><a href="sellshort_2.html">2</a>'
    '<a href="sellshort_15.html">15</a></div></html>'
)

HTML_1ROW = (
    '<html><table><tbody>'
    + ROW_TMPL.format(i=1, code="00700", name="腾讯控股",
                      shares="2,033,300", amt="6.37亿", tov="36.94亿", ssr="17.25")
    + "</tbody></table></html>"
)

HTML_PAGER2 = (
    '<html><table><tbody>'
    + ROW_TMPL.format(i=1, code="00700", name="腾讯控股",
                      shares="2,033,300", amt="6.37亿", tov="36.94亿", ssr="17.25")
    + ROW_TMPL.format(i=2, code="09988", name="阿里巴巴-W",
                      shares="1,000,000", amt="1.00亿", tov="10.00亿", ssr="10.00")
    + "</tbody></table>"
    '<div class="pagerbox"><a href="sellshort_2.html">2</a></div></html>'
)


def test_parse_amount_suffixes():
    assert em_client.parse_amount("7427.37万") == pytest.approx(74273700.0)
    assert em_client.parse_amount("1.23亿") == pytest.approx(123000000.0)
    assert em_client.parse_amount("640,508,607") == pytest.approx(640508607.0)
    assert em_client.parse_amount("6.37亿") == pytest.approx(637000000.0)


def test_parse_sellshort_html_drops_query_time_price():
    df = em_client.parse_sellshort_html(HTML_2ROWS)
    assert len(df) == 2
    r = df.iloc[0]
    assert r["code"] == "00700"
    assert r["name"] == "腾讯控股"
    assert r["short_shares"] == 2033300.0
    assert r["short_amount"] == pytest.approx(637000000.0)
    assert r["turnover"] == pytest.approx(3694000000.0)
    assert r["ssr_pct"] == 17.25
    assert r["source_date"] == "2026-09-18"
    assert "last_price" not in df.columns  # 查询时点价必须丢弃（源验证 §1）


def test_max_page_from_pagerbox():
    assert em_client._max_page(HTML_2ROWS) == 15
    assert em_client._max_page("<html>no pager</html>") == 1


def test_fetch_sellshort_day_paginates(monkeypatch):
    calls = []

    def fake_page(page, params):
        calls.append((page, params["sdate"], params["edate"], params["code"]))
        return HTML_PAGER2 if page == 1 else HTML_1ROW

    monkeypatch.setattr(em_client, "_fetch_page_text", fake_page)
    df = em_client.fetch_sellshort_day("2026-09-18")
    assert [c[0] for c in calls] == [1, 2]        # 第 1 页 pagerbox 发现共 2 页
    assert all(c[1] == c[2] == "2026-09-18" and c[3] == "" for c in calls)
    assert (df["trade_date"] == pd.Timestamp("2026-09-18")).all()
    assert len(df) == 3                           # 第 1 页 2 行 + 第 2 页 1 行


def test_fetch_sellshort_stock_range_query(monkeypatch):
    calls = []

    def fake_page(page, params):
        calls.append(params)
        return HTML_1ROW

    monkeypatch.setattr(em_client, "_fetch_page_text", fake_page)
    df = em_client.fetch_sellshort_stock("00700", "2026-05-01", "2026-09-18")
    assert calls[0]["code"] == "00700"
    assert calls[0]["sdate"] == "2026-05-01" and calls[0]["edate"] == "2026-09-18"
    # 区间查询行内自带日期列 → trade_date 取自 source_date
    assert (df["trade_date"] == pd.to_datetime(df["source_date"])).all()


def _kline_json():
    return {"rc": 0, "data": {"code": "100.HSI", "klines": [
        "2026-09-17,1,26450.1,26500.0,26400.0,1000,100000",
        "2026-09-18,1,26500.1,26600.0,26480.0,1200,120000",
    ]}}


def test_fetch_kline_drops_incomplete_today(monkeypatch):
    monkeypatch.setattr(
        em_client.http_client, "fetch_json",
        lambda *a, **k: _kline_json())
    # 抓取时点 15:00（<16:10 HKT）→ 丢掉当日未完成行（源验证 §5）
    df = em_client.fetch_kline(
        "100.HSI", "2026-09-01", "2026-09-18",
        now=pd.Timestamp("2026-09-18 15:00:00", tz="Asia/Shanghai"))
    assert df["trade_date"].max() == pd.Timestamp("2026-09-17")
    # 16:30（收市后）→ 保留当日行
    df2 = em_client.fetch_kline(
        "100.HSI", "2026-09-01", "2026-09-18",
        now=pd.Timestamp("2026-09-18 16:30:00", tz="Asia/Shanghai"))
    assert df2["trade_date"].max() == pd.Timestamp("2026-09-18")


def test_fetch_total_shares_pins_secid_and_validation(monkeypatch):
    captured = {}

    def fake_fetch_json(url, *, params=None, headers=None, **k):
        captured["url"] = url
        captured["params"] = params
        captured["validate"] = k.get("validate")
        return {"data": {"f84": 9095085993}}

    monkeypatch.setattr(em_client.http_client, "fetch_json", fake_fetch_json)
    out = em_client.fetch_total_shares("00700")
    assert out == 9095085993 and isinstance(out, int)
    assert captured["params"]["secid"] == "116.00700"   # 5 位 zfill + 116. 前缀
    assert captured["params"]["fields"] == "f84"
    # validate 必须拒绝东财限流形态 data:null，接受正常载荷
    assert not captured["validate"]({"rc": 0, "data": None})
    assert captured["validate"]({"rc": 0, "data": {"f84": 1}})
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/flow_dashboard/test_hk_em_client.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

```python
"""东方财富港股客户端：逐证券卖空（股票口径）、K线、总股本。

源验证 §1（sellshort HTML）与 §5（push2his kline / push2 f84）。
口径冻结：sellshort 只含主板+GEM 股票（含 RMB 柜台），不含 ETF/ETP/REIT/L&I。
"""
from __future__ import annotations

import logging
import re

import pandas as pd

from flow_dashboard.config import HK_EM_HEADERS
from flow_dashboard.data.hk_short import http_client

log = logging.getLogger(__name__)

BASE = "https://hk.eastmoney.com"

# 源验证 §1 实测行结构：序号|代码锚点|名称td(被行内通配跳过再单独抓)|最新价|沽空数量|沽空均价|沽空金额|总成交金额|SSR%|日期
# 行内通配用 (?:(?!</tr>).)*? 收紧：格式漂移时不允许回溯跨过 </tr> 拼接相邻行（质量评审加固）
SELLSHORT_ROW_RE = re.compile(
    r'<tr>\s*<td><span>\d+</span></td>\s*<td>\s*<a[^>]*>(\d{5})</a>\s*</td>(?:(?!</tr>).)*?'
    r'<td><span>([\d.]+)</span></td>\s*'          # 最新价（丢弃）
    r'<td><span>([\d,.]+)\s*</span></td>\s*'       # 沽空数量
    r'<td><span>([\d.]+)</span></td>\s*'           # 沽空平均价
    r'<td><span>([\d.万亿]+)</span></td>\s*'       # 沽空金额
    r'<td><span>([\d.万亿]+)</span></td>\s*'       # 总成交金额
    r'<td><span>([\d.]+)%</span></td>\s*'          # SSR
    r'<td><span>(\d{4}-\d{2}-\d{2})</span></td>',  # 日期
    re.S,
)
NAME_RE = re.compile(r'</a>\s*</td>\s*<td[^>]*>\s*<a[^>]*>([^<]+)</a>', re.S)


def parse_amount(text: str) -> float:
    t = text.strip().replace(",", "")
    if t.endswith("亿"):
        return float(t[:-1]) * 1e8
    if t.endswith("万"):
        return float(t[:-1]) * 1e4
    return float(t)


def parse_sellshort_html(html_text: str) -> pd.DataFrame:
    rows = []
    for m in SELLSHORT_ROW_RE.finditer(html_text):
        code, _last_price, shares, avg_px, amt, tov, ssr, d = m.groups()
        nm = NAME_RE.search(m.group(0))
        rows.append({
            "code": code,
            "name": nm.group(1).strip() if nm else "",
            "short_shares": float(shares.replace(",", "")),
            "short_avg_price": float(avg_px),
            "short_amount": parse_amount(amt),
            "turnover": parse_amount(tov),
            "ssr_pct": float(ssr),
            "source_date": d,
        })
    return pd.DataFrame(rows)


def _max_page(html_text: str) -> int:
    pages = [int(p) for p in re.findall(r"sellshort_(\d+)\.html", html_text)]
    return max(pages) if pages else 1


def _fetch_page_text(page: int, params: dict) -> str:
    url = f"{BASE}/sellshort.html" if page == 1 else f"{BASE}/sellshort_{page}.html"
    return http_client.fetch_text(url, params=params, headers=HK_EM_HEADERS)


def _collect_pages(params: dict) -> pd.DataFrame:
    """第 1 页解析 pagerbox 得总页数后逐页抓取（`&page=` 参数无效，源验证 §1）。"""
    p1 = _fetch_page_text(1, params)
    frames = [parse_sellshort_html(p1)]
    for p in range(2, _max_page(p1) + 1):
        frames.append(parse_sellshort_html(_fetch_page_text(p, params)))
    return pd.concat([f for f in frames if not f.empty], ignore_index=True)


def fetch_sellshort_day(date_str: str) -> pd.DataFrame:
    """单日全市场（股票口径）卖空。非交易日返回空 DataFrame，不抛错。"""
    ds = pd.Timestamp(date_str).strftime("%Y-%m-%d")
    out = _collect_pages({"code": "", "sdate": ds, "edate": ds})
    if not out.empty:
        out = out[out["source_date"] == ds].reset_index(drop=True)
    if not out.empty:
        out["trade_date"] = pd.Timestamp(date_str)
    return out


def fetch_sellshort_stock(code: str, start, end) -> pd.DataFrame:
    """单只股票区间历史：一次区间查询跨日翻页（行内自带日期列，每页 50 行）。"""
    out = _collect_pages({
        "code": code,
        "sdate": pd.Timestamp(start).strftime("%Y-%m-%d"),
        "edate": pd.Timestamp(end).strftime("%Y-%m-%d"),
    })
    if not out.empty:
        out["trade_date"] = pd.to_datetime(out["source_date"])
    return out


def fetch_kline(secid: str, beg, end, *, now: pd.Timestamp | None = None) -> pd.DataFrame:
    """日 K（不复权）。丢弃未完成当日 K 线（16:10 HKT 前，源验证 §5）。"""
    j = http_client.fetch_json(
        "https://push2his.eastmoney.com/api/qt/stock/kline/get",
        params={
            "secid": secid,
            "fields1": "f1,f2,f3",
            "fields2": "f51,f52,f53,f54,f55,f56,f57",
            "klt": "101", "fqt": "0",
            "beg": pd.Timestamp(beg).strftime("%Y%m%d"),
            "end": pd.Timestamp(end).strftime("%Y%m%d"),
        },
        headers=HK_EM_HEADERS,
        validate=lambda j: bool(j.get("data") and j["data"].get("klines")),
    )
    rows = []
    for line in j["data"]["klines"]:
        d, o, c, h, low, v, a = line.split(",")
        rows.append({"secid": secid, "trade_date": pd.Timestamp(d),
                     "open": float(o), "close": float(c), "high": float(h),
                     "low": float(low), "volume": float(v), "amount": float(a)})
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    ts_now = now if now is not None else pd.Timestamp.now(tz="Asia/Shanghai")
    ts_now = ts_now.tz_convert("Asia/Shanghai").tz_localize(None) if ts_now.tzinfo \
        else ts_now
    last = df.iloc[-1]
    if (last["trade_date"] == ts_now.normalize()
            and ts_now.hour * 60 + ts_now.minute < 16 * 60 + 10):
        df = df.iloc[:-1]
    return df.reset_index(drop=True)


def fetch_total_shares(code: str) -> int:
    """总股本（f84，当前快照值；PIT 语义见 loaders.load_total_shares）。"""
    j = http_client.fetch_json(
        "https://push2.eastmoney.com/api/qt/stock/get",
        params={"secid": f"116.{code}", "fields": "f84", "fltt": "2", "invt": "2"},
        headers=HK_EM_HEADERS,
        validate=lambda j: j.get("data") and j["data"].get("f84") is not None,
    )
    return int(j["data"]["f84"])
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/flow_dashboard/test_hk_em_client.py -v`
Expected: 7 passed（6 个原测试 + f84 快照测试，质量评审补；原文"5"为计划笔误）

**勘误（质量评审加固，实施时保留）**：
1. `SELLSHORT_ROW_RE` 行内通配由 `.*?` 收紧为 `(?:(?!</tr>).)*?`——防止页面格式漂移时正则回溯跨行拼接（代码取自第 i 行、数值取自第 i+1 行的静默错配）；正常路径行为不变。
2. `fetch_sellshort_day` 在盖 `trade_date` 戳前先按 `source_date == ds` 过滤——防止接口返回相邻日行被错标为请求日。
3. 补 `test_fetch_total_shares_pins_secid_and_validation`：钉死 `116.` secid 前缀、f84 字段、validate 对限流 `data:null` 的拒绝。

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/data/hk_short/em_client.py tests/flow_dashboard/test_hk_em_client.py
git commit -m "feat(hk-short): eastmoney sellshort/kline/shares client with validated parsers"
```

---

### Task 5: hkex_client.py HKEX 客户端

**Files:**
- Create: `src/flow_dashboard/data/hk_short/hkex_client.py`
- Test: `tests/flow_dashboard/test_hk_hkex_client.py`

源验证 §2/§6 要点：dayquot 归档 `d{YYMMDD}e.htm`（滚动 ~61 自然日，节假日 404）；段内文本被 `<pre><font>` 切块、名称含 `&amp;`、行首杂散 `%`；PREVIOUS DAY'S ADJUSTED 段提供 T-1 修正；ashtmain 仅当日；LOS xlsx 用 zipfile+re 解析 inline strings，表头第 3 行，A2 为生效日期。

- [ ] **Step 1: 写失败测试**

```python
"""hkex_client：dayquot 段解析（含切块/&amp;/杂散%）、LOS xlsx 解析。"""
import io
import zipfile

import pandas as pd
import pytest

from flow_dashboard.data.hk_short import hkex_client

# 模拟真实坑：段内 <pre><font> 切块、&amp;、行首 %、千分位数字
DAYQUOT_FIXTURE = """<html><body>
<h3>MARKET HIGHLIGHTS</h3>
<h3>SHORT SELLING TURNOVER - DAILY REPORT</h3>
<pre><font size='1'>
   1 CKH HOLDINGS            1,090,000      74,273,675     8,613,270      640,508,607
   2 YOFC &amp; CO            12,500         312,500        90,000        4,500,000
%  3 TOM GROUP LTD           5,000          10,000         3,000         1,500,000
</font></pre><pre><font size='1'>
   4 WH GROUP                8,000          20,000         2,000         1,000,000
</font></pre>
<h3>PREVIOUS DAY'S ADJUSTED SHORT SELLING TURNOVER</h3>
<pre><font size='1'>
   1 CKH HOLDINGS            1,100,000      75,000,000     8,600,000      640,000,000
</font></pre>
</body></html>"""


def test_parse_dayquot_daily_and_adjusted():
    daily, prev = hkex_client.parse_dayquot(
        DAYQUOT_FIXTURE, data_date="2026-09-18",
        prev_date="2026-09-17")
    assert len(daily) == 4
    assert len(prev) == 1  # 段尾无固定边界，靠行正则特异性截住
    r = daily[daily["code"] == "00002"].iloc[0]
    assert r["name"] == "YOFC & CO"          # &amp; 已 unescape
    assert r["short_shares"] == 12500.0
    assert r["short_amount"] == 312500.0
    assert r["turnover"] == 4500000.0
    assert r["trade_date"] == pd.Timestamp("2026-09-18")
    assert daily.iloc[2]["code"] == "00003"  # 行首 % 已清除，行仍解析
    rp = prev.iloc[0]
    assert rp["code"] == "00001"
    assert rp["short_shares"] == 1100000.0  # 修正值
    assert rp["trade_date"] == pd.Timestamp("2026-09-17")


def test_parse_dayquot_missing_section_returns_empty():
    daily, prev = hkex_client.parse_dayquot("<html>nothing</html>",
                                            "2026-09-18", "2026-09-17")
    assert daily.empty and prev.empty


def _build_los_xlsx() -> bytes:
    sheet = (
        '<?xml version="1.0"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>"
        '<x:row r="1"><x:c r="A1"><x:v>List of Securities</x:v></x:c></x:row>'
        '<x:row r="2"><x:c r="A2"><x:v>Updated as at 21/09/2026</x:v></x:c></x:row>'
        '<x:row r="3"><x:c r="A3"><x:v>Stock Code</x:v></x:c>'
        '<x:c r="B3"><x:v>Name</x:v></x:c><x:c r="C3"><x:v>Category</x:v></x:c>'
        '<x:c r="D3"><x:v>Sub-Category</x:v></x:c></x:row>'
        '<x:row r="4"><x:c r="A4" t="str"><x:v>700</x:v></x:c>'
        '<x:c r="B4" t="str"><x:v>TENCENT</x:v></x:c>'
        '<x:c r="C4" t="str"><x:v>Equity</x:v></x:c>'
        '<x:c r="D4" t="str"><x:v>Securities</x:v></x:c></x:row>'
        '<x:row r="5"><x:c r="A5" t="str"><x:v>2800</x:v></x:c>'
        '<x:c r="B5" t="str"><x:v>TRACKER FUND</x:v></x:c>'
        '<x:c r="C5" t="str"><x:v>Exchange Traded Products</x:v></x:c>'
        '<x:c r="D5" t="str"><x:v>ETF</x:v></x:c></x:row>'
        "</sheetData></worksheet>"
    ).encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    return buf.getvalue()


def test_parse_list_of_securities():
    df, eff = hkex_client.parse_list_of_securities(_build_los_xlsx())
    assert eff == "Updated as at 21/09/2026"
    assert len(df) == 2
    r = df[df["code"] == "02800"].iloc[0]
    assert r["category"] == "Exchange Traded Products"
    assert set(hkex_client.etf_set(df)) == {"02800"}
    assert hkex_client.reit_set(df) == set()


class _Resp:
    def __init__(self, text="", status=200):
        self.status_code = status
        self.text = text


def test_fetch_dayquot_three_state_contract(monkeypatch):
    # 404 → None（非交易日/超出 ~61 天滚动窗口的探测语义）
    monkeypatch.setattr(hkex_client.http_client, "try_get", lambda url, **k: None)
    assert hkex_client.fetch_dayquot("2026-09-18") is None
    # 200 但两段皆无数据行 → 空 DataFrame（不是 None——loader 语义区分）
    monkeypatch.setattr(hkex_client.http_client, "try_get",
                        lambda url, **k: _Resp(text="<html>nothing</html>"))
    out = hkex_client.fetch_dayquot("2026-09-18")
    assert out is not None and out.empty
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/flow_dashboard/test_hk_hkex_client.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

```python
"""HKEX 官方客户端：dayquot/ashtmain 全口径卖空、ListOfSecurities 主表。

源验证 §2：单文件 ~26MB；SHORT SELLING 段被 <pre><font> 切块、含 &amp;、
行首杂散 %；PREVIOUS DAY'S ADJUSTED 段为 T-1 修正（loader 必须覆盖 T-1 缓存）。
"""
from __future__ import annotations

import html
import io
import logging
import re
import zipfile

import pandas as pd

from flow_dashboard.config import HKEX_HEADERS
from flow_dashboard.data.hk_short import http_client
from flow_dashboard.data.hk_short.hk_calendar import prev_trading_day

log = logging.getLogger(__name__)

DAYQUOT_URL = "https://www.hkex.com.hk/eng/stat/smstat/dayquot/d{yymmdd}e.htm"
ASHTMAIN_URL = "https://www.hkex.com.hk/eng/stat/smstat/ssturnover/ncms/ashtmain.htm"
LOS_URL = ("https://www.hkex.com.hk/eng/services/trading/securities/"
           "securitieslists/ListOfSecurities.xlsx")

_HDR_DAILY = "SHORT SELLING TURNOVER - DAILY REPORT"
_HDR_ADJUSTED = "PREVIOUS DAY'S ADJUSTED SHORT SELLING TURNOVER"

_ROW_RE = re.compile(
    r"^\s*(\d{1,5})\s+(\S.*?)\s{2,}([\d,]+)\s+([\d,]+)\s+([\d,]+)\s+([\d,]+)\s*$",
    re.M,
)

_LOS_ROW_RE = re.compile(r"<x:row [^>]*>(.*?)</x:row>", re.S)
_LOS_CELL_RE = re.compile(
    r'<x:c r="([A-Z]+)\d+"[^>]*?(?: t="(\w+)")?[^>]*>(.*?)</x:c>', re.S)


def _clean_section(seg: str) -> str:
    text = html.unescape(re.sub(r"<[^>]+>", "", seg))
    return re.sub(r"[ \t]*\n[ \t]*%?", "\n", text)


def _section(html_text: str, header: str, end_markers: list[str]) -> str:
    i = html_text.find(header)
    if i < 0:
        return ""
    j = len(html_text)
    for em in end_markers:
        k = html_text.find(em, i + len(header))
        if k > 0:
            j = min(j, k)
    return html_text[i:j]


def _rows_from_section(sec: str) -> pd.DataFrame:
    rows = []
    for m in _ROW_RE.finditer(_clean_section(sec)):
        code, name, short_sh, short_amt, total_sh, total_amt = m.groups()
        rows.append({
            "code": code.zfill(5),
            "name": name.strip(),
            "short_shares": float(short_sh.replace(",", "")),
            "short_amount": float(short_amt.replace(",", "")),
            "total_shares_traded": float(total_sh.replace(",", "")),
            "turnover": float(total_amt.replace(",", "")),
        })
    return pd.DataFrame(rows)


def parse_dayquot(html_text: str, *, data_date: str, prev_date: str | None = None
                  ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """返回 (当日全口径逐证券, T-1 修正值)。prev_date 缺省用日历推。"""
    if prev_date is None:
        prev_date = prev_trading_day(data_date)
    daily = _rows_from_section(
        _section(html_text, _HDR_DAILY, [_HDR_ADJUSTED]))
    adjusted = _rows_from_section(
        _section(html_text, _HDR_ADJUSTED, []))  # 段尾无固定边界，靠行正则特异性
    if not daily.empty:
        daily["trade_date"] = pd.Timestamp(data_date)
    if not adjusted.empty:
        adjusted["trade_date"] = pd.Timestamp(prev_date)
    return daily, adjusted


def fetch_dayquot(date_str: str) -> pd.DataFrame | None:
    """归档文件（404=超出滚动窗口或非交易日 → None）。返回合并了 T-1 修正的表。"""
    ts = pd.Timestamp(date_str)
    html_text = http_client.try_get(
        DAYQUOT_URL.format(yymmdd=ts.strftime("%y%m%d")), headers=HKEX_HEADERS)
    if html_text is None:
        return None
    daily, adjusted = parse_dayquot(html_text.text, data_date=date_str)
    frames = [f for f in (daily, adjusted) if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def fetch_ashtmain(data_date: str) -> pd.DataFrame:
    """当日盘后汇总（归档生成前的当日版本，ncms 仅保留当日）。"""
    resp = http_client.try_get(ASHTMAIN_URL, headers=HKEX_HEADERS)
    if resp is None:
        return pd.DataFrame()
    daily, adjusted = parse_dayquot(resp.text, data_date=data_date)
    frames = [f for f in (daily, adjusted) if not f.empty]
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def parse_list_of_securities(xlsx_bytes: bytes) -> tuple[pd.DataFrame, str]:
    """zipfile+re 解析（inline strings，无 sharedStrings，源验证 §6）。"""
    with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as z:
        xml = z.read("xl/worksheets/sheet1.xml").decode("utf-8", "ignore")
    raw_rows = []
    for rm in _LOS_ROW_RE.finditer(xml):
        cells: dict[str, str] = {}
        for cm in _LOS_CELL_RE.finditer(rm.group(1)):
            col, _t, inner = cm.groups()
            vm = re.search(r"<x:v>(.*?)</x:v>", inner, re.S)
            if vm:
                cells[col] = html.unescape(vm.group(1)).strip()
        raw_rows.append(cells)
    eff = ""
    if len(raw_rows) >= 2 and "A" in raw_rows[1]:
        eff = raw_rows[1]["A"]
    rows = []
    for r in raw_rows:
        code = r.get("A", "")
        if code.isdigit() and len(code) <= 5:
            rows.append({"code": code.zfill(5), "name": r.get("B", ""),
                         "category": r.get("C", ""),
                         "sub_category": r.get("D", "")})
    return pd.DataFrame(rows), eff


def fetch_list_of_securities() -> tuple[pd.DataFrame, str]:
    resp = http_client.try_get(LOS_URL, headers=HKEX_HEADERS)
    if resp is None:
        return pd.DataFrame(), ""
    return parse_list_of_securities(resp.content)


def etf_set(los_df: pd.DataFrame) -> set[str]:
    """冻结规则：ETF 集合 = Category == 'Exchange Traded Products'（含 L&I）。"""
    if los_df.empty:
        return set()
    return set(los_df.loc[los_df["category"] == "Exchange Traded Products", "code"])


def reit_set(los_df: pd.DataFrame) -> set[str]:
    if los_df.empty:
        return set()
    return set(los_df.loc[los_df["category"] == "Real Estate Investment Trusts", "code"])
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/flow_dashboard/test_hk_hkex_client.py -v`
Expected: 4 passed

注意：测试里 prev 段断言 3 行是因为 fixture 中 prev 段后无其他 6 字段数字行；真实文件若 prev 段之后存在同构表格，靠 `_ROW_RE` 特异性（代码+名称+4 个千分位数字）过滤——上线时用 Task 16 的 @live 测试核验行数在 700–900 区间。

**勘误（质量评审加固，实施时保留）**：
1. `test_parse_dayquot_missing_section_returns_empty` 的调用改为关键字参数（`data_date=..., prev_date=...`）——原文位置调用与 keyword-only 签名冲突，签名是冻结契约（Task 7 依赖）。
2. 补 `test_fetch_dayquot_three_state_contract`：钉死 404→None / 200 空段→空表 的三态契约（Task 7 loader 依赖 None 与空表的区分）；同时使 "Expected: 4 passed" 计数成立（原文 3 个测试，计划笔误）。

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/data/hk_short/hkex_client.py tests/flow_dashboard/test_hk_hkex_client.py
git commit -m "feat(hk-short): hkex dayquot/ashtmain parser + list-of-securities master"
```

---

### Task 6: sfc_client.py SFC 周报客户端

**Files:**
- Create: `src/flow_dashboard/data/hk_short/sfc_client.py`
- Test: `tests/flow_dashboard/test_hk_sfc_client.py`

源验证 §4：URL = `.../spr/{发布年}/{月}/{日}/Short_Position_Reporting_Aggregated_Data_{报告期YYYYMMDD}.csv`；路径日期=实际公布日（通常 position_date+7 天的周五，假日周漂移）；`Last-Modified` 响应头 = 公布时间证据；CSV `Date` 为 DD/MM/YYYY、代码无前导零。

- [ ] **Step 1: 写失败测试**

```python
"""sfc_client：候选 URL 探测、Last-Modified→published_at、CSV 解析。"""
import pandas as pd

from flow_dashboard.data.hk_short import sfc_client

CSV_BODY = (
    "Date,Stock Code,Stock Name,Aggregated Reportable Short Positions (Shares),"
    "Aggregated Reportable Short Positions (HK$)\n"
    "11/09/2026,1,CKH HOLDINGS,48162045,3315956798\n"
    "11/09/2026,700,TENCENT,91234567,28738234567\n"
)


class _Resp:
    def __init__(self, content, last_modified=None):
        self.status_code = 200
        self.content = content
        self.headers = {"Last-Modified": last_modified} if last_modified else {}


def test_candidate_pub_dates_centered_on_plus7():
    cands = sfc_client.candidate_pub_dates(pd.Timestamp("2026-09-11"))
    assert cands[0] == pd.Timestamp("2026-09-18")  # 正常周五公布
    assert all(c.weekday() == 4 for c in cands[:1])
    assert len(cands) >= 6                          # 假日周漂移余量


def test_fetch_sfc_week_parses_and_stamps(monkeypatch):
    state = {"n": 0}

    def fake_try_get(url, headers=None, **k):
        state["n"] += 1
        if "2026/09/18" in url:  # 首个候选命中
            return _Resp(CSV_BODY.encode(), "Fri, 18 Sep 2026 07:41:00 GMT")
        return None

    monkeypatch.setattr(sfc_client.http_client, "try_get", fake_try_get)
    df = sfc_client.fetch_sfc_week(
        pd.Timestamp("2026-09-11"),
        fetched_at=pd.Timestamp("2026-09-18 18:45", tz="Asia/Shanghai"))
    assert state["n"] == 1
    assert len(df) == 2
    r = df[df["code"] == "00700"].iloc[0]
    assert r["short_shares"] == 91234567
    assert r["short_amount_hkd"] == 28738234567.0
    assert r["position_date"] == pd.Timestamp("2026-09-11")
    assert r["name"] == "TENCENT"
    # published_at 来自 Last-Modified（UTC → tz-aware）
    assert r["published_at"] == pd.Timestamp("2026-09-18 15:41:00", tz="Asia/Shanghai")
    assert r["available_at"] == r["published_at"]


def test_fetch_sfc_week_returns_none_when_all_404(monkeypatch):
    monkeypatch.setattr(sfc_client.http_client, "try_get",
                        lambda url, headers=None, **k: None)
    out = sfc_client.fetch_sfc_week(
        pd.Timestamp("2026-12-25"),
        fetched_at=pd.Timestamp("2027-01-02 18:45", tz="Asia/Shanghai"))
    assert out is None  # 假日周无报告（源验证 §4）
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/flow_dashboard/test_hk_sfc_client.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

```python
"""SFC 周度须申报淡仓 CSV 客户端（权威独占，源验证 §4）。

PIT 铁律：available_at = published_at（响应 Last-Modified）；header 不可得时
退化为 first_observed_at；绝不按 position_date + 固定天数倒推。
"""
from __future__ import annotations

import email.utils
import io
import logging
from datetime import timedelta

import pandas as pd

from flow_dashboard.config import HKEX_HEADERS
from flow_dashboard.data.hk_short import http_client

log = logging.getLogger(__name__)

URL_TMPL = ("https://www.sfc.hk/-/media/EN/pdf/spr/{y}/{m:02d}/{d:02d}/"
            "Short_Position_Reporting_Aggregated_Data_{pos:%Y%m%d}.csv")

_RENAME = {
    "Date": "report_date",
    "Stock Code": "code_raw",
    "Stock Name": "name",
    "Aggregated Reportable Short Positions (Shares)": "short_shares",
    "Aggregated Reportable Short Positions (HK$)": "short_amount_hkd",
}


def candidate_pub_dates(position_date) -> list[pd.Timestamp]:
    """正常公布日 = position_date+7（周五）；假日周向前后漂移，按可能性排序。"""
    base = pd.Timestamp(position_date) + pd.Timedelta(days=7)
    return [base + timedelta(days=o) for o in (0, 1, -1, 2, 3, -2, 4, 5)]


def _parse_last_modified(value: str | None) -> pd.Timestamp | None:
    if not value:
        return None
    dt = email.utils.parsedate_to_datetime(value)  # tz-aware (UTC)
    return pd.Timestamp(dt).tz_convert("Asia/Shanghai")


def parse_sfc_csv(content: bytes) -> pd.DataFrame:
    df = pd.read_csv(io.BytesIO(content))
    df.columns = [c.strip() for c in df.columns]
    df = df.rename(columns=_RENAME)
    df["code"] = df["code_raw"].astype(int).astype(str).str.zfill(5)
    df["position_date"] = pd.to_datetime(df["report_date"], format="%d/%m/%Y")
    return df[["code", "name", "position_date", "short_shares", "short_amount_hkd"]]


def fetch_sfc_week(position_date, *, fetched_at: pd.Timestamp) -> pd.DataFrame | None:
    """抓取某 position_date 一期报告；所有候选 404 → None（假日周/未公布）。"""
    for pub in candidate_pub_dates(position_date):
        url = URL_TMPL.format(y=pub.year, m=pub.month, d=pub.day,
                              pos=pd.Timestamp(position_date))
        resp = http_client.try_get(url, headers=HKEX_HEADERS, timeout=120)
        if resp is None:
            continue
        df = parse_sfc_csv(resp.content)
        published_at = _parse_last_modified(resp.headers.get("Last-Modified"))
        available_at = published_at if published_at is not None else fetched_at
        df["published_at"] = published_at
        df["first_observed_at"] = fetched_at
        df["available_at"] = available_at
        df["source_date"] = pd.Timestamp(position_date)
        df["fetched_at"] = fetched_at
        df["source"] = "sfc"
        df["source_version"] = "sfc_spr_csv_v1"
        return df
    return None
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/flow_dashboard/test_hk_sfc_client.py -v`
Expected: 4 passed

**勘误（质量评审加固，实施时保留）**：
1. 参考实现中 `df["published_at"] = published_at` 在 Last-Modified 头缺失时（published_at=None）会产生 object 列——与正常周的 tz-aware 列 concat 后 dtype 漂移，威胁 Task 7 parquet 缓存 schema。改为 `pd.Series([published_at if published_at is not None else pd.NaT] * len(df), dtype="datetime64[ns, Asia/Shanghai]")`，published_at 列恒为 tz-aware（缺失=NaT）。
2. 补 `test_fetch_sfc_week_missing_last_modified_falls_back`：钉死 header 缺失时 published_at=NaT（tz-aware dtype）、available_at 退化 fetched_at——使 "Expected: 4 passed" 计数成立（原文 3 个测试）。

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/data/hk_short/sfc_client.py tests/flow_dashboard/test_hk_sfc_client.py
git commit -m "feat(hk-short): sfc weekly csv client with published_at from last-modified"
```

### Task 7: loaders.py 六个 PIT loader

**Files:**
- Create: `src/flow_dashboard/data/hk_short/loaders.py`
- Test: `tests/flow_dashboard/test_hk_loaders.py`

契约（设计 §5 + 源验证 §8）：读 parquet 缓存 → 按日历+available 偏移算应入库的最新交易日 → 补增量 → `_merge`（新值覆盖、first_observed_at 保留最早、available_at 晚者胜）→ 写回 → `_pit` 过滤。所有 available_at 一律 tz-aware Asia/Shanghai：东财日频=trade_date+16:10；HKEX=公布文件日+17:30（restated 修正行 available_at=**修正公布日**，不是原数据日）；SFC=published_at；f84/LOS 快照=fetched_at。单日/单次抓取失败 try/except 记 warning 跳过，绝不抛错阻塞发布（设计 §5"抓取失败保留缓存旧数据"）。

- [ ] **Step 1: 写失败测试**

```python
"""hk_short loaders：增量合并、PIT 过滤、restated 覆盖、SFC 负缓存。"""
import pandas as pd

from flow_dashboard.data.hk_short import loaders
from flow_dashboard.data.hk_short.loaders import (
    load_em_sellshort, load_em_days_covered, load_hkex_dayquot,
    load_sfc_weekly, load_hk_kline, load_total_shares,
)

FETCHED = pd.Timestamp("2026-09-18 19:00:00", tz="Asia/Shanghai")


def _em_day(d, n=2):
    return pd.DataFrame({
        "code": ["00700", "09988"][:n],
        "name": ["腾讯控股", "阿里巴巴-W"][:n],
        "trade_date": pd.Timestamp(d),
        "short_shares": [100.0, 200.0][:n],
        "short_avg_price": [300.0, 100.0][:n],
        "short_amount": [3e7, 2e7][:n],
        "turnover": [3e9, 2e9][:n],
        "ssr_pct": [1.0, 1.0][:n],
        "source_date": [pd.Timestamp(d)] * n,
    })


def test_em_full_day_fetch_marks_full_and_pit(tmp_path, monkeypatch):
    calls = []

    def fake_day(d):
        calls.append(str(pd.Timestamp(d).date()))
        return _em_day(d)

    monkeypatch.setattr(loaders.em_client, "fetch_sellshort_day", fake_day)
    out = load_em_sellshort(as_of=FETCHED, start="2026-09-16", cache_dir=tmp_path)
    assert calls == ["2026-09-16", "2026-09-17", "2026-09-18"]  # 全是交易日
    days = load_em_days_covered(as_of=FETCHED, cache_dir=tmp_path)
    assert [str(d.date()) for d in days] == ["2026-09-16", "2026-09-17", "2026-09-18"]
    assert out["trade_date"].max() == pd.Timestamp("2026-09-18")  # 19:00 > 16:10 可见
    early = load_em_sellshort(
        as_of=pd.Timestamp("2026-09-18 10:00", tz="Asia/Shanghai"),
        allow_fetch=False, cache_dir=tmp_path)
    assert early["trade_date"].max() == pd.Timestamp("2026-09-17")  # PIT 截断当日


def test_em_no_refetch_when_fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(loaders.em_client, "fetch_sellshort_day", lambda d: _em_day(d))
    # 先把默认窗口（expected-14d = 09-04）补满 full
    load_em_sellshort(as_of=FETCHED, start="2026-09-04", cache_dir=tmp_path)

    def boom(d):
        raise AssertionError("covered full day must not be refetched")

    monkeypatch.setattr(loaders.em_client, "fetch_sellshort_day", boom)
    out = load_em_sellshort(as_of=FETCHED, cache_dir=tmp_path)  # 窗口内全部 full → 零抓取
    assert (out["trade_date"] == pd.Timestamp("2026-09-18")).any()


def test_em_stock_range_marks_partial(tmp_path, monkeypatch):
    monkeypatch.setattr(loaders.em_client, "fetch_sellshort_day",
                        lambda d: _em_day(d, n=1))
    load_em_sellshort(as_of=FETCHED, start="2026-09-18", cache_dir=tmp_path)  # 18 日 full

    got = {}

    def fake_stock(code, s, e):
        got["code"] = code
        df = _em_day("2026-09-17", n=1)
        df["code"] = code
        return df

    monkeypatch.setattr(loaders.em_client, "fetch_sellshort_stock", fake_stock)
    load_em_sellshort(as_of=FETCHED, codes=["0700.HK"],
                      start="2026-09-10", cache_dir=tmp_path)
    assert got["code"] == "00700"  # '0700.HK' → 5 位数字代码
    days = load_em_days_covered(as_of=FETCHED, cache_dir=tmp_path)
    assert [str(d.date()) for d in days] == ["2026-09-18"]  # partial 日绝不入 full 集合
    cached = load_em_sellshort(as_of=FETCHED, allow_fetch=False, cache_dir=tmp_path)
    assert ((cached["code"] == "00700")
            & (cached["trade_date"] == pd.Timestamp("2026-09-17"))).any()


def test_hkex_restated_override(tmp_path, monkeypatch):
    def fake_dayquot(d):
        daily = pd.DataFrame({
            "code": ["00001"], "name": ["CKH"],
            "trade_date": [pd.Timestamp("2026-09-18")],
            "short_shares": [1090000.0], "short_amount": [74273675.0],
            "total_shares_traded": [8613270.0], "turnover": [640508607.0],
        })
        adjusted = daily.copy()
        adjusted["trade_date"] = pd.Timestamp("2026-09-17")
        adjusted["short_shares"] = [1100000.0]  # T-1 修正值
        return pd.concat([daily, adjusted], ignore_index=True)

    monkeypatch.setattr(loaders.hkex_client, "fetch_dayquot", fake_dayquot)
    out = load_hkex_dayquot(as_of=FETCHED, start="2026-09-18", cache_dir=tmp_path)
    r18 = out[(out["code"] == "00001")
              & (out["trade_date"] == pd.Timestamp("2026-09-18"))].iloc[0]
    r17 = out[(out["code"] == "00001")
              & (out["trade_date"] == pd.Timestamp("2026-09-17"))].iloc[0]
    assert r18["quality_flags"] == ""
    assert r17["quality_flags"] == "restated"
    # restated 行 available_at = 公布日 17:30（非数据日）——17 日 18:00 还看不到修正
    assert r17["available_at"] == pd.Timestamp("2026-09-18 17:30", tz="Asia/Shanghai")
    early = load_hkex_dayquot(
        as_of=pd.Timestamp("2026-09-17 18:00", tz="Asia/Shanghai"),
        allow_fetch=False, cache_dir=tmp_path)
    assert early.empty


def _sfc_one_week():
    pos = pd.Timestamp("2026-09-11")
    pub = pd.Timestamp("2026-09-18 15:41", tz="Asia/Shanghai")
    return pd.DataFrame({
        "code": ["00700"], "name": ["TENCENT"], "position_date": [pos],
        "short_shares": [9.1e7], "short_amount_hkd": [2.87e10],
        "published_at": [pub], "first_observed_at": [FETCHED],
        "available_at": [pub], "source_date": [pos], "fetched_at": [FETCHED],
        "source": ["sfc"], "source_version": ["sfc_spr_csv_v1"],
    })


def test_sfc_skip_cached_and_negative_cache(tmp_path, monkeypatch):
    loaders._write(_sfc_one_week(), tmp_path / loaders.SFC_FILE)
    probed = []

    def fake_fetch(pos_date, fetched_at=None):
        probed.append(pd.Timestamp(pos_date))
        return None  # 全候选 404：假日周/未公布

    monkeypatch.setattr(loaders.sfc_client, "fetch_sfc_week", fake_fetch)
    as_of = pd.Timestamp("2026-09-21 19:00", tz="Asia/Shanghai")
    out = load_sfc_weekly(as_of=as_of, weeks=3, cache_dir=tmp_path)
    # 09-21(周一) 的最近已完成周：09-18、09-11、09-04；09-11 已缓存不重抓
    assert set(probed) == {pd.Timestamp("2026-09-18"), pd.Timestamp("2026-09-04")}
    assert (out["position_date"] == pd.Timestamp("2026-09-11")).any()
    probed.clear()
    load_sfc_weekly(as_of=as_of, weeks=3, cache_dir=tmp_path)
    assert probed == []  # 负缓存 14 天内不重试


def test_sfc_pit_visibility(tmp_path):
    loaders._write(_sfc_one_week(), tmp_path / loaders.SFC_FILE)
    before = load_sfc_weekly(
        as_of=pd.Timestamp("2026-09-18 15:00", tz="Asia/Shanghai"),
        allow_fetch=False, cache_dir=tmp_path)
    after = load_sfc_weekly(
        as_of=pd.Timestamp("2026-09-18 16:00", tz="Asia/Shanghai"),
        allow_fetch=False, cache_dir=tmp_path)
    assert before.empty and not after.empty  # published_at 是 PIT 唯一依据


def test_kline_incremental(tmp_path, monkeypatch):
    cached = pd.DataFrame({
        "secid": ["100.HSI"], "trade_date": [pd.Timestamp("2026-09-17")],
        "open": [1.0], "close": [1.0], "high": [1.0], "low": [1.0],
        "volume": [1.0], "amount": [1.0],
        "source_date": [pd.Timestamp("2026-09-17")],
        "first_observed_at": [FETCHED],
        "available_at": [pd.Timestamp("2026-09-17 16:10", tz="Asia/Shanghai")],
        "fetched_at": [FETCHED], "source": ["eastmoney"],
        "source_version": ["em_kline_v1"], "quality_flags": [""],
    })
    loaders._write(cached, tmp_path / loaders.KLINE_FILE)
    calls = []

    def fake_kline(secid, beg, end, now=None):
        calls.append((str(pd.Timestamp(beg).date()), str(pd.Timestamp(end).date())))
        return pd.DataFrame({
            "secid": [secid], "trade_date": [pd.Timestamp("2026-09-18")],
            "open": [2.0], "close": [2.0], "high": [2.0], "low": [2.0],
            "volume": [2.0], "amount": [2.0],
        })

    monkeypatch.setattr(loaders.em_client, "fetch_kline", fake_kline)
    out = load_hk_kline(as_of=FETCHED, secids=["100.HSI"], cache_dir=tmp_path)
    assert calls == [("2026-09-18", "2026-09-18")]  # 只补增量
    assert set(out["trade_date"]) == {pd.Timestamp("2026-09-17"),
                                      pd.Timestamp("2026-09-18")}


def test_total_shares_snapshot_no_refetch(tmp_path, monkeypatch):
    calls = {"n": 0}

    def fake_f84(c):
        calls["n"] += 1
        return 9095085993

    monkeypatch.setattr(loaders.em_client, "fetch_total_shares", fake_f84)
    out = load_total_shares(as_of=FETCHED, codes=["0700.HK"], cache_dir=tmp_path)
    assert len(out) == 1 and out.iloc[0]["total_shares"] == 9095085993.0
    load_total_shares(as_of=FETCHED, codes=["0700.HK"], cache_dir=tmp_path)
    assert calls["n"] == 1  # 已有快照不重抓（refresh=True 才刷新）


def test_etf_master_weekly_refresh(tmp_path, monkeypatch):
    los = pd.DataFrame({
        "code": ["02800"], "name": ["TRACKER FUND"],
        "category": ["Exchange Traded Products"], "sub_category": ["ETF"],
    })
    calls = {"n": 0}

    def fake_los():
        calls["n"] += 1
        return los.copy(), "Updated as at 21/09/2026"

    monkeypatch.setattr(loaders.hkex_client, "fetch_list_of_securities", fake_los)
    df, eff = loaders.load_etf_master(as_of=FETCHED, cache_dir=tmp_path)
    assert calls["n"] == 1 and eff == pd.Timestamp("2026-09-21")
    assert set(df["code"]) == {"02800"}
    loaders.load_etf_master(as_of=FETCHED, cache_dir=tmp_path)
    assert calls["n"] == 1  # 7 天内不重抓
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/flow_dashboard/test_hk_loaders.py -v`
Expected: FAIL（ModuleNotFoundError / ImportError: loaders）

- [ ] **Step 3: 实现**

```python
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
    if df.empty:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, index=False)


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
        prior = (old[keys + ["first_observed_at"]]
                 .drop_duplicates(subset=keys)
                 .rename(columns={"first_observed_at": "_first_obs"}))
        new = new.merge(prior, on=keys, how="left")
        if "first_observed_at" in new.columns:
            new["first_observed_at"] = new["_first_obs"].fillna(new["first_observed_at"])
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
    return (out.drop_duplicates(subset="trade_date", keep="first", ignore_index=True)
              .drop(columns="_p"))


def _annotate(df: pd.DataFrame, *, source: str, version: str,
              available_at, fetched_at, quality_flags=None) -> pd.DataFrame:
    out = df.copy()
    out["source"] = source
    out["source_version"] = version
    out["fetched_at"] = fetched_at
    out["available_at"] = (list(available_at)
                           if isinstance(available_at, (list, pd.Series))
                           else available_at)
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


def load_em_sellshort(*, as_of, start=None, end=None, codes=None,
                      allow_fetch=True, cache_dir=None) -> pd.DataFrame:
    """codes=None：全市场逐日增量（标 full）；codes 指定：个股区间补历史（标 partial）。"""
    cdir = Path(cache_dir) if cache_dir else HK_SHORT_CACHE_DIR
    as_of_ts = _as_of_ts(as_of)
    path, days_path = cdir / EM_FILE, cdir / DAYS_FILE
    cached, days_df = _read(path), _read(days_path)
    expected = _expected_latest(as_of_ts, EM_AVAILABLE)

    if codes is None:
        full = (set(pd.to_datetime(days_df.loc[days_df["coverage"] == "full", "trade_date"]))
                if not days_df.empty else set())
        lo = (pd.Timestamp(start).normalize() if start
              else (expected - pd.Timedelta(days=14) if expected else None))
        hi = pd.Timestamp(end).normalize() if end else expected
        targets = ([d for d in _trading_days_between(lo, hi) if d not in full]
                   if lo is not None and hi is not None else [])
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
            day = _annotate(day, source="eastmoney", version="em_sellshort_html_v1",
                            available_at=_em_avail(d), fetched_at=as_of_ts)
            day["trade_date"] = pd.Timestamp(d)
            day["source_date"] = pd.Timestamp(d)
            frames.append(day)
        if frames:
            cached = _merge(cached, pd.concat(frames, ignore_index=True),
                            keys=["code", "trade_date"])
            _write(cached, path)
            new_days = pd.DataFrame({
                "trade_date": [f["trade_date"].iloc[0] for f in frames],
                "coverage": ["full"] * len(frames),
            })
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
                lo = pd.Timestamp(prev["trade_date"].max()).normalize() + pd.Timedelta(days=1)
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
            rng = _annotate(rng, source="eastmoney", version="em_sellshort_html_v1",
                            available_at=[_em_avail(t) for t in rng["trade_date"]],
                            fetched_at=as_of_ts)
            rng["source_date"] = pd.to_datetime(rng["source_date"])
            frames.append(rng)
        if frames:
            all_new = pd.concat(frames, ignore_index=True)
            cached = _merge(cached, all_new, keys=["code", "trade_date"])
            _write(cached, path)
            touched = sorted(set(pd.to_datetime(all_new["trade_date"])))
            new_days = pd.DataFrame({"trade_date": touched,
                                     "coverage": ["partial"] * len(touched)})
            days_df = _merge_days(days_df, new_days)
            _write(days_df, days_path)
    return _pit(cached, as_of_ts)


def load_em_days_covered(*, as_of, cache_dir=None) -> list[pd.Timestamp]:
    """已确认 full 覆盖的交易日（升序）——市场聚合只允许用这些天。"""
    cdir = Path(cache_dir) if cache_dir else HK_SHORT_CACHE_DIR
    days_df = _read(cdir / DAYS_FILE)
    if days_df.empty:
        return []
    return sorted(pd.to_datetime(days_df.loc[days_df["coverage"] == "full",
                                              "trade_date"]))


def load_hkex_dayquot(*, as_of, start=None, end=None,
                      allow_fetch=True, cache_dir=None) -> pd.DataFrame:
    cdir = Path(cache_dir) if cache_dir else HK_SHORT_CACHE_DIR
    as_of_ts = _as_of_ts(as_of)
    path = cdir / HKEX_FILE
    cached = _read(path)
    expected = _expected_latest(as_of_ts, HKEX_AVAILABLE)
    have = (set(pd.to_datetime(cached["source_date"]).unique())
            if not cached.empty else set())
    lo = (pd.Timestamp(start).normalize() if start
          else (expected - pd.Timedelta(days=10) if expected else None))
    hi = pd.Timestamp(end).normalize() if end else expected
    targets = ([d for d in _trading_days_between(lo, hi) if d not in have]
               if lo is not None and hi is not None else [])
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
        df_d = _annotate(df_d, source="hkex", version="hkex_dayquot_v1",
                         available_at=_hkex_avail(d), fetched_at=as_of_ts,
                         quality_flags=flags)
        df_d["source_date"] = pd.Timestamp(d)
        frames.append(df_d)
    if frames:
        cached = _merge(cached, pd.concat(frames, ignore_index=True),
                        keys=["code", "trade_date"])
        _write(cached, path)
    return _pit(cached, as_of_ts)


def load_sfc_weekly(*, as_of, weeks=8, allow_fetch=True, cache_dir=None) -> pd.DataFrame:
    cdir = Path(cache_dir) if cache_dir else HK_SHORT_CACHE_DIR
    as_of_ts = _as_of_ts(as_of)
    path, none_path = cdir / SFC_FILE, cdir / SFC_NONE_FILE
    cached, none_df = _read(path), _read(none_path)
    have = (set(pd.to_datetime(cached["position_date"]).unique())
            if not cached.empty else set())
    none_map = ({pd.Timestamp(r.position_date): pd.Timestamp(r.checked_at)
                 for r in none_df.itertuples()} if not none_df.empty else {})
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
            new_none.append({"position_date": pos,
                             "checked_at": as_of_ts.tz_localize(None)})
            continue
        frames.append(df_w)
    if frames:
        cached = _merge(cached, pd.concat(frames, ignore_index=True),
                        keys=["code", "position_date"])
        _write(cached, path)
    if new_none:
        none_df = _merge(none_df, pd.DataFrame(new_none), keys=["position_date"])
        _write(none_df, none_path)
    return _pit(cached, as_of_ts)


def load_hk_kline(*, as_of, secids, start=None, end=None,
                  allow_fetch=True, cache_dir=None) -> pd.DataFrame:
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
            lo = pd.Timestamp(prev["trade_date"].max()).normalize() + pd.Timedelta(days=1)
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
        k = _annotate(k, source="eastmoney", version="em_kline_v1",
                      available_at=[_em_avail(t) for t in k["trade_date"]],
                      fetched_at=as_of_ts)
        k["source_date"] = pd.to_datetime(k["trade_date"]).dt.normalize()
        frames.append(k)
    if frames:
        cached = _merge(cached, pd.concat(frames, ignore_index=True),
                        keys=["secid", "trade_date"])
        _write(cached, path)
    return _pit(cached, as_of_ts)


def load_total_shares(*, as_of, codes, refresh=False,
                      allow_fetch=True, cache_dir=None) -> pd.DataFrame:
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
        snap = _annotate(snap, source="eastmoney", version="em_f84_v1",
                         available_at=as_of_ts, fetched_at=as_of_ts)
        snap["source_date"] = _naive_sh(as_of_ts).normalize()
        frames.append(snap)
    if frames:
        cached = _merge(cached, pd.concat(frames, ignore_index=True),
                        keys=["code", "source_date"])
        _write(cached, path)
    if cached.empty:
        return cached
    latest = cached.drop_duplicates(subset=["code"], keep="last", ignore_index=True)
    return _pit(latest, as_of_ts)


def _parse_eff(eff_str: str):
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", eff_str or "")
    return pd.Timestamp(int(m.group(3)), int(m.group(2)), int(m.group(1))) if m else pd.NaT


def load_etf_master(*, as_of, allow_fetch=True, cache_dir=None):
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
            los = _annotate(los, source="hkex", version="hkex_los_v1",
                            available_at=as_of_ts, fetched_at=as_of_ts)
            los["source_date"] = _naive_sh(as_of_ts).normalize()
            los["effective_date"] = _parse_eff(eff)
            _write(los, path)
            return _pit(los, as_of_ts), _parse_eff(eff)
    eff = (pd.Timestamp(cached["effective_date"].iloc[0])
           if not cached.empty else pd.NaT)
    return _pit(cached, as_of_ts), eff
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/flow_dashboard/test_hk_loaders.py -v`
Expected: 11 passed（9 个原测试 + 负缓存过期 + SFC quality_flags，质量评审加固；原文"9"不含加固测试）

**勘误（质量评审加固，实施时保留，commit 2ac4ed7）**：
1. `_write` 改为原子写：先写 `path.with_suffix(path.suffix + ".tmp")` 再 `os.replace`——崩溃中断 to_parquet 会留下截断文件，使后续每次 `_read` 永久抛错、阻塞发布（Important）。
2. `test_hkex_restated_override` 预先种入 09-17 旧行后再抓取，钉死 `_merge` 三契约：新值覆盖（short_shares 1050000→1100000）、`first_observed_at` 保留最早（09-17 19:00 而非 FETCHED）、keys 去重后仅一行——原测试从空缓存起步，三条均未被断言（Important）。
3. `load_total_shares` 在 `drop_duplicates(subset=["code"], keep="last")` 前显式 `sort_values("available_at", kind="stable")`——不依赖 `_merge` 行序副作用（Important）。
4. `load_sfc_weekly` 抓取成功后补 `df_w["quality_flags"] = ""`——SFC 帧自带审计列但缺该列，与其他缓存 parquet schema 不一致，Task 12 渲染统一访问会 KeyError。
5. `load_etf_master` 补返回类型注解 `tuple[pd.DataFrame, pd.Timestamp]`，`_parse_eff(eff)` 只算一次。
6. 补两个测试：`test_sfc_negative_cache_expires_after_14_days`（checked_at 超 14 天后重探）、`test_sfc_fetch_adds_quality_flags`。

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/data/hk_short/loaders.py tests/flow_dashboard/test_hk_loaders.py
git commit -m "feat(hk-short): PIT loaders with restated-override, day coverage, sfc negative cache"
```

---

### Task 8: hk_short_metrics.py 核心指标（纯函数）

**Files:**
- Create: `src/flow_dashboard/indicators/hk_short_metrics.py`
- Test: `tests/flow_dashboard/test_hk_metrics.py`

设计 §6.1 冻结定义：均值/分位窗口一律**不含当日**；不足最小观测数返回 None（unavailable），绝不视为 0；除零/负分母 → None。

- [ ] **Step 1: 写失败测试**

```python
"""hk_short_metrics：强度/分位/方向/聚合，边界=不足观测与除零返回 None。"""
import pandas as pd
import pytest

from flow_dashboard.indicators import hk_short_metrics as mx


def test_daily_intensity_excludes_today():
    s = pd.Series([10.0] * 20 + [50.0])   # 前 20 均值 10，当日 50
    assert mx.daily_intensity(s, window=20) == pytest.approx(5.0)
    assert mx.daily_intensity(pd.Series([1.0, 2.0]), window=20) is None  # 观测不足
    assert mx.daily_intensity(pd.Series([0.0] * 20 + [5.0]), window=20) is None  # 分母 0


def test_weekly_intensity_non_overlapping_windows():
    s = pd.Series(range(1, 71), dtype=float)  # 1..70
    # recent = 66..70 = 340；此前 12 个非重叠窗口 = 6..65，均值 177.5
    assert mx.weekly_intensity(s) == pytest.approx(340.0 / 177.5)
    assert mx.weekly_intensity(pd.Series(range(1, 61), dtype=float)) is None  # <65


def test_percentile_rank_min_obs_and_bounds():
    s = pd.Series(list(range(1, 21)) + [21.0])   # 前 20 个观测 1..20
    assert mx.percentile_rank(s, window=60, min_obs=20) == pytest.approx(100.0)
    s0 = pd.Series(list(range(1, 21)) + [0.5])
    assert mx.percentile_rank(s0, window=60, min_obs=20) == pytest.approx(0.0)
    assert mx.percentile_rank(pd.Series([1.0, 2.0])) is None  # <min_obs+1


def test_ret_n_and_price_direction():
    close = pd.Series([100.0, 101, 102, 103, 104, 105.0])  # +5%
    assert mx.ret_n(close, n=5) == pytest.approx(0.05)
    assert mx.ret_n(pd.Series([100.0, 101]), n=5) is None
    assert mx.price_direction(0.012, 0.010) == "up"       # 等权 +1.1% >= 1%
    assert mx.price_direction(-0.012, -0.010) == "down"
    assert mx.price_direction(0.005, -0.005) == "neutral" # 等权 0
    assert mx.price_direction(0.012, -0.005) == "neutral" # 等权 +0.35% < 1%
    assert mx.price_direction(None, 0.010) == "up"        # 单指数可用即判
    assert mx.price_direction(None, None) == "unavailable"


def test_market_daily_aggregate_full_days_only():
    em = pd.DataFrame({
        "code": ["00700", "09988"] * 2,
        "trade_date": [pd.Timestamp("2026-09-17")] * 2 + [pd.Timestamp("2026-09-18")] * 2,
        "short_amount": [3e7, 2e7, 6e7, 2e7],
        "turnover": [3e9, 2e9, 4e9, 2e9],
    })
    agg = mx.market_daily_aggregate(em, full_days=[pd.Timestamp("2026-09-17")])
    assert len(agg) == 1                                  # 09-18 非 full 日被剔除
    r = agg.iloc[0]
    assert r["short_amount"] == pytest.approx(5e7)
    assert r["ssr"] == pytest.approx(5e7 / 5e9)
    assert r["n_secs"] == 2


def test_etf_interference_share():
    hkex = pd.DataFrame({
        "code": ["00700", "02800", "03033"],
        "trade_date": [pd.Timestamp("2026-09-18")] * 3,
        "short_amount": [6.0e9, 3.0e9, 1.0e9],
    })
    out = mx.etf_interference_share(hkex, etf_codes={"02800", "03033"},
                                    trade_date="2026-09-18")
    assert out == pytest.approx(4.0e9 / 10.0e9)
    assert mx.etf_interference_share(hkex, {"02800"}, "2026-09-17") is None  # 无当日行


def test_stock_daily_recomputes_ssr():
    em = pd.DataFrame({
        "code": ["00700", "00700"],
        "trade_date": [pd.Timestamp("2026-09-17"), pd.Timestamp("2026-09-18")],
        "short_amount": [1.0e8, 2.0e8],
        "turnover": [2.0e9, 4.0e9],
        "short_shares": [100.0, 200.0], "short_avg_price": [100.0, 100.0],
        "ssr_pct": [99.0, 99.0], "source_date": ["a", "b"],
        "name": ["腾讯控股", "腾讯控股"],
    })
    df = mx.stock_daily(em, "0700.HK")
    assert list(df["ssr"]) == [0.05, 0.05]  # 金额口径重算，弃用源 ssr_pct
    assert mx.stock_daily(em, "00005.HK").empty
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/flow_dashboard/test_hk_metrics.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

```python
"""hk_short 纯函数指标（设计 §6.1，窗口均不含当日；不足观测/除零 → None）。"""
from __future__ import annotations

import pandas as pd


def daily_intensity(series: pd.Series, window: int = 20) -> float | None:
    """日沽空强度 = 当日 / 前 window 个值均值（均值不含当日）。"""
    s = pd.Series(series).dropna().astype(float)
    if len(s) < window + 1:
        return None
    denom = s.iloc[-window - 1:-1].mean()
    return float(s.iloc[-1] / denom) if denom > 0 else None


def weekly_intensity(series: pd.Series, window_days: int = 5,
                     n_windows: int = 12) -> float | None:
    """周沽空强度 = 最近 window_days 合计 / 此前 n_windows 个非重叠窗口均值。"""
    s = pd.Series(series).dropna().astype(float)
    need = window_days * (n_windows + 1)
    if len(s) < need:
        return None
    recent = s.iloc[-window_days:].sum()
    prior = s.iloc[-need:-window_days].to_numpy().reshape(n_windows, window_days)
    denom = prior.sum(axis=1).mean()
    return float(recent / denom) if denom > 0 else None


def percentile_rank(series: pd.Series, window: int = 60,
                    min_obs: int = 20) -> float | None:
    """当日值在前 window 个历史值（不含当日）中的分位（%，严格小于计次）。"""
    s = pd.Series(series).dropna().astype(float)
    if len(s) < min_obs + 1:
        return None
    prev = s.iloc[-window - 1:-1].dropna()
    if len(prev) < min_obs:
        return None
    return float((prev < s.iloc[-1]).mean() * 100.0)


def ret_n(close: pd.Series, n: int = 5) -> float | None:
    s = pd.Series(close).dropna().astype(float)
    if len(s) < n + 1 or s.iloc[-1 - n] == 0:
        return None
    return float(s.iloc[-1] / s.iloc[-1 - n] - 1.0)


def price_direction(hsi_ret5, hstech_ret5, threshold_bp: float = 100.0) -> str:
    """恒指/恒生科技 5 日收益等权平均；±threshold_bp 之外才有方向。"""
    vals = [v for v in (hsi_ret5, hstech_ret5)
            if v is not None and pd.notna(v)]
    if not vals:
        return "unavailable"
    bp = (sum(vals) / len(vals)) * 1e4
    if bp >= threshold_bp:
        return "up"
    if bp <= -threshold_bp:
        return "down"
    return "neutral"


def market_daily_aggregate(em_df: pd.DataFrame, full_days) -> pd.DataFrame:
    """股票口径市场日度聚合：Σ沽空金额 / Σ总成交金额，只用 full 覆盖日。"""
    if em_df.empty:
        return pd.DataFrame()
    df = em_df[em_df["trade_date"].isin(set(pd.to_datetime(list(full_days))))].copy()
    if df.empty:
        return pd.DataFrame()
    g = (df.groupby("trade_date")
         .agg(short_amount=("short_amount", "sum"),
              turnover=("turnover", "sum"),
              n_secs=("code", "nunique"))
         .sort_index().reset_index())
    g["ssr"] = g["short_amount"] / g["turnover"]
    return g


def etf_interference_share(hkex_df: pd.DataFrame, etf_codes, trade_date) -> float | None:
    """当日 ETF 沽空额 / 全口径沽空额（HKEX dayquot 当日值，设计 §6.3 第 6 步）。"""
    if hkex_df is None or hkex_df.empty:
        return None
    day = hkex_df[hkex_df["trade_date"] == pd.Timestamp(trade_date)]
    if day.empty:
        return None
    total = day["short_amount"].sum()
    if total <= 0:
        return None
    etf = day[day["code"].isin(set(etf_codes))]["short_amount"].sum()
    return float(etf / total)


def stock_daily(em_df: pd.DataFrame, code: str) -> pd.DataFrame:
    """个股日频序列（升序），SSR 按金额口径重算：short_amount / turnover。"""
    if em_df.empty:
        return pd.DataFrame()
    code5 = str(code).split(".")[0].zfill(5)
    df = em_df[em_df["code"] == code5].sort_values("trade_date").copy()
    if df.empty:
        return df
    df["ssr"] = df["short_amount"] / df["turnover"]
    return df
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/flow_dashboard/test_hk_metrics.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/indicators/hk_short_metrics.py tests/flow_dashboard/test_hk_metrics.py
git commit -m "feat(hk-short): pure metrics - intensity, percentile, aggregation, etf share"
```

---

### Task 9: SFC 指标（个股周环比 + 市场可比集合）

**Files:**
- Modify: `src/flow_dashboard/indicators/hk_short_metrics.py`（文件末尾追加）
- Test: `tests/flow_dashboard/test_hk_metrics.py`（追加测试）

个股：`淡仓股数/总股本` 比例周环比（bp）及 4 周斜率（`delta_4w_bp`，不足 5 期 → None，设计 §6.1）；隐含价（金额/股数）两期跳变 >20% 视为公司行动嫌疑 → 保守放弃（available=False）。市场：连续两期均出现的可比集合上算 `Σ淡仓金额/Σ市值` 比例差（bp）与扩散度；可比 <100 只或市值覆盖 <80% → unavailable（设计 §6.1）。

- [ ] **Step 1: 追加失败测试**

```python
def _sfc_two_weeks():
    return pd.DataFrame({
        "code": ["00001", "00700"] * 2,
        "position_date": [pd.Timestamp("2026-09-04")] * 2 + [pd.Timestamp("2026-09-11")] * 2,
        "short_shares": [100.0, 50.0, 200.0, 50.0],
        "short_amount_hkd": [1000.0, 1000.0, 2000.0, 1000.0],
    })


def _shares():
    return pd.DataFrame({"code": ["00001", "00700"],
                         "total_shares": [1000.0, 1000.0]})


def test_sfc_stock_metrics_delta_bp():
    out = mx.sfc_stock_metrics(_sfc_two_weeks(), "00001.HK", total_shares=1000.0)
    assert out["available"] is True
    assert out["delta_bp"] == pytest.approx((0.2 - 0.1) * 1e4)  # +100bp → 加仓
    assert out["latest_pd"] == pd.Timestamp("2026-09-11")
    # 00700 淡仓不变 → 0bp
    out2 = mx.sfc_stock_metrics(_sfc_two_weeks(), "0700.HK", total_shares=1000.0)
    assert out2["delta_bp"] == pytest.approx(0.0)
    # 只有一期 → unavailable
    assert mx.sfc_stock_metrics(_sfc_two_weeks().iloc[:2], "00001.HK", 1000.0)["available"] is False


def test_sfc_stock_metrics_corp_action_suspect():
    df = _sfc_two_weeks()
    df.loc[df["position_date"] == pd.Timestamp("2026-09-11"), "short_amount_hkd"] = [5000.0, 2500.0]
    # 00001 隐含价 10 → 25（跳变 150% > 20%）→ 拆股嫌疑，保守 unavailable
    out = mx.sfc_stock_metrics(df, "00001.HK", total_shares=1000.0)
    assert out["available"] is False


def test_sfc_stock_metrics_four_week_delta():
    rows = []
    for i, wk in enumerate(pd.date_range("2026-08-14", periods=5, freq="7D")):
        rows.append({"code": "00001", "position_date": wk.normalize(),
                     "short_shares": 100.0 + i * 10.0,
                     "short_amount_hkd": (100.0 + i * 10.0) * 10.0})
    out = mx.sfc_stock_metrics(pd.DataFrame(rows), "00001.HK", total_shares=1000.0)
    assert out["available"] is True
    # 周环比：140 vs 130 → +10bp；4 周斜率（4 周差分）：140 vs 100 → +40bp
    assert out["delta_bp"] == pytest.approx(10.0)
    assert out["delta_4w_bp"] == pytest.approx(40.0)
    # 不足 5 期 → delta_4w_bp 为 None（设计 §6.1 斜率证据 unavailable）
    out2 = mx.sfc_stock_metrics(_sfc_two_weeks(), "00001.HK", total_shares=1000.0)
    assert out2["available"] is True and out2.get("delta_4w_bp") is None


def test_sfc_market_metrics_ratio_and_breadth():
    out = mx.sfc_market_metrics(_sfc_two_weeks(), _shares(),
                                min_comparable=2, min_coverage=0.5)
    assert out["available"] is True
    # t0: (1000+1000)/(10000+20000)=0.0667; t1: (2000+1000)/30000=0.1 → +333bp
    assert out["delta_bps"] == pytest.approx((0.1 - 2.0 / 30.0) * 1e4)
    assert out["breadth"] == pytest.approx(0.5)   # 00001 增、00700 平（不增）
    assert out["n_comparable"] == 2


def test_sfc_market_metrics_gates():
    # 可比证券不足 → unavailable
    out = mx.sfc_market_metrics(_sfc_two_weeks(), _shares(),
                                min_comparable=100, min_coverage=0.5)
    assert out["available"] is False and out["n_comparable"] == 2
    # 只有一期 → unavailable
    out2 = mx.sfc_market_metrics(_sfc_two_weeks().iloc[:2], _shares(),
                                 min_comparable=2, min_coverage=0.5)
    assert out2["available"] is False
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/flow_dashboard/test_hk_metrics.py -v -k sfc`
Expected: 5 FAIL（sfc_stock_metrics 不存在）

- [ ] **Step 3: 实现（追加到 hk_short_metrics.py 末尾）**

```python
def sfc_stock_metrics(sfc_df: pd.DataFrame, code: str, total_shares: float,
                      *, jump_threshold: float = 0.20) -> dict:
    """个股 SFC：淡仓/总股本比例周环比（bp）及 4 周斜率。隐含价跳变>阈值=公司行动嫌疑→unavailable。"""
    if sfc_df is None or sfc_df.empty or not total_shares:
        return {"available": False}
    code5 = str(code).split(".")[0].zfill(5)
    df = sfc_df[sfc_df["code"] == code5].sort_values("position_date")
    if len(df) < 2:
        return {"available": False}
    latest, prev = df.iloc[-1], df.iloc[-2]
    implied_now = latest["short_amount_hkd"] / latest["short_shares"]
    implied_prev = prev["short_amount_hkd"] / prev["short_shares"]
    if implied_prev > 0 and abs(implied_now / implied_prev - 1.0) > jump_threshold:
        return {"available": False, "corp_action_suspect": True}
    p_now = latest["short_shares"] / total_shares
    p_prev = prev["short_shares"] / total_shares
    delta_4w = None
    if len(df) >= 5:
        p_4w = df.iloc[-5]["short_shares"] / total_shares
        delta_4w = float((p_now - p_4w) * 1e4)
    return {
        "available": True,
        "latest_pd": pd.Timestamp(latest["position_date"]),
        "prev_pd": pd.Timestamp(prev["position_date"]),
        "latest_shares": float(latest["short_shares"]),
        "delta_bp": float((p_now - p_prev) * 1e4),
        "delta_4w_bp": delta_4w,
    }


def sfc_market_metrics(sfc_df: pd.DataFrame, shares_df: pd.DataFrame, *,
                       min_comparable: int = 100, min_coverage: float = 0.80) -> dict:
    """市场 SFC：连续两期可比集合上 Σ淡仓金额/Σ市值 的比例差与扩散度。

    市值 = 隐含价（金额/股数）× 总股本（f84 缓存）。覆盖率 = 可比集合 t0 市值
    / 上一期全报告 t0 市值；不足门槛 → unavailable（设计 §6.1）。
    """
    if sfc_df is None or sfc_df.empty or shares_df is None or shares_df.empty:
        return {"available": False}
    pds = sorted(pd.to_datetime(sfc_df["position_date"].unique()))
    if len(pds) < 2:
        return {"available": False}
    latest, prev = pds[-1], pds[-2]
    cols = ["code", "short_shares", "short_amount_hkd"]
    cur = sfc_df[sfc_df["position_date"] == latest][cols]
    old = sfc_df[sfc_df["position_date"] == prev][cols]
    m = cur.merge(old, on="code", suffixes=("_t1", "_t0"))
    sh = shares_df[["code", "total_shares"]].drop_duplicates("code")
    m = m.merge(sh, on="code", how="left")
    m = m[(m["total_shares"] > 0)
          & (m["short_shares_t0"] > 0) & (m["short_shares_t1"] > 0)]
    if len(m) < min_comparable:
        return {"available": False, "n_comparable": int(len(m))}
    m = m.copy()
    m["mcap_t1"] = m["short_amount_hkd_t1"] / m["short_shares_t1"] * m["total_shares"]
    m["mcap_t0"] = m["short_amount_hkd_t0"] / m["short_shares_t0"] * m["total_shares"]
    old_full = old.merge(sh, on="code", how="left")
    old_full = old_full[old_full["total_shares"] > 0]
    denom = ((old_full["short_amount_hkd"] / old_full["short_shares"])
             * old_full["total_shares"]).sum()
    coverage = float(m["mcap_t0"].sum() / denom) if denom > 0 else None
    if coverage is None or coverage < min_coverage:
        return {"available": False, "n_comparable": int(len(m)), "coverage": coverage}
    ratio_t1 = m["short_amount_hkd_t1"].sum() / m["mcap_t1"].sum()
    ratio_t0 = m["short_amount_hkd_t0"].sum() / m["mcap_t0"].sum()
    return {
        "available": True,
        "latest_pd": latest, "prev_pd": prev,
        "delta_bps": float((ratio_t1 - ratio_t0) * 1e4),
        "breadth": float((m["short_shares_t1"] > m["short_shares_t0"]).mean()),
        "n_comparable": int(len(m)),
        "coverage": coverage,
    }
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/flow_dashboard/test_hk_metrics.py -v`
Expected: 12 passed

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/indicators/hk_short_metrics.py tests/flow_dashboard/test_hk_metrics.py
git commit -m "feat(hk-short): sfc stock/market metrics on comparable set with corp-action guard"
```

**勘误（质量评审与实施加固记录，c119c4a + 1d34ff1，后续任务依赖不得回退）**：
1. 计划内部矛盾（P5，实施时按修正后测试为准）：`test_sfc_stock_metrics_four_week_delta` 原文首次调用 `total_shares=1000.0` 与断言 +10bp/+40bp 不自洽（(140−130)/1000×1e4=100bp）。修正：首次调用改 `total_shares=10000.0`（out2 保留 1000.0）；实现不变。
2. 指标加固（1d34ff1）：`sfc_stock_metrics` 开头守卫 `not total_shares` 扩为 `not total_shares or pd.isna(total_shares)`——NaN 为真值漏过守卫会产生 NaN delta_bp，使 `_stock_oi` 误判 flat 而非 unavailable；补测试 `test_sfc_stock_metrics_nan_total_shares_unavailable`。
3. 小修：`percentile_rank` 删除 prev 上冗余二次 `dropna()`；`ret_n` 分母守卫 `== 0` → `<= 0` 并补 docstring；补分位并列语义测试（严格小于计次）；`weekly_intensity` 观测不足断言钉死 `len==65`。
4. Step 4 计数勘正：**14 passed**（7 个 Task 8 + P3 并列语义 + 5 个 SFC + P4 + NaN 守卫）。

---

---

### Task 10: hk_short_state.py 状态引擎（§6.4）

**Files:**
- Create: `src/flow_dashboard/indicators/hk_short_state.py`
- Test: `tests/flow_dashboard/test_hk_state.py`

设计 §6.3/§6.4 冻结：状态按矩阵自上而下匹配，首个命中即返回；SFC 证据 unavailable 时任何需要淡仓方向的状态都不得输出"净加仓/净回补明显"；宽限期内不加"待确认"；ETF 干扰只加注释不改状态。

- [ ] **Step 1: 写失败测试**

```python
"""hk_short_state：§6.4 状态矩阵、阈值边界、SFC 降级、宽限期。"""
import pandas as pd
import pytest

from flow_dashboard.indicators import hk_short_state as st
from flow_dashboard.indicators.hk_short_state import Evidence


def _ev(**kw):
    base = dict(oi="unavailable", short_high=False, ssr_high=False,
                price="neutral", participation_high=False,
                sfc_pending=False, etf_interference=False)
    base.update(kw)
    return Evidence(**base)


def test_state_adding_all_conditions():
    ev = _ev(oi="up", short_high=True, ssr_high=True, price="down",
             participation_high=True)
    assert st._classify(ev)["state"] == "空头净加仓迹象明显"


def test_state_divergence_oi_up_price_up():
    ev = _ev(oi="up", price="up")
    assert st._classify(ev)["state"] == "多空分歧扩大"


def test_state_covering_oi_down_price_up_participation():
    ev = _ev(oi="down", price="up", participation_high=True)
    out = st._classify(ev)
    assert out["state"] == "空头净回补迹象明显"
    assert out["notes"] == []  # 沽空额不高 → 无附加注
    out2 = st._classify(_ev(oi="down", price="up", participation_high=True,
                            short_high=True))
    assert st.COVER_NOTE in out2["notes"]  # 回补但沽空额高 → 注明博弈


def test_state_active_but_flat_oi():
    ev = _ev(oi="flat", short_high=True, ssr_high=True)
    assert st._classify(ev)["state"] == "沽空活跃但净仓变化有限"


def test_state_fall_with_oi_down_note():
    # 价跌 + 淡仓↓ 但无参与度 → 未命中回补 → 无法确认 + 长仓卖盘注
    out = st._classify(_ev(oi="down", price="down"))
    assert out["state"] == "暂时无法确认"
    assert st.FALL_NOTE in out["notes"]


def test_oi_unavailable_blocks_directional_states():
    # 淡仓↑ + 价涨本应"多空分歧扩大"，但 SFC unavailable → 无法确认
    out = st._classify(_ev(oi="unavailable", price="up"))
    assert out["state"] == "暂时无法确认"
    # 沽空额高 + SSR 高 + oi unavailable → 不输出"活跃但净仓有限"？§6.4 该状态
    # 要求 淡仓Δ≈0（flat），unavailable 不等于 ≈0 → 无法确认
    out2 = st._classify(_ev(oi="unavailable", short_high=True, ssr_high=True))
    assert out2["state"] == "暂时无法确认"


def test_etf_note_added_without_changing_state():
    out = st._classify(_ev(oi="flat", short_high=True, ssr_high=True,
                           etf_interference=True))
    assert out["state"] == "沽空活跃但净仓变化有限"
    assert st.ETF_HEDGE_NOTE in out["notes"]


def test_market_conclusion_thresholds_and_suffix():
    out = st.market_conclusion(
        sfc={"available": True, "delta_bps": 4.0, "breadth": 0.56},
        weekly_short_intensity=1.25,   # == 阈值 → short_high（>=）
        ssr_percentile=80.0,           # == 阈值 → ssr_high（>=）
        price="down",
        participation_high=True)
    assert out["state"] == "空头净加仓迹象明显"  # delta==3bp? 不：4.0>3，等值边界见下
    # delta 恰为 +3bp 且 breadth 恰为 0.55 → 仍算 up（>=）
    out2 = st.market_conclusion(
        sfc={"available": True, "delta_bps": 3.0, "breadth": 0.55},
        weekly_short_intensity=1.24, ssr_percentile=79.9,
        price="down", participation_high=True)
    # oi=up 但强度/分位不足 → 不满足加仓五条件，也不满足其余 → 无法确认
    assert out2["state"] == "暂时无法确认"
    # sfc_pending → 后缀
    out3 = st.market_conclusion(sfc=None, sfc_pending=True)
    assert out3["state"].endswith(st.SFC_PENDING_SUFFIX)


def test_market_oi_direction_bands():
    t = {"mkt_sfc_delta_bp": 3.0, "mkt_sfc_breadth_pos": 0.55,
         "mkt_sfc_breadth_neg": 0.45}
    assert st._market_oi({"available": True, "delta_bps": 5.0, "breadth": 0.6}, t) == "up"
    assert st._market_oi({"available": True, "delta_bps": -5.0, "breadth": 0.4}, t) == "down"
    # delta +4bp 但 breadth 0.50（<0.55）→ 不算 up → flat
    assert st._market_oi({"available": True, "delta_bps": 4.0, "breadth": 0.50}, t) == "flat"
    # delta -4bp 但 breadth 0.50（>0.45）→ 不算 down → flat
    assert st._market_oi({"available": True, "delta_bps": -4.0, "breadth": 0.50}, t) == "flat"
    assert st._market_oi({"available": False}, t) == "unavailable"
    assert st._market_oi(None, t) == "unavailable"


def test_stock_conclusion_and_oi_bands():
    t = {"stock_sfc_delta_bp": 5.0}
    assert st._stock_oi({"available": True, "delta_bp": 5.0}, t) == "up"    # >=
    assert st._stock_oi({"available": True, "delta_bp": -5.0}, t) == "down" # <=
    assert st._stock_oi({"available": True, "delta_bp": 4.99}, t) == "flat"
    out = st.stock_conclusion(
        sfc={"available": True, "delta_bp": 6.0},
        weekly_short_intensity=1.30, ssr_percentile=85.0,
        price="down", participation_high=True)
    assert out["state"] == "空头净加仓迹象明显"


def test_sfc_is_pending_grace_window():
    # 缺失的下一个应公布周 = 09-18（最新已完成周），其宽限期至 09-25 EOD
    cached = pd.Timestamp("2026-09-11")
    # 09-21（宽限期内，09-18 报告未超宽限期）→ 不 pending（与 Task 14 一致）
    assert not st.sfc_is_pending(latest_cached_pd=cached,
                                 as_of=pd.Timestamp("2026-09-21 18:45", tz="Asia/Shanghai"))
    # 09-28（09-18 宽限期已过仍缺）→ pending
    assert st.sfc_is_pending(latest_cached_pd=cached,
                             as_of=pd.Timestamp("2026-09-28 18:45", tz="Asia/Shanghai"))
    # 09-16（本周五 09-18 未结束，最新已完成周=09-11，缓存已含）→ 不 pending
    assert not st.sfc_is_pending(latest_cached_pd=cached,
                                 as_of=pd.Timestamp("2026-09-16 10:00", tz="Asia/Shanghai"))
    # 缓存已含最新周（09-18）→ 不 pending
    assert not st.sfc_is_pending(latest_cached_pd=pd.Timestamp("2026-09-18"),
                                 as_of=pd.Timestamp("2026-09-21 18:45", tz="Asia/Shanghai"))
    # 无任何缓存 → pending（数据缺失）
    assert st.sfc_is_pending(latest_cached_pd=None,
                             as_of=pd.Timestamp("2026-09-21 18:45", tz="Asia/Shanghai"))
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/flow_dashboard/test_hk_state.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

```python
"""hk_short 状态引擎（设计 §6.3 判断顺序 + §6.4 状态矩阵，纯规则）。

冻结原则：
- 状态按矩阵自上而下匹配，首个命中即返回，未命中返回"暂时无法确认"
- 任何需要淡仓方向的状态在 oi=unavailable 时不得输出（含"活跃但净仓有限"，
  该状态要求 淡仓Δ≈0 即 flat，unavailable ≠ ≈0）
- "·SFC待确认"后缀只在超过宽限期仍缺最新一期时添加
- ETF 干扰只加注释，不改状态
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from flow_dashboard.config import HK_THRESHOLDS
from flow_dashboard.data.hk_short.hk_calendar import (
    recent_sfc_position_dates, sfc_grace_deadline,
)

ETF_HEDGE_NOTE = "总沽空增加或主要来自指数对冲，不宜直接解读为个股看空增强"
SFC_PENDING_SUFFIX = "·SFC待确认"
FALL_NOTE = "下跌压力或来自长仓卖盘而非新增空头"
COVER_NOTE = "沽空额仍高，回补或伴随激烈博弈"


@dataclass
class Evidence:
    oi: str = "unavailable"          # up / down / flat / unavailable
    short_high: bool = False
    ssr_high: bool = False
    price: str = "neutral"           # up / down / neutral / unavailable
    participation_high: bool = False
    sfc_pending: bool = False
    etf_interference: bool = False
    notes: list[str] = field(default_factory=list)


def _classify(ev: Evidence) -> dict:
    """§6.4 状态矩阵（自上而下，首个命中即返回）。"""
    state, notes = "暂时无法确认", list(ev.notes)
    if (ev.oi == "up" and ev.short_high and ev.ssr_high
            and ev.price == "down" and ev.participation_high):
        state = "空头净加仓迹象明显"
    elif ev.oi == "up" and ev.price == "up":
        state = "多空分歧扩大"
    elif ev.oi == "down" and ev.price == "up" and ev.participation_high:
        state = "空头净回补迹象明显"
        if ev.short_high:
            notes.append(COVER_NOTE)
    elif ev.short_high and ev.ssr_high and ev.oi == "flat":
        state = "沽空活跃但净仓变化有限"
    elif ev.price == "down" and ev.oi == "down":
        notes.append(FALL_NOTE)

    if ev.etf_interference:
        notes.append(ETF_HEDGE_NOTE)
    if ev.sfc_pending:
        state = state + SFC_PENDING_SUFFIX
    return {"state": state, "notes": notes}


def _market_oi(sfc: dict | None, t: dict) -> str:
    """市场淡仓方向：delta ±3bp 且 breadth 55%/45% 同向才给方向。"""
    if not sfc or not sfc.get("available"):
        return "unavailable"
    d, b = sfc["delta_bps"], sfc["breadth"]
    if d >= t["mkt_sfc_delta_bp"] and b >= t["mkt_sfc_breadth_pos"]:
        return "up"
    if d <= -t["mkt_sfc_delta_bp"] and b <= t["mkt_sfc_breadth_neg"]:
        return "down"
    return "flat"


def _stock_oi(stock_sfc: dict | None, t: dict) -> str:
    if not stock_sfc or not stock_sfc.get("available"):
        return "unavailable"
    d = stock_sfc["delta_bp"]
    if d >= t["stock_sfc_delta_bp"]:
        return "up"
    if d <= -t["stock_sfc_delta_bp"]:
        return "down"
    return "flat"


def market_conclusion(
    *,
    sfc: dict | None = None,
    weekly_short_intensity: float | None = None,
    ssr_percentile: float | None = None,
    price: str = "unavailable",
    participation_high: bool = False,
    sfc_pending: bool = False,
    etf_interference: bool = False,
    extra_notes: list[str] | None = None,
) -> dict:
    t = HK_THRESHOLDS
    ev = Evidence(
        oi=_market_oi(sfc, t),
        short_high=(weekly_short_intensity is not None
                    and weekly_short_intensity >= t["weekly_intensity_high"]),
        ssr_high=(ssr_percentile is not None
                  and ssr_percentile >= t["ssr_pct_high"]),
        price=price,
        participation_high=participation_high,
        sfc_pending=sfc_pending,
        etf_interference=etf_interference,
        notes=list(extra_notes or []),
    )
    return _classify(ev)


def stock_conclusion(
    *,
    sfc: dict | None = None,
    weekly_short_intensity: float | None = None,
    ssr_percentile: float | None = None,
    price: str = "neutral",
    participation_high: bool = False,
    etf_interference: bool = False,
    extra_notes: list[str] | None = None,
) -> dict:
    t = HK_THRESHOLDS
    ev = Evidence(
        oi=_stock_oi(sfc, t),
        short_high=(weekly_short_intensity is not None
                    and weekly_short_intensity >= t["weekly_intensity_high"]),
        ssr_high=(ssr_percentile is not None
                  and ssr_percentile >= t["ssr_pct_high"]),
        price=price,
        participation_high=participation_high,
        etf_interference=etf_interference,
        notes=list(extra_notes or []),
    )
    return _classify(ev)


def sfc_is_pending(*, latest_cached_pd, as_of) -> bool:
    """缓存是否缺失已超宽限期的 SFC 周报（设计 §6.3，勘误修正版）。

    从最新缓存一期之后的第一个应公布周 W（recent 列表中 > 缓存期的最小一周）
    起算：W 的宽限期（position_date 后第 5 个香港交易日 EOD）已过仍缺该期
    → True。宽限期内沿用最新已公布一期，不加"待确认"。
    latest_cached_pd=None（缓存里没有任何一期）→ 恒 True（数据缺失）。
    """
    if latest_cached_pd is None or pd.isna(latest_cached_pd):
        return True
    ts = pd.Timestamp(as_of)
    ts = ts.tz_convert("Asia/Shanghai").tz_localize(None) if ts.tzinfo else ts
    recent = recent_sfc_position_dates(ts, n=8)
    if not recent:
        return False
    cached = pd.Timestamp(latest_cached_pd).normalize()
    newer = [w for w in recent if w > cached]
    if not newer:
        return False  # 已含最新已完成周
    return ts > sfc_grace_deadline(min(newer))
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/flow_dashboard/test_hk_state.py -v`
Expected: 11 passed

**勘误（实施前修正，后续任务依赖不得回退）**：计划原 `sfc_is_pending` 参考实现与其验收测试 `test_sfc_is_pending_grace_window`、Task 14 的 `test_sfc_missing_grace_window` 三方矛盾（同一输入 09-21/cached=09-11 一处断言 pending、一处断言 not-missing）。按设计文档 §6.3（"宽限期内沿用最新已公布一期并显示其报告日，不加'待确认'；超过宽限期仍缺新一期时，SFC 证据记为 unavailable，并添加后缀"）修正为：**从最新缓存期之后的第一个应公布周 W 起算宽限**（`recent_sfc_position_dates` 结果中 > 缓存期的最小一周）；`latest_cached_pd=None` → 恒 pending（数据缺失）。已同步改写参考实现与该测试（判 Task 14 + 设计文档胜出）。修正后行为：报告正常公布日（=宽限期末日）过后仍缺才加后缀；缓存落后多周时按最早缺失周判定。

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/indicators/hk_short_state.py tests/flow_dashboard/test_hk_state.py
git commit -m "feat(hk-short): rule-based state engine per design 6.4 matrix"
```

---

### Task 11: theme.py tabs 支持

**Files:**
- Modify: `src/flow_dashboard/render/theme.py`（`build_html_skeleton` 增加 `tabs` 参数）
- Test: `tests/flow_dashboard/test_hk_theme_tabs.py`

设计 §3：顶部一级 tab 导航（A股资金流 | 港股沽空），原生 JS 切换 + URL hash 记忆；A股现有调用（tabs=None）行为完全不变。隐藏容器中的 Plotly 图初始宽度为 0，切换显示时必须 `Plotly.Plots.resize`。

- [ ] **Step 1: 写失败测试**

```python
"""theme tabs：结构、默认首个激活、legacy 路径不受影响。"""
from flow_dashboard.render.theme import build_html_skeleton


def _skeleton(**kw):
    return build_html_skeleton(
        title="t", body="<p>legacy</p>", data_date="2026-09-18",
        last_success_at="2026-09-18 19:00", **kw)


def test_legacy_skeleton_has_no_tabs():
    html = _skeleton(nav_sections=[("section-etf", "01 ETF")])
    assert "tab-bar" not in html
    assert '<p>legacy</p>' in html
    assert 'class="section-nav"' in html  # 旧导航条仍在


def test_tabs_structure_and_default_active():
    html = _skeleton(tabs=[
        {"id": "ashare", "name": "A股资金流", "body": "<div>A股内容</div>",
         "nav_sections": [("section-etf", "01 ETF")]},
        {"id": "hk-short", "name": "港股沽空", "body": "<div>港股内容</div>",
         "nav_sections": [("section-hk-conclusion", "HK 结论")]},
    ])
    assert 'class="tab-bar"' in html
    assert 'data-tab="ashare"' in html and 'data-tab="hk-short"' in html
    assert 'id="tab-ashare"' in html and 'id="tab-hk-short"' in html
    # 服务端默认激活第一个 tab（无 JS 也可看）
    assert 'id="tab-ashare" class="tab-panel active"' in html
    assert 'id="tab-hk-short" class="tab-panel"' in html
    # 每个 tab 内有自己的 section-nav
    assert html.count('class="section-nav"') == 2
    assert "A股内容" in html and "港股内容" in html
    # legacy body 不进 tab 模式
    assert "<p>legacy</p>" not in html
    # JS：hash 记忆 + Plotly resize
    assert "Plotly.Plots.resize" in html
    assert "hashchange" in html


def test_tabs_html_escaping():
    html = _skeleton(tabs=[
        {"id": "a<x", "name": "A&股", "body": "<div>b</div>"},
        {"id": "b", "name": "B", "body": "<div>c</div>"},
    ])
    assert "A&amp;股" in html and "a<x" not in html  # name/id 转义
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/flow_dashboard/test_hk_theme_tabs.py -v`
Expected: FAIL（TypeError: unexpected keyword 'tabs'）

- [ ] **Step 3: 实现**

`build_html_skeleton` 签名增加 `tabs: list[dict] | None = None`。函数体内 nav_html 与 main 部分替换为：

```python
def build_html_skeleton(
    *,
    title: str,
    body: str,
    data_date: str,
    last_success_at: str,
    footer: str = "市场观察，非交易建议",
    nav_sections: list[tuple[str, str]] | None = None,
    tabs: list[dict] | None = None,
) -> str:
    """构建完整 HTML 文档。Plotly JS 仅在此处内嵌一次。

    Args:
        nav_sections: 章节锚点列表（无 tabs 时的旧导航条行为）。
        tabs: 一级 tab 页列表，每项
            ``{"id": str, "name": str, "body": str, "nav_sections": [(anchor, name), ...]}``；
            提供时忽略顶层 body/nav_sections，每个 tab 渲染独立容器 + 独立
            section-nav。第一个 tab 服务端标记 active（无 JS 回退）。
    """
    bundle = get_plotly_bundle()
    title_h = _html_escape(title)
    data_date_h = _html_escape(data_date)
    last_success_at_h = _html_escape(last_success_at)
    footer_h = _html_escape(footer)

    def _nav(sec) -> str:
        if not sec:
            return ""
        items = "".join(
            f'<a href="#{_html_escape(anchor)}">{_html_escape(name)}</a>'
            for anchor, name in sec
        )
        return f'<nav class="section-nav">{items}</nav>'

    if tabs is None:
        nav_html = _nav(nav_sections)
        main_html = f"<main>\n{body}\n</main>"
        tab_bar_html, tab_js = "", ""
    else:
        nav_html = ""
        bar_items = "".join(
            f'<a href="#tab-{_html_escape(t["id"])}" data-tab="{_html_escape(t["id"])}">'
            f'{_html_escape(t["name"])}</a>'
            for t in tabs
        )
        tab_bar_html = f'<nav class="tab-bar">{bar_items}</nav>'
        panels = []
        for i, t in enumerate(tabs):
            active = " active" if i == 0 else ""
            panels.append(
                f'<section id="tab-{_html_escape(t["id"])}" '
                f'class="tab-panel{active}">\n'
                f'{_nav(t.get("nav_sections"))}\n{t["body"]}\n</section>'
            )
        main_html = f"<main>\n{chr(10).join(panels)}\n</main>"
        tab_js = """
<script>
function _showTab(id){
  document.querySelectorAll('.tab-panel').forEach(function(p){
    p.classList.toggle('active', p.id === 'tab-' + id);});
  document.querySelectorAll('.tab-bar a').forEach(function(a){
    a.classList.toggle('active', a.dataset.tab === id);});
  if (window.Plotly) {
    document.querySelectorAll('.tab-panel.active .plotly-graph-div')
      .forEach(function(d){ Plotly.Plots.resize(d); });
  }
}
function _tabFromHash(){
  var m = location.hash.match(/^#tab-(.+)$/);
  var first = document.querySelector('.tab-bar a');
  _showTab(m ? m[1] : (first ? first.dataset.tab : ''));
}
window.addEventListener('hashchange', _tabFromHash);
_tabFromHash();
</script>"""
```

`<body>` 部分的模板中 `{nav_html}` 之后、`<main>` 之前插入 `{tab_bar_html}`；`</body>` 前插入 `{tab_js}`。同时在 `<style>` 末尾追加：

```css
/* —— 一级 tab（A股 | 港股） —— */
.tab-bar {{
    background: {COLORS['primary']}; padding: 8px 24px; margin: 0 -20px 0 -20px;
    font-size: 14px;
}}
.tab-bar a {{
    color: rgba(255,255,255,0.75); text-decoration: none; margin-right: 28px;
    padding: 6px 12px; border-radius: 4px;
}}
.tab-bar a.active {{ background: rgba(255,255,255,0.18); color: #fff; font-weight: 600; }}
.tab-panel {{ display: none; }}
.tab-panel.active {{ display: block; }}
.tab-panel .section-nav {{ margin-top: 16px; }}
```

注意：`tab_js` 与 CSS 块写在 f-string 模板外/内的选择——CSS 追加到现有 `<style>` f-string 内（花括号双写），`tab_js` 是纯字符串常量直接插入模板（无 f-string 花括号冲突，因为独立赋值）。

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/flow_dashboard/test_hk_theme_tabs.py -v && python -m pytest tests/flow_dashboard/ -v -k "theme or skeleton" --no-header -q`
Expected: 新 3 passed；现有 theme 相关测试不回归

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/render/theme.py tests/flow_dashboard/test_hk_theme_tabs.py
git commit -m "feat(hk-short): top-level tabs in html skeleton with hash memory and plotly resize"
```

**勘误（实施与质量评审加固记录，2313bc9 + a1f6526，后续任务依赖不得回退）**：
1. tab CSS 用条件变量 `tab_css` 仅在 tabs 模式注入 `<style>`——原参考代码无条件追加会令 legacy 模式出现 `tab-bar` 字样，直接违反 `test_legacy_skeleton_has_no_tabs` 与设计 §3"A股调用行为完全不变"。
2. `test_tabs_html_escaping` 的 `assert "a<x" not in html` 原文不可满足（内嵌 plotly 压缩 bundle 含字面 `a<x`）。改为：先以 re.sub 剥离 `<script>` 块再作负断言，并新增正断言 `assert "a&lt;x" in markup`（id 确被转义）。
3. 质量评审 Important 修复（a1f6526）：`_tabFromHash` 在 hash 不匹配 `#tab-` 时**保持当前 tab**（`if (!m) return;`），不得回退第一个 tab——否则点击 tab 内 section-nav 锚点（如 `#section-hk-conclusion`）会把用户强切回 A股 tab；初始无 hash 时依赖服务端 active 类（首 tab 已标记）。补测试 `test_tab_js_keeps_current_tab_on_non_tab_hash`（对 JS 函数体做文本契约钉死，JS 不可单测）。
4. 顺带删除 theme.py 既有无用导入 `from pathlib import Path`（F401）并应用 ruff format（既有代码重排，值不变）；tabs=None 路径输出 sha256 前后字节级一致。Step 4 计数勘正：新 **4 passed**（3 原测试 + 守卫测试），theme/skeleton 回归 11 passed。

---

### Task 12: panels_hk_short.py 港股 tab 渲染

**Files:**
- Create: `src/flow_dashboard/render/panels_hk_short.py`
- Test: `tests/flow_dashboard/test_hk_panels.py`

设计 §4：结论卡（置顶）→ 市场总览图 → watch list 逐日明细（11 列，未平仓列仅 SFC 周报日有值）→ TOP20。渲染**只读缓存**（所有 loader `allow_fetch=False`），缓存为空返回"数据待更新"横幅、不抛错（§3：港股故障不拖垮 A股 tab）。ETF watch（2800/3033）卖空来自 HKEX dayquot（东财无 ETF）。

- [ ] **Step 1: 写失败测试**

```python
"""panels_hk_short：空缓存横幅、结论卡、11 列明细、稀疏 OI、TOP20、ETF 回退。"""
import pandas as pd

from flow_dashboard.data.hk_short import loaders
from flow_dashboard.render.panels_hk_short import render_hk_short_body

AS_OF = pd.Timestamp("2026-09-18 19:00", tz="Asia/Shanghai")
AVAIL_EM = pd.Timestamp("2026-09-18 16:10", tz="Asia/Shanghai")


def _audit(df, avail=AVAIL_EM):
    df = df.copy()
    df["source_date"] = pd.to_datetime(df["trade_date"]) if "trade_date" in df else AS_OF.tz_localize(None)
    df["first_observed_at"] = AS_OF
    df["available_at"] = avail
    df["fetched_at"] = AS_OF
    df["source"] = "test"
    df["source_version"] = "v1"
    df["quality_flags"] = ""
    return df


def _build_cache(tmp_path):
    days = [pd.Timestamp(d) for d in ("2026-09-11", "2026-09-16",
                                      "2026-09-17", "2026-09-18")]
    em_rows = []
    for d in days:
        em_rows.append({"code": "00700", "name": "腾讯控股", "trade_date": d,
                        "short_shares": 1e6, "short_avg_price": 300.0,
                        "short_amount": 3e8, "turnover": 3e9, "ssr_pct": 10.0})
        em_rows.append({"code": "09988", "name": "阿里巴巴-W", "trade_date": d,
                        "short_shares": 1e6, "short_avg_price": 100.0,
                        "short_amount": 1e8, "turnover": 1e9, "ssr_pct": 10.0})
    loaders._write(_audit(pd.DataFrame(em_rows)), tmp_path / loaders.EM_FILE)
    loaders._write(pd.DataFrame({"trade_date": days, "coverage": ["full"] * 4}),
                   tmp_path / loaders.DAYS_FILE)

    kl = []
    for secid, closes in (("100.HSI", [100, 101, 102, 103, 104, 105]),
                          ("124.HSTECH", [100, 100, 100, 100, 100, 100]),
                          ("116.00700", [300, 301, 302, 303, 304, 305])):
        for i, c in enumerate(closes):
            kl.append({"secid": secid, "trade_date": pd.Timestamp("2026-09-09") + pd.Timedelta(days=i + 1),
                       "open": c, "close": c, "high": c, "low": c, "volume": 1e6, "amount": 1e8})
    loaders._write(_audit(pd.DataFrame(kl)), tmp_path / loaders.KLINE_FILE)

    hq = []
    for d in days[1:]:
        hq.append({"code": "02800", "name": "盈富基金", "trade_date": d,
                   "short_shares": 3e5, "short_amount": 3e9,
                   "total_shares_traded": 1e7, "turnover": 2e10})
    hq.append({"code": "00700", "name": "腾讯控股", "trade_date": pd.Timestamp("2026-09-18"),
               "short_shares": 1e6, "short_amount": 6e9,
               "total_shares_traded": 1e7, "turnover": 3e9})
    loaders._write(_audit(pd.DataFrame(hq)), tmp_path / loaders.HKEX_FILE)

    los = pd.DataFrame({"code": ["02800"], "name": ["盈富基金"],
                        "category": ["Exchange Traded Products"], "sub_category": ["ETF"]})
    los = los.assign(effective_date=pd.Timestamp("2026-09-18"))
    loaders._write(_audit(los), tmp_path / loaders.LOS_FILE)

    sh = pd.DataFrame({"code": ["00700", "02800"], "total_shares": [9.095e9, 1.0e10]})
    loaders._write(_audit(sh), tmp_path / loaders.SHARES_FILE)

    sfc_rows = []
    for pos, pub in ((pd.Timestamp("2026-09-04"), pd.Timestamp("2026-09-11 15:41", tz="Asia/Shanghai")),
                     (pd.Timestamp("2026-09-11"), pd.Timestamp("2026-09-18 15:41", tz="Asia/Shanghai"))):
        sfc_rows.append({"code": "00001", "name": "CKH", "position_date": pos,
                         "short_shares": 1e6, "short_amount_hkd": 1e8,
                         "published_at": pub, "first_observed_at": AS_OF,
                         "available_at": pub, "source_date": pos, "fetched_at": AS_OF,
                         "source": "sfc", "source_version": "v1"})
        # 00700 淡仓 +100bp（0.01 → 0.02 of 9.095e9? 用显式值）
        sfc_rows.append({"code": "00700", "name": "TENCENT", "position_date": pos,
                         "short_shares": (9.095e9 * 0.001) if pos == pd.Timestamp("2026-09-04") else (9.095e9 * 0.002),
                         "short_amount_hkd": 3e8, "published_at": pub,
                         "first_observed_at": AS_OF, "available_at": pub,
                         "source_date": pos, "fetched_at": AS_OF,
                         "source": "sfc", "source_version": "v1"})
    loaders._write(pd.DataFrame(sfc_rows), tmp_path / loaders.SFC_FILE)


def test_empty_cache_returns_banner_and_none_date(tmp_path):
    html, hk_date = render_hk_short_body(as_of=AS_OF, cache_dir=tmp_path)
    assert hk_date is None
    assert "数据待更新" in html


def test_render_smoke_full_cache(tmp_path):
    _build_cache(tmp_path)
    html, hk_date = render_hk_short_body(as_of=AS_OF, cache_dir=tmp_path)
    assert hk_date == "2026-09-18"
    # 结论卡 + 指数对冲注（ETF 3e9/9e9 = 33% >= 30%）
    assert "市场结论" in html
    assert "暂时无法确认" in html            # SFC 市场可比集合不足 100 → oi unavailable
    assert "指数对冲" in html
    assert "·SFC待确认" not in html          # 宽限期内不加后缀
    # 市场总览图 + KPI 副指标标注股票口径
    assert "股票口径" in html


def test_watch_table_11_cols_sparse_oi_and_etf_fallback(tmp_path):
    _build_cache(tmp_path)
    html, _ = render_hk_short_body(as_of=AS_OF, cache_dir=tmp_path)
    # 11 列表头
    assert "未平仓卖空期末值·股数" in html
    assert "期末未平仓/总股本%" in html
    # 00700：SFC 09-11 有 OI（0.002*9.095e9 = 18,190,000），且只出现一次
    assert html.count("18,190,000") == 1
    # 00700 状态标签：oi=up（+10bp）+ 价涨 → 多空分歧扩大
    assert "多空分歧扩大" in html
    # ETF 2800 走 HKEX 回退，表格照常渲染
    assert "盈富基金" in html


def test_top20_renders_with_insufficient_sample(tmp_path):
    _build_cache(tmp_path)
    html, _ = render_hk_short_body(as_of=AS_OF, cache_dir=tmp_path)
    assert "TOP20" in html
    assert "样本不足" in html            # 历史仅 4 日 < 20 → 不伪造分位
    assert "腾讯控股" in html
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/flow_dashboard/test_hk_panels.py -v`
Expected: FAIL（ModuleNotFoundError）

- [ ] **Step 3: 实现**

```python
"""港股沽空 tab 渲染（设计 §4）：只读缓存确定性重放，不发起网络请求。

render_hk_short_body 是唯一入口，返回 (html, hk_data_date)；缓存为空时
返回"数据待更新"横幅与 None（A股 tab 不受影响，设计 §3）。
"""
from __future__ import annotations

from html import escape as _esc
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go

from flow_dashboard.config import (
    HK_SHORT_CACHE_DIR, HK_THRESHOLDS, HK_WATCH_LIST, HK_INDEX_SECIDS,
)
from flow_dashboard.data.hk_short.hkex_client import etf_set
from flow_dashboard.data.hk_short.loaders import (
    load_em_days_covered, load_em_sellshort, load_etf_master,
    load_hkex_dayquot, load_hk_kline, load_sfc_weekly, load_total_shares,
)
from flow_dashboard.indicators import hk_short_metrics as mx
from flow_dashboard.indicators import hk_short_state as state
from flow_dashboard.render.theme import (
    COLORS, apply_theme, render_figure_to_html, render_kpi_cards,
    render_section_band,
)

T = HK_THRESHOLDS

_TH = ("border:1px solid #e8e8e8;padding:4px 8px;background:#f0f3f7;"
       "text-align:right;font-weight:600;white-space:nowrap")
_TD = "border:1px solid #e8e8e8;padding:4px 8px;text-align:right;white-space:nowrap"

_COLS = ["交易日期", "卖空股数", "卖空金额", "未平仓卖空期末值·股数",
         "未平仓卖空期末值·金额", "收盘价", "涨跌幅%", "成交量", "成交额",
         "卖空金额/成交额%", "期末未平仓/总股本%"]


def _fmt_amount(v) -> str:
    if v is None or pd.isna(v):
        return "—"
    if abs(v) >= 1e8:
        return f"{v / 1e8:.2f}亿"
    if abs(v) >= 1e4:
        return f"{v / 1e4:.1f}万"
    return f"{v:,.0f}"


def _fmt_pct(v, digits: int = 2) -> str:
    return "—" if v is None or pd.isna(v) else f"{v * 100:.{digits}f}%"


def _fmt_x(v) -> str:
    return "样本不足" if v is None or pd.isna(v) else f"{v:.2f}x"


def _price_direction(kline: pd.DataFrame) -> str:
    if kline is None or kline.empty:
        return "unavailable"
    rets = []
    for secid in ("HSI", "HSTECH"):
        s = kline[kline["secid"] == HK_INDEX_SECIDS[secid]].sort_values("trade_date")["close"]
        rets.append(mx.ret_n(s, n=5))
    return mx.price_direction(rets[0] if len(rets) > 0 else None,
                              rets[1] if len(rets) > 1 else None,
                              threshold_bp=T["price_ret_bp"])


def _secid_of(code: str) -> str:
    return f"116.{code.split('.')[0].zfill(5)}"


def _build_context(*, as_of, cdir: Path) -> dict:
    em = load_em_sellshort(as_of=as_of, allow_fetch=False, cache_dir=cdir)
    full_days = load_em_days_covered(as_of=as_of, cache_dir=cdir)
    hkex = load_hkex_dayquot(as_of=as_of, allow_fetch=False, cache_dir=cdir)
    sfc = load_sfc_weekly(as_of=as_of, allow_fetch=False, cache_dir=cdir)
    secids = list(HK_INDEX_SECIDS.values()) + [_secid_of(c) for _, c in HK_WATCH_LIST]
    kline = load_hk_kline(as_of=as_of, secids=secids, allow_fetch=False, cache_dir=cdir)
    los, _eff = load_etf_master(as_of=as_of, allow_fetch=False, cache_dir=cdir)
    shares = load_total_shares(as_of=as_of, codes=[], allow_fetch=False, cache_dir=cdir)

    mkt = mx.market_daily_aggregate(em, full_days) if not em.empty else pd.DataFrame()
    weekly_i = mx.weekly_intensity(mkt["short_amount"]) if not mkt.empty else None
    ssr_pct = (mx.percentile_rank(mkt["ssr"], window=T["ssr_pct_window"],
                                  min_obs=T["ssr_pct_min_obs"])
               if not mkt.empty else None)
    m20 = (mx.daily_intensity(mkt["short_amount"], window=T["daily_intensity_window"])
           if not mkt.empty else None)
    part = (mx.daily_intensity(mkt["turnover"], window=T["daily_intensity_window"])
            if not mkt.empty else None)
    price = _price_direction(kline)
    sfc_mkt = (mx.sfc_market_metrics(sfc, shares,
                                     min_comparable=T["sfc_min_comparable"],
                                     min_coverage=T["sfc_min_coverage"])
               if not sfc.empty and not shares.empty else {"available": False})
    etf_codes = etf_set(los)
    hk_date = (mkt["trade_date"].max() if not mkt.empty
               else (pd.to_datetime(kline["trade_date"]).max() if not kline.empty
                     else pd.to_datetime(sfc["position_date"]).max()))
    dstr = pd.Timestamp(hk_date).strftime("%Y-%m-%d")
    etf_share = (mx.etf_interference_share(hkex, etf_codes, dstr)
                 if not hkex.empty and etf_codes else None)
    full_total = (hkex.loc[hkex["trade_date"] == pd.Timestamp(dstr), "short_amount"].sum()
                  if not hkex.empty else None)
    pending = state.sfc_is_pending(
        latest_cached_pd=(pd.to_datetime(sfc["position_date"]).max()
                          if not sfc.empty else None),
        as_of=as_of)
    conclusion = state.market_conclusion(
        sfc=sfc_mkt, weekly_short_intensity=weekly_i, ssr_percentile=ssr_pct,
        price=price,
        participation_high=part is not None and part >= T["participation_high"],
        sfc_pending=pending,
        etf_interference=etf_share is not None and etf_share >= T["etf_interference"])
    return {
        "as_of": as_of, "em": em, "hkex": hkex, "sfc": sfc, "kline": kline,
        "los": los, "shares": shares, "mkt": mkt, "weekly_i": weekly_i,
        "ssr_pct": ssr_pct, "m20": m20, "part": part, "price": price,
        "sfc_mkt": sfc_mkt, "etf_share": etf_share, "full_total": full_total,
        "pending": pending, "conclusion": conclusion, "dstr": dstr,
    }


def render_hk_short_body(*, as_of, cache_dir=None) -> tuple[str, str | None]:
    cdir = Path(cache_dir) if cache_dir else HK_SHORT_CACHE_DIR
    ctx = _build_context(as_of=as_of, cdir=cdir)
    if (ctx["em"].empty and ctx["sfc"].empty and ctx["hkex"].empty
            and ctx["kline"].empty):
        banner = ('<div class="panel stale">⚠️ 港股沽空数据待更新 — 缓存为空。'
                  "请检查 com.ygr.hk-short.eod runner、HKEX/东财/SFC 网络与 launchd 日志。</div>")
        return banner, None
    parts = [
        render_section_band(anchor_id="section-hk-conclusion", num="HK",
                            title="港股沽空 · 空头状态",
                            subtitle=f"数据截至 {ctx['dstr']} · 股票口径，不含 ETF/ETP"),
        _render_conclusion(ctx),
        _render_market_chart(ctx),
        _render_watch(ctx),
        _render_top20(ctx),
    ]
    return "\n".join(parts), ctx["dstr"]


def _render_conclusion(ctx: dict) -> str:
    out = ctx["conclusion"]
    mkt = ctx["mkt"]
    latest_short = mkt["short_amount"].iloc[-1] if not mkt.empty else None
    latest_ssr = mkt["ssr"].iloc[-1] if not mkt.empty else None
    sfc_m = ctx["sfc_mkt"]
    if sfc_m.get("available"):
        sfc_val = f"{sfc_m['delta_bps']:+.0f}bp"
        sfc_delta = (f"可比 {sfc_m['n_comparable']} 只 · 覆盖 {sfc_m['coverage']:.0%}"
                     f" · 报告期 {pd.Timestamp(sfc_m['latest_pd']).strftime('%m-%d')}")
    elif ctx["pending"]:
        sfc_val, sfc_delta = "待公布", "已超宽限期，等待 SFC 周报"
    else:
        sfc_val, sfc_delta = "—", "宽限期内 / 可比集合不足"

    cards = render_kpi_cards([
        {"label": "今日全市场沽空额（股票口径）", "value": _fmt_amount(latest_short),
         "delta": f"vs 前{T['daily_intensity_window']}日均值 {_fmt_x(ctx['m20'])}"},
        {"label": "市场加权 SSR（股票口径，不含 ETF/ETP）", "value": _fmt_pct(latest_ssr),
         "delta": (f"前{T['ssr_pct_window']}日分位 {ctx['ssr_pct']:.0f}%"
                   if ctx["ssr_pct"] is not None else "样本不足")},
        {"label": "SFC 须申报淡仓比例变化", "value": sfc_val, "delta": sfc_delta},
    ])
    notes = "".join(
        f'<div class="panel-subtitle">· {_esc(n)}</div>' for n in out["notes"])
    return (f'<div class="panel" id="panel-hk-conclusion">'
            f'<div class="panel-title">市场结论</div>'
            f'<div style="font-size:20px;font-weight:700;color:{COLORS["primary"]};'
            f'margin:8px 0">{_esc(out["state"])}</div>{notes}{cards}</div>')


def _render_market_chart(ctx: dict) -> str:
    fig = go.Figure()
    mkt = ctx["mkt"]
    if not mkt.empty:
        x = mkt["trade_date"].dt.strftime("%Y-%m-%d")
        fig.add_bar(x=x, y=mkt["short_amount"] / 1e8, name="总沽空额·股票口径(亿)",
                    marker_color=COLORS["primary_light"])
        fig.add_scatter(x=x, y=mkt["ssr"] * 100, name="市场加权SSR%(股票口径)",
                        mode="lines", line={"color": COLORS["warning"]}, yaxis="y2")
    for key, label, color in (("HSI", "恒指(归一=100)", "#8c564b"),
                              ("HSTECH", "恒生科技(归一=100)", "#e377c2")):
        s = (ctx["kline"][ctx["kline"]["secid"] == HK_INDEX_SECIDS[key]]
             .sort_values("trade_date") if not ctx["kline"].empty else pd.DataFrame())
        if s.empty:
            continue
        fig.add_scatter(x=s["trade_date"].dt.strftime("%Y-%m-%d"),
                        y=s["close"] / s["close"].iloc[0] * 100, name=label,
                        mode="lines", line={"color": color, "width": 1.2, "dash": "dot"},
                        yaxis="y2")
    fig.update_layout(yaxis={"title": "沽空额(亿港元)", "gridcolor": COLORS["grid"]},
                      yaxis2={"title": "SSR% / 指数(归一)", "overlaying": "y",
                              "side": "right", "gridcolor": COLORS["grid"]})
    note = ""
    if ctx["full_total"] is not None and not pd.isna(ctx["full_total"]) and ctx["full_total"] > 0:
        note = (f"HKEX 全口径总沽空 {_fmt_amount(ctx['full_total'])}"
                + (f"，ETF 占比 {_fmt_pct(ctx['etf_share'])}" if ctx["etf_share"] is not None else ""))
    fig = apply_theme(fig, title="市场总览 · 沽空额 / SSR / 指数",
                      y_title="沽空额(亿港元)", data_date=ctx["dstr"],
                      coverage=None, last_success_at=None, unit=note or None)
    return ('<div class="panel" id="panel-hk-market">'
            + render_figure_to_html(fig, div_id="hk-market-overview") + "</div>")


def _watch_stock_df(code: str, ctx: dict) -> pd.DataFrame:
    code5 = code.split(".")[0]
    em_stock = mx.stock_daily(ctx["em"], code) if not ctx["em"].empty else pd.DataFrame()
    hk_stock = (ctx["hkex"][ctx["hkex"]["code"] == code5].sort_values("trade_date")
                if not ctx["hkex"].empty else pd.DataFrame())
    cols = ["trade_date", "short_shares", "short_amount", "turnover"]
    if not em_stock.empty:
        short_df = em_stock[cols + ["ssr"]].copy()
    elif not hk_stock.empty:
        short_df = hk_stock[cols].copy()
        short_df["ssr"] = short_df["short_amount"] / short_df["turnover"]
    else:
        short_df = pd.DataFrame(columns=cols + ["ssr"])
    k = (ctx["kline"][ctx["kline"]["secid"] == _secid_of(code)].sort_values("trade_date")
         if not ctx["kline"].empty else pd.DataFrame())
    if not k.empty:
        kx = k[["trade_date", "close", "volume", "amount"]].copy()
        kx["chg_pct"] = kx["close"].pct_change() * 100
        df = short_df.merge(kx, on="trade_date", how="outer")
    else:
        df = short_df.copy()
        df["close"] = df["volume"] = df["amount"] = df["chg_pct"] = float("nan")
    if ctx["sfc"].empty:
        oi = pd.DataFrame(columns=["trade_date", "oi_shares", "oi_amount"])
    else:
        oi = (ctx["sfc"][ctx["sfc"]["code"] == code5]
              [["position_date", "short_shares", "short_amount_hkd"]]
              .rename(columns={"position_date": "trade_date", "short_shares": "oi_shares",
                               "short_amount_hkd": "oi_amount"}))
    df = df.merge(oi, on="trade_date", how="left").sort_values("trade_date")
    total = float("nan")
    if not ctx["shares"].empty:
        n = ctx["shares"].loc[ctx["shares"]["code"] == code5, "total_shares"]
        if len(n):
            total = float(n.iloc[0])
    df["oi_pct"] = df["oi_shares"] / total * 100 if total and not pd.isna(total) else float("nan")
    return df.tail(20).reset_index(drop=True)


def _stock_status(code: str, ctx: dict) -> str:
    code5 = code.split(".")[0]
    sd = mx.stock_daily(ctx["em"], code) if not ctx["em"].empty else pd.DataFrame()
    if sd.empty:
        weekly_i = ssr_pct = part = None
    else:
        weekly_i = mx.weekly_intensity(sd["short_amount"])
        ssr_pct = mx.percentile_rank(sd["ssr"], window=T["ssr_pct_window"],
                                     min_obs=T["ssr_pct_min_obs"])
        part = mx.daily_intensity(sd["turnover"], window=T["daily_intensity_window"])
    price = "unavailable"
    if not ctx["kline"].empty:
        s = (ctx["kline"][ctx["kline"]["secid"] == _secid_of(code)]
             .sort_values("trade_date")["close"])
        price = mx.price_direction(mx.ret_n(s, n=5), None,
                                   threshold_bp=T["price_ret_bp"])
    total = float("nan")
    if not ctx["shares"].empty:
        n = ctx["shares"].loc[ctx["shares"]["code"] == code5, "total_shares"]
        if len(n):
            total = float(n.iloc[0])
    sfc_s = (mx.sfc_stock_metrics(ctx["sfc"], code, total)
             if not ctx["sfc"].empty and total and not pd.isna(total)
             else {"available": False})
    return state.stock_conclusion(
        sfc=sfc_s if sfc_s.get("available") else None,
        weekly_short_intensity=weekly_i, ssr_percentile=ssr_pct, price=price,
        participation_high=part is not None and part >= T["participation_high"])["state"]


def _watch_table_html(name: str, code: str, df: pd.DataFrame, status: str) -> str:
    head = "".join(f"<th style='{_TH}'>{_esc(c)}</th>" for c in _COLS)

    def td(v) -> str:
        return f"<td style='{_TD}'>{v}</td>"

    rows = []
    for r in df.itertuples():
        vals = [
            pd.Timestamp(r.trade_date).strftime("%Y-%m-%d"),
            f"{r.short_shares:,.0f}" if pd.notna(r.short_shares) else "—",
            _fmt_amount(r.short_amount),
            f"{r.oi_shares:,.0f}" if pd.notna(r.oi_shares) else "",
            _fmt_amount(r.oi_amount) if pd.notna(r.oi_amount) else "",
            f"{r.close:,.2f}" if pd.notna(r.close) else "—",
            f"{r.chg_pct:+.2f}" if pd.notna(r.chg_pct) else "—",
            f"{r.volume:,.0f}" if pd.notna(r.volume) else "—",
            _fmt_amount(r.amount) if pd.notna(r.amount) else "—",
            f"{r.ssr * 100:.2f}" if pd.notna(r.ssr) else "—",
            f"{r.oi_pct:.2f}" if pd.notna(r.oi_pct) else "",
        ]
        rows.append("<tr>" + "".join(td(v) for v in vals) + "</tr>")
    return (f'<div class="panel" id="panel-hk-watch-{code.split(".")[0]}">'
            f'<div class="panel-title">{_esc(name)} ({_esc(code)})'
            f' <span style="font-size:12px;color:{COLORS["warning"]}">[{_esc(status)}]</span></div>'
            f'<div class="panel-subtitle">最近 20 个交易日；未平仓两列仅 SFC 周报日（周度）有值</div>'
            f'<div style="overflow-x:auto"><table style="border-collapse:collapse;font-size:12px">'
            f"<thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div></div>")


def _render_watch(ctx: dict) -> str:
    parts = [render_section_band(anchor_id="section-hk-watch", num="HK·2",
                                 title="Watch List 逐日明细",
                                 subtitle="股票来自东财；ETF(2800/3033)来自 HKEX；未平仓=SFC 周度")]
    for name, code in HK_WATCH_LIST:
        df = _watch_stock_df(code, ctx)
        parts.append(_watch_table_html(name, code, df, _stock_status(code, ctx)))
    return "\n".join(parts)


def _top20_tag(weekly_i, pct) -> str:
    a = weekly_i is not None and weekly_i >= T["weekly_intensity_high"]
    b = pct is not None and pct >= T["ssr_pct_high"]
    if a and b:
        return "沽空额高·SSR高分位"
    if a:
        return "沽空额高"
    if b:
        return "SSR高分位"
    return "—"


def _render_top20(ctx: dict) -> str:
    em, dstr = ctx["em"], ctx["dstr"]
    if em.empty:
        return ""
    day = em[em["trade_date"] == pd.Timestamp(dstr)]
    if day.empty:
        return ""
    top = day.sort_values("short_amount", ascending=False).head(20)
    rows = []
    for r in top.itertuples():
        hist = mx.stock_daily(em, f"{r.code}.HK")
        pct = (mx.percentile_rank(hist["ssr"], window=T["ssr_pct_window"],
                                  min_obs=T["ssr_pct_min_obs"])
               if not hist.empty else None)
        w_i = mx.weekly_intensity(hist["short_amount"]) if not hist.empty else None
        ssr = r.short_amount / r.turnover if r.turnover else None
        rows.append(
            f"<tr><td style='{_TD}'>{_esc(r.code)}</td>"
            f"<td style='{_TD}'>{_esc(str(r.name))}</td>"
            f"<td style='{_TD}'>{_fmt_amount(r.short_amount)}</td>"
            f"<td style='{_TD}'>{_fmt_pct(ssr)}</td>"
            f"<td style='{_TD}'>{'样本不足' if pct is None else f'{pct:.0f}%'}</td>"
            f"<td style='{_TD}'>{_esc(_top20_tag(w_i, pct))}</td></tr>")
    head = "".join(f"<th style='{_TH}'>{_esc(c)}</th>"
                   for c in ("代码", "名称", "沽空额", "SSR", "SSR 60日分位", "状态标签"))
    return (f'<div class="panel" id="panel-hk-top20">'
            f'<div class="panel-title">当日沽空额 TOP20（股票口径，不含 ETF）</div>'
            f'<div style="overflow-x:auto"><table style="border-collapse:collapse;font-size:12px">'
            f"<thead><tr>{head}</tr></thead><tbody>{''.join(rows)}</tbody></table></div></div>")
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/flow_dashboard/test_hk_panels.py -v`
Expected: 4 passed

注意两点（实现时照做）：
1. `itertuples` 要求列名为合法标识符——`_watch_stock_df` 的列（oi_shares/oi_pct/chg_pct 等）已满足；若 merge 产生 `_x/_y` 后缀说明列冲突，先检查 fixture。
2. `_audit` 测试辅助给 kline 写的 `source_date` 用 trade_date（`_audit` 已处理），与 loader 写入格式一致。

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/render/panels_hk_short.py tests/flow_dashboard/test_hk_panels.py
git commit -m "feat(hk-short): cache-only hk tab panels - conclusion, overview, watch tables, top20"
```

**勘误（质量评审与实施加固记录，b3b63e8 + aceac5b，后续任务依赖不得回退）**：
1. 计划 fixture 缺陷：`_build_cache` 中 00700 两期 SFC `short_amount_hkd` 原文均为 3e8，隐含价 16.48→8.24 跳变 100% 会触发公司行动守卫 → 断言"多空分歧扩大"不可达。修正：09-04 期 amount 改 1.5e8（隐含价 ~16.4926 两期恒定），delta_bp = +10.0（≥5bp → oi=up，价涨 → 多空分歧扩大）。
2. 实施偏离（规格审查已核准的最小修复）：SHARES fixture 行包 `_audit`；watch 面板 id 用 `code.split(".")[0]`（ETF → `panel-hk-watch-2800`，与规格 `{code5}` 等价）。
3. Critical（aceac5b）：SFC 缓存为空时 `pd.DataFrame(columns=[...])` 的 trade_date 为 object dtype，与主表 merge 抛 `ValueError`（真实新装机仅-EM 状态整个 tab 崩溃）→ 空 SFC 分支键列显式 `datetime64[ns]`；补回归测试 `test_render_without_sfc_cache_does_not_crash`（`_build_cache` 加 `with_sfc` 参数）。
4. Minor 清理（aceac5b）：`_price_direction` 删恒真分支；`_render_market_chart` 删被 `apply_theme(y_title)` 覆盖的 yaxis 重复配置（yaxis2 保留）；`weekly_intensity` 显式传 `window_days`/`n_windows`（取自 T）。Step 4 计数勘正：**5 passed**（4 原测试 + 空缓存回归）。
5. 已知豁免留待后续：`_secid_of`/`_code5` 三处重复、`_stock_status` 重复过滤、TOP20 断言锚定弱、hk_date 在 HKEX-only 场景返回空串而非 None——Task 13 集成时注意区分。

### Task 13: pipeline.py 集成 tabs + report_date 双日期

**Files:**
- Modify: `src/flow_dashboard/pipeline.py`
- Test: `tests/flow_dashboard/test_hk_pipeline.py`

设计 §3（同页 tab）+ §7（组合报告保存 ashare_data_date 与 hk_data_date 两个日期；顶层归档文件名沿用触发本次发布的报告日期）。要点：
- `_run_eod_preview_inner` 增加 `report_date` 参数：A股 runner 调用时缺省 = data_date（行为不变）；港股 runner 调用时传自己的触发日期 → 归档文件名/标题/skeleton 用 report_date，A股数据日期单独进 manifest。
- HK tab 渲染封装为模块级 `_render_hk_tab_for_pipeline(as_of)`（只读缓存、无网络无写入），单测可 patch 它；真实运行时缓存为空则返回"数据待更新"横幅（设计 §3：港股故障不拖垮 A股 tab）。
- 现有 4 个 eod_preview 测试不 patch 该 helper —— 真实函数读空缓存返回横幅，安全无网络。

- [ ] **Step 1: 写失败测试**

`tests/flow_dashboard/test_hk_pipeline.py`：

```python
"""pipeline 集成港股 tab：tabs 结构、双日期 manifest、report_date 归档名。"""
import json
from pathlib import Path

import pandas as pd

from flow_dashboard.pipeline import run_eod_preview, _run_eod_preview_inner


def _mock_ashare_empty(monkeypatch):
    """A股 loaders 全部空表（复用 test_pipeline_eod_preview.py 的 mock 模式）。"""
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_etf_share_for_pipeline",
        lambda codes, start, end, as_of: pd.DataFrame(),
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


def test_eod_preview_renders_both_tabs_and_dual_dates(tmp_path, monkeypatch):
    _mock_ashare_empty(monkeypatch)
    monkeypatch.setattr(
        "flow_dashboard.pipeline._render_hk_tab_for_pipeline",
        lambda as_of: ('<div id="hk-x">港股内容</div>', "2026-09-18"),
    )
    output_dir = tmp_path / "x"
    path = run_eod_preview(
        data_date="2026-08-12",
        as_of=pd.Timestamp("2026-08-12 19:30", tz="Asia/Shanghai"),
        output_dir=output_dir,
        lock_path=output_dir / "runners.lock",
    )
    assert "report_2026-08-12_v01.html" in path.name  # A股触发 → report_date=data_date
    html = path.read_text()
    assert 'class="tab-bar"' in html
    assert 'data-tab="ashare"' in html and 'data-tab="hk-short"' in html
    assert 'id="tab-ashare" class="tab-panel active"' in html  # 服务端默认激活 A股
    assert "港股内容" in html
    assert "市场流动性日报 — 2026-08-12" in html
    manifest = json.loads(
        (output_dir / "manifest" / "2026-08-12_v01.json").read_text())
    assert manifest["panel_status"]["ashare_data_date"] == "2026-08-12"
    assert manifest["panel_status"]["hk_data_date"] == "2026-09-18"
    assert "panel-hk-conclusion" in manifest["panels"]
    assert manifest["source_versions"]["hk_short"] == "hk_short_v1"


def test_report_date_controls_archive_and_title(tmp_path, monkeypatch):
    """港股 runner 触发时 report_date != A股 data_date → 归档名/标题用 report_date。"""
    _mock_ashare_empty(monkeypatch)
    monkeypatch.setattr(
        "flow_dashboard.pipeline._render_hk_tab_for_pipeline",
        lambda as_of: ("<div>hk</div>", None),
    )
    output_dir = tmp_path / "y"
    path = _run_eod_preview_inner(
        "2026-08-12", pd.Timestamp("2026-08-13 18:45", tz="Asia/Shanghai"),
        output_dir, None, report_date="2026-08-13")
    assert "report_2026-08-13_v01.html" in path.name
    html = path.read_text()
    assert "市场流动性日报 — 2026-08-13" in html
    manifest = json.loads(
        (output_dir / "manifest" / "2026-08-13_v01.json").read_text())
    assert manifest["panel_status"]["ashare_data_date"] == "2026-08-12"
    assert manifest["panel_status"]["hk_data_date"] is None


def test_hk_tab_helper_delegates_to_panels(tmp_path, monkeypatch):
    """_render_hk_tab_for_pipeline 只读缓存委托 render_hk_short_body。"""
    from flow_dashboard.pipeline import _render_hk_tab_for_pipeline
    monkeypatch.setattr(
        "flow_dashboard.render.panels_hk_short.render_hk_short_body",
        lambda *, as_of, cache_dir=None: ("<b>HK</b>", "2026-09-18"))
    html, d = _render_hk_tab_for_pipeline(
        pd.Timestamp("2026-09-18 19:00", tz="Asia/Shanghai"))
    assert html == "<b>HK</b>" and d == "2026-09-18"
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/flow_dashboard/test_hk_pipeline.py -v`
Expected: FAIL（ImportError: cannot import name '_render_hk_tab_for_pipeline' / '_run_eod_preview_inner' 无 report_date 参数）

- [ ] **Step 3: 实现（pipeline.py 四处修改）**

**修改 1** — 在 `as_of_format(as_of)` 函数后追加模块级 helper：

```python
def _render_hk_tab_for_pipeline(as_of: pd.Timestamp) -> tuple[str, str | None]:
    """渲染港股沽空 tab（只读缓存，无网络/无写入；供单测 patch）。"""
    from flow_dashboard.render.panels_hk_short import render_hk_short_body
    return render_hk_short_body(as_of=as_of)
```

**修改 2** — `_run_eod_preview_inner` 签名与 panel_ids：

```python
def _run_eod_preview_inner(
    data_date: str, as_of: pd.Timestamp, output_dir: Path,
    universe: list[str] | None, report_date: str | None = None,
) -> Path:
```

（`run_eod_preview` / `run_daily_finalize` 两个调用点不改——report_date 缺省 = data_date，行为不变。）

panel_ids 列表末尾追加：

```python
        # NEW (HK short) — 港股 tab 四面板
        "panel-hk-conclusion",
        "panel-hk-market",
        "panel-hk-watch",
        "panel-hk-top20",
    ]
```

**修改 3** — 函数体开头（`is_partial` 计算之前）加：

```python
    report_date = report_date or data_date
```

**修改 4** — 替换 `build_html_skeleton` 调用到 `publish_archive` 调用之间的整段（原 409–441 行）：

```python
    body = "\n".join(body_parts)

    title_suffix = " (partial)" if is_partial else ""
    hk_body, hk_data_date = _render_hk_tab_for_pipeline(as_of)
    full_html = build_html_skeleton(
        title=f"市场流动性日报 — {report_date}{title_suffix}",
        body=body,
        data_date=report_date,
        last_success_at=as_of.strftime("%Y-%m-%d %H:%M CST"),
        footer="市场观察，非交易建议。" + (
            " 本期为 partial：ETF 份额数据尚未完整入库。" if is_partial else ""
        ),
        tabs=[
            {"id": "ashare", "name": "A股资金流", "body": body,
             "nav_sections": [
                 ("section-etf", "01 ETF 被动"),
                 ("section-margin", "02 杠杆资金"),
                 ("section-basis", "03 衍生品"),
                 ("section-periodic", "04 周度/月度"),
             ]},
            {"id": "hk-short", "name": "港股沽空", "body": hk_body,
             "nav_sections": [
                 ("section-hk-conclusion", "HK 结论"),
                 ("section-hk-watch", "HK 明细"),
             ]},
        ],
    )

    _, archive_path, _, _ = publish_archive(
        output_dir=output_dir, data_date=report_date,
        html_body=body,
        manifest_payload={
            "panels": panel_ids,
            "source_versions": {
                "etf_share": "etf_share_size_v1",
                "margin": "margin_v1",
                "fut_daily": "fut_daily_v1",
                "index_daily": "index_daily_v1",
                "hk_short": "hk_short_v1",
            },
            "panel_status": {
                "is_partial": is_partial,
                "ashare_data_date": data_date,
                "hk_data_date": hk_data_date,
            },
        },
        full_html=full_html,
    )
    return archive_path
```

注意：tabs 模式下顶层 `body` 参数仍传（被 theme 忽略），保持参数完整；原 `nav_sections=[...]` 参数删除（已进 tab 内）。

- [ ] **Step 4: 运行确认通过（含回归）**

Run: `python -m pytest tests/flow_dashboard/test_hk_pipeline.py tests/flow_dashboard/test_pipeline_eod_preview.py tests/flow_dashboard/test_pipeline_daily_finalize.py tests/flow_dashboard/test_suffix_invariance_e2e.py -v`
Expected: 全部 passed（现有 4 个 eod_preview 测试不 patch HK helper → 真函数读空缓存返回横幅，无网络）

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/pipeline.py tests/flow_dashboard/test_hk_pipeline.py
git commit -m "feat(hk-short): dual-tab pipeline with report_date and per-market data dates"
```

---

### Task 14: hk_short_pipeline.py 港股 runner + launchd

**Files:**
- Create: `src/flow_dashboard/hk_short_pipeline.py`
- Create: `scripts/flow_dashboard/run_hk_short_eod.py`
- Create: `scripts/launchd/com.ygr.hk-short.eod.plist`
- Test: `tests/flow_dashboard/test_hk_pipeline.py`（追加）

设计 §7 要点：18:45 触发（plist 无 Weekday 键，runner 用香港日历短路休市日）；与 A股 runner 共用 `RUNNERS_LOCK`；**直接调用 `_run_eod_preview_inner`（已持锁，不得嵌套 acquire_runner_lock —— fcntl 非阻塞锁会死锁）**；锁失败保留现有页面记 `skipped_due_to_lock`；港股休市日短路（除非 SFC 宽限期已过需要补抓周报）；report_date = as_of 当日或之前最近的香港交易日。

- [ ] **Step 1: 追加失败测试**

```python
def test_hk_eod_short_circuits_on_non_trading_day(tmp_path, monkeypatch):
    """周六休市且 SFC 无逾期 → 不抓数据不渲染，直接返回 latest.html。"""
    from flow_dashboard import hk_short_pipeline as hp
    monkeypatch.setattr(hp, "_sfc_missing", lambda *, as_of, cache_dir=None: False)

    def boom(*a, **k):
        raise AssertionError("non-trading day must not fetch/render")

    monkeypatch.setattr(hp, "_fetch_hk_increments", boom)
    monkeypatch.setattr("flow_dashboard.pipeline._run_eod_preview_inner", boom)
    out = hp.run_hk_short_eod(
        as_of=pd.Timestamp("2026-09-19 18:45", tz="Asia/Shanghai"),  # 周六
        output_dir=tmp_path, lock_path=tmp_path / "runners.lock")
    assert out.name == "latest.html"


def test_hk_eod_fetches_and_publishes_on_trading_day(tmp_path, monkeypatch):
    from flow_dashboard import hk_short_pipeline as hp
    _mock_ashare_empty(monkeypatch)
    monkeypatch.setattr(
        "flow_dashboard.pipeline._render_hk_tab_for_pipeline",
        lambda as_of: ("<div>hk</div>", "2026-09-18"))
    fetched = {}

    def fake_fetch(as_of):
        fetched["called"] = str(pd.Timestamp(as_of).date())
        return None

    monkeypatch.setattr(hp, "_fetch_hk_increments", fake_fetch)
    out = hp.run_hk_short_eod(
        as_of=pd.Timestamp("2026-09-18 18:45", tz="Asia/Shanghai"),  # 周五
        output_dir=tmp_path, lock_path=tmp_path / "runners.lock")
    assert fetched["called"] == "2026-09-18"
    # report_date = 2026-09-18（触发当日即交易日）
    assert "report_2026-09-18_v01.html" in out.name


def test_hk_eod_skipped_due_to_lock(tmp_path, monkeypatch):
    from flow_dashboard import hk_short_pipeline as hp
    import fcntl

    lock_path = tmp_path / "runners.lock"
    lock_path.touch()
    held = open(lock_path, "w")
    fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # 模拟 A股 runner 持锁
    monkeypatch.setattr(hp, "_fetch_hk_increments",
                        lambda as_of: (_ for _ in ()).throw(AssertionError()))
    out = hp.run_hk_short_eod(
        as_of=pd.Timestamp("2026-09-18 18:45", tz="Asia/Shanghai"),
        output_dir=tmp_path, lock_path=lock_path)
    assert out.name == "latest.html"  # 保留现有页面
    fcntl.flock(held.fileno(), fcntl.LOCK_UN)
    held.close()


def test_sfc_missing_grace_window(tmp_path, monkeypatch):
    from flow_dashboard import hk_short_pipeline as hp
    from flow_dashboard.data.hk_short import loaders
    # 缓存最新一期 = 09-11；最新已完成周 = 09-18，其宽限期至 09-25 EOD
    loaders._write(pd.DataFrame({
        "position_date": [pd.Timestamp("2026-09-11")],
        "checked_at": [pd.Timestamp("2026-09-18")],
    }), tmp_path / loaders.SFC_NONE_FILE)
    loaders._write(pd.DataFrame({
        "code": ["00700"], "position_date": [pd.Timestamp("2026-09-11")],
        "published_at": [pd.Timestamp("2026-09-11 15:41", tz="Asia/Shanghai")],
        "available_at": [pd.Timestamp("2026-09-11 15:41", tz="Asia/Shanghai")],
        "fetched_at": [pd.Timestamp("2026-09-11 19:00", tz="Asia/Shanghai")],
    }), tmp_path / loaders.SFC_FILE)
    # 09-21 周一：09-18 报告的宽限期未到（至 09-25）→ 不算 missing
    assert not hp._sfc_missing(
        as_of=pd.Timestamp("2026-09-21 18:45", tz="Asia/Shanghai"),
        cache_dir=tmp_path)
    # 09-28 周一：宽限期已过仍缺 09-18 → missing（休市日也要跑，补抓 SFC）
    assert hp._sfc_missing(
        as_of=pd.Timestamp("2026-09-28 18:45", tz="Asia/Shanghai"),
        cache_dir=tmp_path)


def test_launchd_plist_and_runner_script_present():
    root = Path(__file__).resolve().parents[2]
    plist = root / "scripts/launchd/com.ygr.hk-short.eod.plist"
    runner = root / "scripts/flow_dashboard/run_hk_short_eod.py"
    assert plist.exists() and runner.exists()
    text = plist.read_text()
    assert "com.ygr.hk-short.eod" in text
    assert "<integer>18</integer>" in text and "<integer>45</integer>" in text
    assert "run_hk_short_eod.py" in text
    assert "<key>Weekday</key>" not in text  # 无 Weekday：休市日靠 runner 日历短路
    assert "run_hk_short_eod" in runner.read_text()
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/flow_dashboard/test_hk_pipeline.py -v -k "hk_eod or sfc_missing or launchd"`
Expected: FAIL（ModuleNotFoundError: hk_short_pipeline）

- [ ] **Step 3: 实现**

`src/flow_dashboard/hk_short_pipeline.py`：

```python
"""港股沽空 EOD runner：18:45 触发，抓增量 + 整页重渲染（含 A股 tab）。

设计 §7：
- 与 A股 runner 共用 RUNNERS_LOCK；本模块持有锁后直接调用
  _run_eod_preview_inner（其内部不再取锁——fcntl 非阻塞锁嵌套会死锁）
- 休市日短路（除非 SFC 最新周报已超宽限期，仍需补抓）
- report_date = as_of 当日或之前最近的香港交易日
"""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from flow_dashboard.config import HK_WATCH_LIST, HK_INDEX_SECIDS, OUTPUT_DIR, RUNNERS_LOCK
from flow_dashboard.data.hk_short.hk_calendar import (
    is_hk_trading_day, latest_trading_day_on_or_before,
)
from flow_dashboard.render.assembly import acquire_runner_lock, RunnerLockError

log = logging.getLogger(__name__)


def _sfc_missing(*, as_of, cache_dir=None) -> bool:
    """最新已完成交易周的 SFC 报告是否已超宽限期（休市日短路例外的判据）。"""
    from flow_dashboard.data.hk_short.loaders import load_sfc_weekly
    from flow_dashboard.indicators import hk_short_state as state
    cached = load_sfc_weekly(as_of=as_of, allow_fetch=False, cache_dir=cache_dir)
    latest = (pd.to_datetime(cached["position_date"]).max()
              if not cached.empty else None)
    return state.sfc_is_pending(latest_cached_pd=latest, as_of=as_of)


def _fetch_hk_increments(as_of) -> None:
    """抓全部港股增量（单源失败只告警，不阻塞发布，设计 §5）。"""
    from flow_dashboard.data.hk_short.loaders import (
        load_em_sellshort, load_etf_master, load_hkex_dayquot,
        load_hk_kline, load_sfc_weekly, load_total_shares,
    )
    load_em_sellshort(as_of=as_of)                       # 全市场逐日（full 标记）
    load_em_sellshort(as_of=as_of, codes=[c for _, c in HK_WATCH_LIST])
    load_hkex_dayquot(as_of=as_of)
    load_sfc_weekly(as_of=as_of)
    secids = list(HK_INDEX_SECIDS.values()) + [
        f"116.{c.split('.')[0].zfill(5)}" for _, c in HK_WATCH_LIST]
    load_hk_kline(as_of=as_of, secids=secids)
    load_total_shares(as_of=as_of, codes=[c for _, c in HK_WATCH_LIST])
    load_etf_master(as_of=as_of)


def run_hk_short_eod(
    *,
    as_of: pd.Timestamp,
    output_dir: Path | str | None = None,
    lock_path: Path | str | None = None,
) -> Path:
    output_dir = Path(output_dir) if output_dir else OUTPUT_DIR
    lock_path = Path(lock_path) if lock_path else RUNNERS_LOCK
    output_dir.mkdir(parents=True, exist_ok=True)

    ts = pd.Timestamp(as_of)
    ts = ts.tz_convert("Asia/Shanghai").tz_localize(None) if ts.tzinfo else ts
    if not is_hk_trading_day(ts) and not _sfc_missing(as_of=as_of):
        log.info("hk_short_eod skipped: %s 非香港交易日且 SFC 无逾期", ts.date())
        return output_dir / "latest.html"

    try:
        with acquire_runner_lock(lock_path):
            _fetch_hk_increments(as_of)
            from flow_dashboard.pipeline import _run_eod_preview_inner
            report_date = latest_trading_day_on_or_before(ts).strftime("%Y-%m-%d")
            return _run_eod_preview_inner(
                report_date, as_of, output_dir, universe=None,
                report_date=report_date)
    except RunnerLockError:
        log.warning("hk_short_eod skipped_due_to_lock at %s", as_of)
        return output_dir / "latest.html"
```

`scripts/flow_dashboard/run_hk_short_eod.py`：

```python
#!/usr/bin/env python3
"""launchd 入口：港股沽空 EOD（18:45）。港股休市日由 run_hk_short_eod 短路。"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from flow_dashboard.config import TIMEZONE  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", default=None,
                        help="回放时点（默认 now，ISO 格式）")
    args = parser.parse_args()

    import pandas as pd
    if args.as_of:
        as_of = pd.Timestamp(args.as_of)
    else:
        as_of = pd.Timestamp.now(tz=str(TIMEZONE))

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    from flow_dashboard.hk_short_pipeline import run_hk_short_eod
    out = run_hk_short_eod(as_of=as_of)
    print(f"published: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

`scripts/launchd/com.ygr.hk-short.eod.plist`（仿现有 plist；注意 `.env` 含 token，只 source 不回显）：

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
 "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key><string>com.ygr.hk-short.eod</string>
    <key>ProgramArguments</key>
    <array>
        <string>/bin/zsh</string>
        <string>-lc</string>
        <string>cd '/Users/xinghuazhang/ygr-project/a股监控' &amp;&amp; set -a &amp;&amp; source .env &amp;&amp; set +a &amp;&amp; exec .venv/bin/python3 scripts/flow_dashboard/run_hk_short_eod.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>18</integer>
        <key>Minute</key><integer>45</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/Users/xinghuazhang/ygr-project/a股监控/logs/flow_dashboard/hk_short_eod.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/xinghuazhang/ygr-project/a股监控/logs/flow_dashboard/hk_short_eod.err.log</string>
</dict>
</plist>
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/flow_dashboard/test_hk_pipeline.py -v`
Expected: 8 passed（Task 13 的 3 个 + 本任务 5 个）

- [ ] **Step 5: Commit**

```bash
git add src/flow_dashboard/hk_short_pipeline.py scripts/flow_dashboard/run_hk_short_eod.py scripts/launchd/com.ygr.hk-short.eod.plist tests/flow_dashboard/test_hk_pipeline.py
git commit -m "feat(hk-short): 18:45 eod runner sharing RUNNERS_LOCK with calendar short-circuit"
```

**勘误（Task 13 质量评审遗留修复，Task 14 必须一并完成，后续任务依赖不得回退）**：
1. Task 13 质量评审批准但遗留一个 Important 问题：`_run_eod_preview_inner` 中 `_render_hk_tab_for_pipeline(as_of)` 调用（pipeline.py:493 附近）未包 try/except——缓存 parquet 损坏导致 render 抛异常时会穿透整个发布路径、跳过 `publish_archive`，A股当日报告整体丢失，违背设计 §3"港股故障不拖垮 A股"。Task 14 实施时必须一并加固：将该调用包 try/except——异常时 log warning 并以"数据待更新"横幅与 None 作为 hk_body/hk_data_date 继续发布。
2. 补测试 `test_hk_tab_render_failure_does_not_block_ashare_publish`（追加到 test_hk_pipeline.py）：`_mock_ashare_empty` + patch `_render_hk_tab_for_pipeline` 抛 RuntimeError，断言发布照常完成（返回的 archive path 存在、HTML 含 A股 tab）且 manifest `panel_status.hk_data_date is None`、HTML 含"数据待更新"。
3. 该加固改动落在 `src/flow_dashboard/pipeline.py`，与 Task 14 一并提交（git add 需含 pipeline.py 与 test_hk_pipeline.py）；Step 4 期望相应变为 **9 passed**（Task 13 的 3 + 本任务原 5 + 加固 1）。

---

### Task 15: backfill_hk_short.py 一次性回补 CLI

**Files:**
- Create: `scripts/flow_dashboard/backfill_hk_short.py`
- Test: `tests/flow_dashboard/test_hk_pipeline.py`（追加）

首日回补历史（EM 卖空 ~1 年、HKEX ~61 自然日窗口内、SFC 周报、指数/watch K线、总股本、LOS 主表）。loader 本身缓存感知（已入库日期/代码跳过），CLI 只负责传窗口参数 → 可中断重跑。注意：EM 首跑约 270 个交易日 × 15 页 ≈ 数千次请求（限流退避下 1–2 小时），用 nohup 跑；HKEX 每日文件 26MB。

- [ ] **Step 1: 追加失败测试**

```python
def test_backfill_cli_wires_windows(tmp_path, monkeypatch):
    """backfill CLI 把窗口参数传给各 loader（SFC 用周数、K线用 secids）。"""
    import importlib.util
    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "backfill_hk_short", root / "scripts/flow_dashboard/backfill_hk_short.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    calls = {}

    def fake_loader(name):
        def f(**kw):
            calls[name] = kw
        return f

    monkeypatch.setattr(mod, "_loaders", lambda: {
        "em_day": fake_loader("em_day"),
        "em_watch": fake_loader("em_watch"),
        "hkex": fake_loader("hkex"),
        "sfc": fake_loader("sfc"),
        "kline": fake_loader("kline"),
        "shares": fake_loader("shares"),
        "los": fake_loader("los"),
    })
    mod.main(["--as-of", "2026-09-18 19:00",
              "--em-days", "10", "--hkex-days", "5",
              "--sfc-weeks", "4", "--kline-days", "30", tmp_path.as_posix()])
    assert calls["em_day"]["start"] == pd.Timestamp("2026-09-08")
    assert calls["hkex"]["start"] == pd.Timestamp("2026-09-13")
    assert calls["sfc"]["weeks"] == 4
    assert calls["kline"]["start"] == pd.Timestamp("2026-08-19")
    assert "116.00700" in calls["kline"]["secids"]
    assert "100.HSI" in calls["kline"]["secids"]
    assert [c for _, c in
            __import__("flow_dashboard.config", fromlist=["HK_WATCH_LIST"])
            .HK_WATCH_LIST] == calls["shares"]["codes"]
```

- [ ] **Step 2: 运行确认失败**

Run: `python -m pytest tests/flow_dashboard/test_hk_pipeline.py -v -k backfill`
Expected: FAIL（FileNotFoundError）

- [ ] **Step 3: 实现**

```python
#!/usr/bin/env python3
"""港股沽空一次性回补：EM 卖空历史 / HKEX 窗口 / SFC 周报 / K线 / 总股本 / LOS。

用法（首日，数小时级，建议 nohup）：
  nohup .venv/bin/python3 scripts/flow_dashboard/backfill_hk_short.py \
      [--as-of '2026-09-18 19:00'] [cache_dir] &
loader 缓存感知，可中断重跑（已入库增量自动跳过）。
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd  # noqa: E402

from flow_dashboard.config import (  # noqa: E402
    HK_INDEX_SECIDS, HK_SHORT_CACHE_DIR, HK_WATCH_LIST,
)

log = logging.getLogger(__name__)


def _loaders():
    from flow_dashboard.data.hk_short.loaders import (
        load_em_sellshort, load_etf_master, load_hkex_dayquot,
        load_hk_kline, load_sfc_weekly, load_total_shares,
    )
    return {
        "em_day": load_em_sellshort,
        "em_watch": load_em_sellshort,
        "hkex": load_hkex_dayquot,
        "sfc": load_sfc_weekly,
        "kline": load_hk_kline,
        "shares": load_total_shares,
        "los": load_etf_master,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--as-of", default=None)
    parser.add_argument("--em-days", type=int, default=400)
    parser.add_argument("--hkex-days", type=int, default=70)
    parser.add_argument("--sfc-weeks", type=int, default=12)
    parser.add_argument("--kline-days", type=int, default=400)
    parser.add_argument("cache_dir", nargs="?", default=None)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    as_of = (pd.Timestamp(args.as_of, tz="Asia/Shanghai") if args.as_of
             else pd.Timestamp.now(tz="Asia/Shanghai"))
    cache_dir = Path(args.cache_dir) if args.cache_dir else HK_SHORT_CACHE_DIR

    watch_codes = [c for _, c in HK_WATCH_LIST]
    secids = list(HK_INDEX_SECIDS.values()) + [
        f"116.{c.split('.')[0].zfill(5)}" for c in watch_codes]

    L = _loaders()
    em_start = as_of.tz_localize(None).normalize() - pd.Timedelta(days=args.em_days)
    log.info("backfill EM sellshort %s 起（首跑约 1-2 小时）", em_start.date())
    L["em_day"](as_of=as_of, start=em_start, cache_dir=cache_dir)
    L["em_watch"](as_of=as_of, codes=watch_codes, start=em_start, cache_dir=cache_dir)
    hkex_start = as_of.tz_localize(None).normalize() - pd.Timedelta(days=args.hkex_days)
    log.info("backfill HKEX dayquot %s 起（每日 26MB）", hkex_start.date())
    L["hkex"](as_of=as_of, start=hkex_start, cache_dir=cache_dir)
    log.info("backfill SFC %d 周", args.sfc_weeks)
    L["sfc"](as_of=as_of, weeks=args.sfc_weeks, cache_dir=cache_dir)
    kline_start = as_of.tz_localize(None).normalize() - pd.Timedelta(days=args.kline_days)
    log.info("backfill kline %s 起", kline_start.date())
    L["kline"](as_of=as_of, secids=secids, start=kline_start, cache_dir=cache_dir)
    L["shares"](as_of=as_of, codes=watch_codes, cache_dir=cache_dir)
    L["los"](as_of=as_of, cache_dir=cache_dir)
    log.info("backfill done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 运行确认通过**

Run: `python -m pytest tests/flow_dashboard/test_hk_pipeline.py -v -k backfill`
Expected: 1 passed

- [ ] **Step 5: Commit**

```bash
git add scripts/flow_dashboard/backfill_hk_short.py tests/flow_dashboard/test_hk_pipeline.py
git commit -m "feat(hk-short): resumable backfill cli for all six cache datasets"
```

---

### Task 16: @live 冒烟测试

**Files:**
- Create: `tests/flow_dashboard/test_hk_live.py`

conftest 已有逻辑：`@pytest.mark.live` 默认 skip，`--run-live` 显式开启。动态日期（不硬编码今天）：`latest_trading_day_on_or_before(now - 1d)`、`recent_sfc_position_dates(now, 1)[0]`。上线前跑一次全绿再装 launchd。

- [ ] **Step 1: 实现（live 测试不先跑失败验证）**

```python
"""港股数据源真实抓取冒烟测试（@live，--run-live 开启）。

行数基准来自 docs/港股沽空/source-validation.md（2026-09-18 实测）：
EM 单日 ~745 行；HKEX dayquot ~843 行；SFC 单期数百行；f84(00700)=9,095,085,993。
"""
import pandas as pd
import pytest

from flow_dashboard.config import HK_INDEX_SECIDS, HK_WATCH_LIST
from flow_dashboard.data.hk_short import em_client, hkex_client, sfc_client
from flow_dashboard.data.hk_short.hk_calendar import (
    latest_trading_day_on_or_before, recent_sfc_position_dates,
)

pytestmark = pytest.mark.live


def _now():
    return pd.Timestamp.now(tz="Asia/Shanghai")


def _last_trading_day():
    return latest_trading_day_on_or_before(_now().tz_localize(None) - pd.Timedelta(days=1))


def test_live_em_sellshort_day():
    d = _last_trading_day()
    df = em_client.fetch_sellshort_day(d)
    assert len(df) > 600, f"EM 单日行数异常: {len(df)} @ {d.date()}"
    assert df["short_amount"].sum() > 1e10  # >100 亿港元量级


def test_live_hkex_dayquot_rows():
    d = _last_trading_day()
    df = hkex_client.fetch_dayquot(d)
    assert df is not None and len(df) > 0
    codes = df["code"].nunique()
    assert 700 <= codes <= 950, f"dayquot 证券数异常: {codes} @ {d.date()}"


def test_live_sfc_latest_week():
    pos = recent_sfc_position_dates(_now().tz_localize(None), n=1)[0]
    df = sfc_client.fetch_sfc_week(pos, fetched_at=_now())
    if df is not None:  # 假日周允许 None
        assert len(df) > 100
        assert df["published_at"].notna().all()


def test_live_kline_and_total_shares():
    d = _last_trading_day()
    k = em_client.fetch_kline(HK_INDEX_SECIDS["HSI"],
                              d - pd.Timedelta(days=30), d, now=_now())
    assert not k.empty and k["trade_date"].max() <= d
    assert em_client.fetch_total_shares("00700") == 9095085993


def test_live_list_of_securities():
    los, eff = hkex_client.fetch_list_of_securities()
    assert len(los) > 5000
    assert eff  # 生效日期非空（"Updated as at ..."）
    assert len(hkex_client.etf_set(los)) > 350  # ETP ~411
```

- [ ] **Step 2: 运行（显式开启 live）**

Run: `python -m pytest tests/flow_dashboard/test_hk_live.py -v --run-live`
Expected: 5 passed（HKEX prev 段若行数越界，回到 Task 5 `_ROW_RE` 收紧段边界）

Run（默认 skip 验证）: `python -m pytest tests/flow_dashboard/test_hk_live.py -v`
Expected: 5 skipped

- [ ] **Step 3: Commit**

```bash
git add tests/flow_dashboard/test_hk_live.py
git commit -m "test(hk-short): live smoke tests for all frozen sources"
```

**勘误（实施与双阶段审查记录，d9fb438，收尾步骤依赖不得回退）**：
1. 计划前提错误：仓库 conftest 此前**并无** `--run-live` 逻辑（计划"conftest 已有逻辑"不实，原逻辑只有 tushare token 门槛）。实施时在 `tests/flow_dashboard/conftest.py` 新增 `pytest_addoption` 注册 `--run-live`（store_true）+ 收集期对 live 标记测试默认 skip（reason="live 测试默认跳过；--run-live 显式开启"）+ 开启后保留原 token 门槛作第二层。副作用：5 个既有 live 标记文件（test_tushare_*/test_sina_* 等）从"有 token 即跑"变为"须显式 `--run-live`"——规范审查裁决为计划意图内的正确泛化。
2. 已知限制（质量审查批准留待跟进，不影响默认流程与已验证路径）：a) `pytest_addoption` 位于非根 conftest，`--run-live` 仅当初始参数含 `tests/flow_dashboard` 路径时可解析（本计划所有命令均带该路径，成立）；b) `test_live_sfc_latest_week` 在报告未公布窗口（约 position_date+7 之前）空转通过——计划冻结文本如此，后续可改为遍历 `recent_sfc_position_dates(now, 2)` 要求至少一期非 None；c) f84 `== 9095085993` 精确等值断言会因腾讯回购注销而漂移，届时按实测更新并同步 source-validation.md。
3. 规范审查确认的 4 处偏离（均合规）：删除未用导入 `HK_WATCH_LIST`（F401）；ruff format 重排；conftest 顺带修复既有 lint（未用 `import os`、导入排序）；commit 信息照抄计划原文。

---

## 最终整体审查记录（20f918e..d9fb438 全量 diff 审查 + 复核，不得回退）

**结论：Critical 0 / Important 1（已修复复核通过）/ Minor 2（记录为已知事项，不改码）——分支批准收尾。**

**Important #1（已修复，2efabc3 + 复核通过）**：分支触碰文件存在真实 ruff check / ruff format 违规——此前多个任务级质量审查误报"ruff 绿"，最终整体审查实测揭穿。修复：机械清理子代理仅对分支触碰的 17 个文件执行 `ruff check --fix` + `ruff format`（16 处 auto-fix + 17 处重排，0 手工改动、0 noqa、0 配置放宽），提交 2efabc3。复核（独立审查代理）确认：26 个触碰文件 check/format 全绿；diff 逐文件抽样为纯格式重排（引号规范化、签名重排、切片空格、fixture 缩进），无逻辑/断言变化；提交范围恰好等于触碰文件集，未改 pyproject/ruff 配置；回归 227 passed / 17 skipped / 1 deselected 与修复前逐项一致。
- 教训记录：任务级审查中"ruff 绿"结论必须由审查者**实际运行命令**得出，不得采信实现者转述；本计划后续任何改动沿用"触碰文件必须 check+format 双绿"标准。
- 遗留（留给人类决策）：仓库无 `[tool.ruff]` 配置、ruff 0.16.2 未钉版，未触碰文件存在 ~103 处既有违规（基线红）；建议仓库级落 ruff 配置并钉版本，属仓库治理范畴，不在本分支强行统一。

**Minor #2（已知事项，不改码）**：manifest `panels` 声明的逻辑 id `panel-hk-watch` 与实际渲染 id `panel-hk-watch-{code5}`（如 `panel-hk-watch-00700`，panels_hk_short.py）前缀不一致——下游若按 manifest 逐 id 映射 DOM 会落空。该 id 是 Task 13 冻结的逻辑分组 id（manifest 语义为"面板清单"而非"DOM 锚点清单"），保留不改；后续若做面板级健康检查，须按前缀匹配或改为逐证券展开。

**Minor #3（已知事项，不改码）**：A股权衡休市而港股开市的日子（如国庆 10-01），港股 runner 触发的报告中 `manifest.panel_status.ashare_data_date` 记录的是触发日口径的 report_date 相关值而非该日真实 A股 数据日。`is_partial` 标志与双日期设计已缓解歧义，且与 Task 13/14 冻结代码一致，属设计层观察——如需精确，后续可在 manifest 增加 `ashare_real_data_date` 字段。

---

## 收尾

1. 全量回归：`python -m pytest tests/flow_dashboard/ -v`（排除 live）全绿。
2. 首日回补（数小时，nohup）：`nohup .venv/bin/python3 scripts/flow_dashboard/backfill_hk_short.py &`。
3. 手动触发一次 runner 验证发布：`.venv/bin/python3 scripts/flow_dashboard/run_hk_short_eod.py --as-of "$(date '+%Y-%m-%d %H:%M')"`，浏览器打开 `current.html` 检查两个 tab、hash 记忆、港股面板。
4. 安装 launchd：`cp scripts/launchd/com.ygr.hk-short.eod.plist ~/Library/LaunchAgents/ && launchctl load ~/Library/LaunchAgents/com.ygr.hk-short.eod.plist`。
5. 次日检查 `logs/flow_dashboard/hk_short_eod.log` 与页面日期。




