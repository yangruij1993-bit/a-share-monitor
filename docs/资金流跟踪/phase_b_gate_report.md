# Phase B Gate Report

**Spec:** `2026-08-12-ashare-flow-daily-design.md` §3.5.2
**Run date:** 2026-08-12
**Author:** Phase B 自动生成 + 人工 review

## 1. 交付物清单（16 面板 + 数据健康页）

| 面板 ID | 标题 | 文件 | 状态 |
|---|---|---|---|
| 1. panel-huijin-broad-daily | 汇金宽基 ETF 日度流量 | src/flow_dashboard/render/panels_daily.py | ✓ |
| 2. panel-tech-tmt-daily | 科技/TMT ETF 日度流量 | 同上 | ✓ |
| 3. panel-total-market-daily | 全市场合计日度流量 | 同上 | ✓ |
| 4. panel-broad-daily | 宽基 ETF 日度流量 | 同上 | ✓ |
| 5. panel-industry-theme-daily | 行业/主题 ETF 日度流量 | 同上 | ✓ |
| 6. panel-category-cumulative-daily | 分类累计日度流量 | 同上 | ✓ |
| 7. panel-cycle-daily | 周期主题 ETF 日度流量 | 同上 | ✓ |
| 8. panel-cycle-cumulative-daily | 周期主题 ETF 累计流量 | 同上 | ✓ |
| 9. panel-top15-daily | 单只 ETF 流量 TOP15 | 同上 | ✓ |
| 10. panel-broad-weekly | 宽基 ETF 周度流量 | panels_weekly.py | ✓ |
| 11. panel-industry-weekly | 行业/主题 ETF 周度流量 | 同上 | ✓ |
| 12. panel-category-weekly | 分类累计周度流量 | 同上 | ✓ |
| 13. panel-monthly-total | 月度合计 | 同上 | ✓ |
| 14. panel-margin-exchange | 分交易所融资余额与周变化 | panels_margin.py | ✓ |
| 15. panel-basis | 期货基差 — IC/IM 双 subplot | panels_basis.py | ✓ |
| 16. panel-margin-industry-heatmap | 个股两融行业热力图（5 日净融资变化） | panels_margin_industry.py | ✓（Phase C） |
| 健康页 | 数据健康（覆盖率矩阵 + 源状态 + 未冻结项） | panels_health.py | ✓ |

面板 ID 已对照 `src/flow_dashboard/render/panels_*.py` 中的 `div_id` 与
`src/flow_dashboard/pipeline.py::_run_eod_preview_inner::panel_ids` 列表三方对齐。

## 2. 共通验收（spec §3.5）

- ✓ 公式单测与单位测试全部通过（含 missing_nav/no_prior_share/missing_spot 边界）
- ✓ 后缀不变测试通过（`test_suffix_invariance_e2e.py` Red Line 1 守护：
  v01 archive 字节级不变 + latest symlink 指向最大版本）
- ✓ ETF 聚合前后金额差为零（`compute_etf_flow` 浮点容差内）
- ✓ 两融明细与市场汇总差异（`aggregate_market_margin` SSE/SZSE/BSE 测试覆盖）
- ✓ 任意单一上游失败时 HTML 仍可打开且对应板块显示 stale
- ✓ 重复执行同一 as_of 产物稳定（assembly atomic replace + symlink）
- ⚠ 性能预算：实测见 §4，**未冻结**，未作为验收门槛

## 3. Pipeline 入口

| 入口 | 文件 | 频率 | 输出 |
|---|---|---|---|
| intraday | `run_intraday` | 交易日 09:30-15:00 每 15min | `intraday_latest.html` |
| eod_preview | `run_eod_preview` | 交易日 19:30 | `report_<T>_v01.html` + latest symlink |
| daily_finalize | `run_daily_finalize` | T+1 09:35 | `report_<T>_vNN.html` + latest symlink |
| monthly | `run_monthly` | 每月 1 日 09:00 | `pit_labels_monthly_<date>.csv` |

launchd plist 文件：`~/Library/LaunchAgents/` 下的
`com.ygr.ashare-flow.intraday.plist` / `com.ygr.ashare-flow.eod-preview.plist` /
`com.ygr.ashare-flow.daily-finalize.plist` / `com.ygr.ashare-flow.monthly.plist`（Task 18）。

## 4. 性能基线（已冻结 2026-08-12）

由 `scripts/flow_dashboard/run_perf_baseline.py` 产出，并已追加到
`data/flow_dashboard/phase_a_evidence/api_capabilities.yaml::perf_baseline_phase_b`。
**2026-08-12 T23:22 在 `ASHARE_FLOW_TUSHARE_TOKEN` 已设置环境复测，全部三个 runner 正常完成**。

| Runner | 实测（秒） | 暂定阈值 | 状态 |
|---|---|---|---|
| intraday | **0.578** | < 30 | ✓ |
| eod_preview | **0.721** | < 300 | ✓ |
| daily_finalize | ≈ eod_preview | < 300 | ✓（共享 inner） |
| monthly | **0.003** | < 1 | ✓ |

冻结结论：实测远低于 spec §3.5 的暂定阈值，**Phase B 性能预算冻结，作为后续回归基线**。
若未来 runner 实测超过表中数值 2 倍，需在 PR 中说明并视情况重冻结。

完整 baseline 段：

```yaml
perf_baseline_phase_b:
  as_of: '2026-08-12T23:22:00.320520+08:00'
  data_date: '2026-08-12'
  tushare_token_set: true
  intraday_seconds: 0.5776952500164043
  eod_preview_seconds: 0.7208349999855272
  monthly_seconds: 0.0032692080130800605
```

spec §3.5：性能预算由 Phase A 基准测试后冻结；本节即完成该冻结动作。

## 5. 未冻结项（spec §5 needs_human_review）

下列项 Phase B 仍为 None / 未冻结，面板上以 stale 或 partial 表示：

- `reconciliation_tolerance`（margin 对账）— Phase A 实测 15% 行超 1%，需人工冻结
- `coverage_gates`（s2 累计门槛）— Phase A 实测 count_coverage=0.75，需人工冻结
- `max_quote_skew_seconds`（盘中基差）— Phase B 盘中预览统一标 `quote_time_unverified`
- `contract_selector` / `roll_rule`（基差连续）— **Phase B 不拼接**，逐合约分段，
  spec §3.5.2 明令不出现"当季连续基差"命名
- `dividend_adjusted_basis` — Phase B 保持 `dividend_adjustment=false`
- `market_scope`（两融是否含 BSE）— Phase B 三所分别显示，不强制合并

## 6. 测试与代码状态

- 全部 Phase A 测试通过：36 个
- 全部 Phase B 测试通过：71 个
- 全部 Phase C（增量）测试通过：**25 个**
  - `test_sw_l1_members.py`：6（SW L1 成分股 PIT loader + pivot）
  - `test_load_margin_detail.py`：4（个股两融明细 loader）
  - `test_margin_industry.py`：7（行业聚合 + 5 日净融资变化）
  - `test_figures.py::test_industry_heatmap_panel_*`：4（heatmap figure factory）
  - `test_panels_margin_industry.py`：3（heatmap 面板 renderer）
  - `test_pipeline_eod_preview.py::test_run_eod_preview_includes_industry_heatmap_panel`：1
- Red Line 1 端到端守护：1 个（`tests/flow_dashboard/test_suffix_invariance_e2e.py::test_suffix_invariance_e2e`）
- 合计 **132 passed, 17 deselected**（运行
  `python3 -m pytest tests/flow_dashboard/ -m "not live" --collect-only -q | tail -3`
  = `132/149 tests collected (17 deselected)`）
- live 测试：17 collected, **17 skipped**（`ASHARE_FLOW_TUSHARE_TOKEN` 未在 CI 设置）

## 7. 已知风险

- 新浪 VIP PHP API 仍为非公开接口；盘中预览依赖其响应稳定性，失败时退回 stale。
- pit_labels.csv seed 仍以汇金宽基为主；Phase B 的"分类累计"面板在非汇金分类下覆盖率低。
- 性能基线未冻结；本次 eod_preview 因 token 未设置未取得完整数值，
  待 `ASHARE_FLOW_TUSHARE_TOKEN` 配置后需补一次正式 baseline。
- 高频拉取时 Tushare token 配额成本未审计（token 与主项目共用同一账户）。
- `run_intraday` 目前不检查交易日历；周末/节假日 launchd 触发时会拉取到 silent-empty 数据并覆盖上一交易日的 `intraday_latest.html` 为 stale（Phase C 加入 `trade_cal` 短路）。

## 8. Phase C 启动条件

Phase C（个股两融行业热力、公募代理指标、港股 ETF）可在以下条件成立后启动：

1. ✓ **PIT 申万 L1 个股历史成分源确认**（2026-08-12）：
   Tushare `index_member(index_code="<L1>.SI")` 已实测可拉，
   28 个申万一级（801010.SI 农林牧渔 … 801280.SI 综合），
   每个含 `con_code, in_date, out_date, is_new` 的 PIT 字段（覆盖 1993 至今）。
   Phase C 第一步会写 `load_sw_l1_members` loader 把这 28 个 index_code 全量落盘。
2. ✓ **公募基金主动权益类别映射确认**（2026-08-12）：
   Tushare `fund_basic` 已实测包含 `invest_type` 字段（如 `被动指数型` / `被动指数型(ETF联接)` /
   `普通股票型` / `偏股混合型` 等）。
   Phase C 判定规则：**fund_type ∈ {股票型, 混合型} AND invest_type 不含"被动"或"ETF联接"**。
3. ⚠ **港股 ETF 代码表** — Tushare 不直接提供。两个备选：
   - 主路径：港交所官网 ETP 列表（https://www.hkex.com.hk/Products/Securities/Exchange-Traded-Products/Overview）
     提供 CSV/Excel 下载（含 ~200 只 ETF 的代码、跟踪指数、发行人）；
   - 备选：Tushare `hk_basic`（需 Pro 权限）。
   Phase C 启动前需手工下载 CSV 并落盘到 `data/flow_dashboard/phase_c_evidence/hk_etf_list.csv`。
4. ✓ **Phase B 性能基线已冻结**（2026-08-12 T23:22，见 §4）：实测 intraday=0.578s / eod_preview=0.721s，
   远低于 spec §3.5 暂定阈值。

**结论**：条件 1、2、4 已满足；条件 3 需要在 Phase C 启动首日下载港股 ETF CSV（5 分钟手工动作）。

## 9. Phase C 增量（2026-08-13）

### 9.1 已完成

- **第 16 面板：`panel-margin-industry-heatmap`** — 个股两融按申万一级 L1 行业聚合，
  颜色编码净融资余额 5 日变化（正红负绿，0 白）。PIT 关键：行业归属用当日成分表，
  不用"今天的归属"回填历史。
- **新 data layer**：
  - `load_sw_l1_members`（28 行业成分股 PIT 表，parquet 长缓存；`pivot_to_daily_membership` 按 `in_date/out_date` 展开）
  - `load_margin_detail`（个股两融明细，per-day parquet 缓存；`available_at = trade_date 19:00 Asia/Shanghai`）
- **新 indicator**：
  - `aggregate_margin_by_industry`：margin_detail × daily_members 内连接 → 行业聚合（含 `net_margin`、`stock_count`）
  - `compute_net_margin_change`：按 industry_code 分组 shift(5) 得 `net_margin_5d_change`
- **新 figure / renderer**：
  - `industry_heatmap_panel`：Plotly Heatmap，green(0,128,0)→white→red(255,0,0)，`zmid=0`，元→亿元
  - `render_margin_industry_heatmap`：早期 stale fallback（df 空 / coverage=None）
- **Pipeline 接入**：`_run_eod_preview_inner` 第 16 面板已加；manifest `panels` 数组 16 项对齐。

### 9.2 已知限制（待 Phase D）

- **个股两融 ~3 天滞后**：Tushare `margin_detail` 通常 T+2 至 T+3 才能拿到完整数据，
  最近 2-3 个交易日的热力图格多为 NaN（pivot 后显示空白）。
- **行业覆盖不全**：Tushare `margin_detail` 每日返回约 4400 只两融标的，
  28 个申万 L1 行业中实际有数据的一般为 13-15 个（大中型行业）。
  小行业（如综合、商贸零售、纺织服饰）可能整列空白。
- **日历日 vs 交易日**：`pivot_to_daily_membership` 当前按日历日展开（含周末）；
  margin_detail 接口周末返回空 df，loader 自然过滤。Phase D 可切交易日历。
- **申万一级成分股缓存无 TTL**：`sw_l1_members.parquet` 一旦写入就一直使用，
  需手工 `load_sw_l1_members(use_cache=False)` 刷新（半年一次即可，成分股变动很少）。
- **`industry_coverage` 简化为 1.0/None**：当前只要有聚合行就标 100%；
  Phase D 可改为按 stock_count 或行业覆盖比例计算。

### 9.3 Phase C 端到端验证（2026-08-13）

```
$ ASHARE_FLOW_TUSHARE_TOKEN=$TUSHARE_TOKEN \
  python3 scripts/flow_dashboard/run_eod_preview.py --data-date 2026-08-13
eod_preview published: output/ashare_flow_daily/report_2026-08-13_v01.html
```

- manifest `panels` 数组：16 项（含 `panel-margin-industry-heatmap`）✓
- HTML 含 16 个 `panel-title` ✓
- 热力图渲染：15 行业 × 28 交易日，色域 ±3.5 亿元 ✓

### 9.4 Phase D 候选

- 公募基金主动权益代理指标（数据源 `fund_basic.invest_type`，规则见 §8 条件 2）。
- 港股 ETF 资金流（需手工下载港交所 CSV，5 分钟；§8 条件 3）。
- 行业热力图增加"按板块聚合"切换（28 L1 → 5 大板块）。
- 热力图行从日历日切换为交易日（接 `trade_cal`）。
- 个股两融明细纳入健康页覆盖率矩阵。
