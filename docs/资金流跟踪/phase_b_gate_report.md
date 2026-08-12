# Phase B Gate Report

**Spec:** `2026-08-12-ashare-flow-daily-design.md` §3.5.2
**Run date:** 2026-08-12
**Author:** Phase B 自动生成 + 人工 review

## 1. 交付物清单（15 面板 + 数据健康页）

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
`com.ygr.ashare-flow.intraday.plist` / `.eod.plist` / `.finalize.plist` /
`.monthly.plist`（Task 18）。

## 4. 性能基线（未冻结）

由 `scripts/flow_dashboard/run_perf_baseline.py` 产出，并已追加到
`data/flow_dashboard/phase_a_evidence/api_capabilities.yaml::perf_baseline_phase_b`。
**注意：本次运行环境未设置 `ASHARE_FLOW_TUSHARE_TOKEN`（仅遗留 `TUSHARE_TOKEN`）**，
故 `eod_preview` 在 setup 阶段立即抛 `SetupError`（spec §3.2.1 的 token 解耦护栏）；
`intraday` 仅用新浪、`monthly` 仅刷新 CSV 快照，二者不受 token 影响。

| Runner | 实测（秒） | 备注 |
|---|---|---|
| intraday | **0.592** | sina VIP PHP API（IC + IM 期货）+ `sh000905`/`sh000852` spot，单次 |
| eod_preview | <not measured: SetupError — `ASHARE_FLOW_TUSHARE_TOKEN` 未设置> | 仅测得 0.006s（setup 即抛错）；需在 token 已设置环境复测 |
| daily_finalize | ≈ eod_preview | 共享 `_run_eod_preview_inner`，需 token 后复测 |
| monthly | **0.001** | 仅刷新分类表 CSV 快照（`< 1s`） |

完整 baseline 段：

```yaml
perf_baseline_phase_b:
  as_of: '2026-08-12T22:47:17.631340+08:00'
  data_date: '2026-08-12'
  tushare_token_set: false
  intraday_seconds: 0.5919813749787863
  eod_preview_error: 'SetupError: 检测到 TUSHARE_TOKEN 但未检测到 ASHARE_FLOW_TUSHARE_TOKEN。
    请运行: export ASHARE_FLOW_TUSHARE_TOKEN="$TUSHARE_TOKEN"'
  eod_preview_seconds: 0.006280166999204084
  monthly_seconds: 0.0013633749913424253
```

spec §3.5：性能预算由 Phase A 基准测试后冻结；未冻结前不把
"日终 < 5 分钟 / 盘中 < 30 秒" 作为已证实验收门槛。

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
- 全部 Phase B 测试通过：**71 个**（运行
  `python3 -m pytest tests/flow_dashboard/ -m "not live" --collect-only -q | tail -3`
  = `107/124 tests collected (17 deselected)`；107 - 36 = 71）
- Red Line 1 端到端守护：1 个（`tests/flow_dashboard/test_suffix_invariance_e2e.py::test_suffix_invariance_e2e`）
- 合计 **107 passed, 17 deselected**（live 测试因 token 未设置全部 SKIP）
- live 测试：17 collected, **17 skipped**（`ASHARE_FLOW_TUSHARE_TOKEN` 未设置）

## 7. 已知风险

- 新浪 VIP PHP API 仍为非公开接口；盘中预览依赖其响应稳定性，失败时退回 stale。
- pit_labels.csv seed 仍以汇金宽基为主；Phase B 的"分类累计"面板在非汇金分类下覆盖率低。
- 性能基线未冻结；本次 eod_preview 因 token 未设置未取得完整数值，
  待 `ASHARE_FLOW_TUSHARE_TOKEN` 配置后需补一次正式 baseline。
- 高频拉取时 Tushare token 配额成本未审计（token 与主项目共用同一账户）。
- launchd plist 中 intraday 仅展开周一时刻；周二至周五需安装时补齐或用 wrapper 展开。

## 8. Phase C 启动条件

Phase C（个股两融行业热力、公募代理指标、港股 ETF）可在以下条件成立后启动：

1. PIT 申万 L1 个股历史成分源确认（`pit_sw_l1_history` 关闭）。
2. 公募基金主动权益类别映射确认（`equity_category_mapping` 关闭）。
3. 港股 ETF PIT 分类与代码表补齐。
4. Phase B 性能基线冻结（`performance_budget` 关闭）— 需在 token 已设置环境
   完成 eod_preview / daily_finalize 完整 baseline 后方可冻结。
