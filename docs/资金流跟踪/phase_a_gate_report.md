# Phase A Gate Report

**Spec:** `2026-08-12-ashare-flow-daily-design.md` §3.5.1
**Run date:** 2026-08-12
**Author:** Phase A 自动生成 + 人工 review

## 1. 交付物清单

| 文件 | 路径 | 状态 |
|---|---|---|
| api_capabilities.yaml | `data/flow_dashboard/phase_a_evidence/api_capabilities.yaml` | ✓ 含 live_sample |
| ETF PIT 标签表 | `data/flow_dashboard/phase_a_evidence/etf_pit_labels.csv` | seed (待扩充) |
| 源切换对账 | `data/flow_dashboard/phase_a_evidence/source_switch_reconcile.csv` | ✓ 587 rows |
| 覆盖率基线 | `data/flow_dashboard/phase_a_evidence/coverage_baseline.csv` | ✓ 1024 rows |
| 可得性轮询 | `data/flow_dashboard/phase_a_evidence/share_polling/poll_summary.csv` | ✓ complete |

## 2. 实测可得性结论

(api_capabilities.yaml 的 live_sample 段已经记录每个 endpoint 实际行数与首次观测时间。)

- Tushare: `fund_basic`, `etf_share_size`, `fund_nav`, `fund_daily`, `margin`,
  `fut_basic`, `fut_daily`, `index_daily` — 全部返回非空样本。
- 新浪: `fetch_futures_node("IC")` 返回 5 条活跃合约、`fetch_spot_indices(["sh000905","sh000852"])`
  返回 2 条 — 全部非空。`hq.sinajs.cn/list=` 不支持 CFFEX 期货，已固定使用 VIP PHP API。
- 可得性轮询：trade_date=20260811 的 4 只 seed ETF 全部命中（status=complete, coverage_rate=1.0）。

## 3. 已冻结的契约

- 单位：份额 → 份（万份 × 10000）；金额 → 元（万元 × 10000）。
- CFFEX 期货新浪 node mark：`IC=zzgz_qh`, `IM=im_qh`, `IF=qz_qh`, `IH=szgz_qh`。
- 现货指数新浪代码：CSI500=`sh000905`, CSI1000=`sh000852`。
- Tushare 期货代码后缀：`.CFX`（CFFEX）。
- `etf_share_size` 的 `total_size` 字段单位 = 万元（落盘前转元）。
- `etf_share_size` endpoint 不返回 `nav`/`close`；spec §1.3 要求：缺失时由 loader 写
  `quality_flags=missing_nav`，不得用 fund_daily 收盘价代替。
- Python src-layout：`pyproject.toml` + `pythonpath=src`，所有 import 使用 `flow_dashboard.*`
  （plan 原写的 `src.flow_dashboard.*` 是 bug，已修正）。

## 4. 实测分布（用于人工 freeze 阈值）

- **source_switch_reconcile (1% 容差)**：587 行中 89 行 (15.2%) over_tolerance、
  495 行 ok、2 行 only_fund_share、1 行 only_etf。15% 不一致主要分布在 2026 上半年早期日历日，
  可能反映 etf_share_size 与 fund_share 对早期 ETF 的口径差异。
- **coverage_baseline (ownership=huijin)**：universe=4（510050/510300/510500/159915），
  count_coverage=0.75（3/4，因 159915 未在 huijin 标签下），prior_share_coverage=1.0、
  prior_aum_coverage=1.0（3 只覆盖到的 ETF 已覆盖全部份额/AUM）。

## 5. 待人工决策（来自 spec §5 needs_human_review）

下列项 Phase A 已采集证据，但数值阈值仍需人工冻结后才能进入 Phase B：

- `data_contract.sina_realtime_provider` — 访问条款合规性需人工确认。
- `data_contract.pit_sw_l1_history` — 申万 L1 个股历史成分源尚未确认；
  Phase C 行业两融面板不进入 Phase B。
- `logic_pipeline[s3_margin].parameters.reconciliation_tolerance` — 已有
  source_switch_reconcile.csv 的 `diff_pct` 分布（15% 行超 1%），需决定是否分层容忍。
- `logic_pipeline[s3_margin].parameters.market_scope` — 已实测 SSE/SZSE/BSE 三所
  都返回；是否合并"全市场"待冻结。
- `logic_pipeline[s4_basis].parameters.contract_selector` — 当季合约定义待冻结
  （季月代码 / 切换日 / 缺失候选顺序）。
- `logic_pipeline[s4_basis].parameters.max_quote_skew_seconds` — 需 Phase B
  盘中实测报价延迟分布。
- `logic_pipeline[s2_flow_aggregation].parameters.coverage_gates` — 已有
  coverage_baseline.csv 分布；count_coverage 实测多在 0.75，prior_aum 多在 1.0，
  需 freeze 双门槛。
- `data_contract.etf_universes` — Phase A seed 含汇金宽基（3 只）+ 创业板 (1 只)；
  港股、科技、周期、行业主题等分类需人工补齐 + 公告来源。
- `data_contract.etf_share_source_switch` — 15% over_tolerance 比例较高，
  建议人工逐 ETF 决定独立换源日，而非全局切换。

## 6. Phase B 启动条件

Phase B 实施计划可在以下条件成立后启动：

1. 人工确认 §5 中的 sina_realtime_provider 合规性。
2. 人工冻结 coverage_gates 与 reconciliation_tolerance 双阈值。
3. 人工冻结 contract_selector 规则（IC/IM 当季合约定义）。
4. 人工补充 etf_pit_labels.csv 的至少一组非汇金宽基分类（例如科技/TMT、周期、
   港股中的一类）。

不冻结 §5 中的项不影响：项目骨架、provider 契约、PIT 表结构、原子发布工具
（Phase B 早期任务可在 needs_human_review 关闭前先做）。

## 7. 已知风险

- etf_pit_labels.csv 的 seed 是从公开基金合同信息手工填的，未与原公告逐字校对。
  Phase B 实施前必须人工复核至少汇金标签的生效日（2015-07 期间多个时点）。
- 新浪 VIP PHP API 是非公开声明接口；响应结构变化由 sina_providers 的契约测试
  捕获，但人工 review 时仍需确认内部使用合规。
- Tushare token 与主项目共用同一个值（虽然环境变量名已解耦）；token 余额计费仍
  在主账户，需注意 Phase B 高频拉取时的成本。
- 实测 15% 的 etf_share_size vs fund_share 不一致率较高，Phase B 若用 fund_share
  补早期历史，需要 source_switch_break 质量标记逐行可见。

## 8. 测试与代码状态

- 全部 Phase A 测试通过：tushare client (2) + schema (4) + 8 providers (9)
  + sina client (3) + sina providers (3) + pit labels (3) + api_capabilities (3)
  + poll_etf_share (3) + source_switch_reconcile (3) + coverage_baseline (3)
  = 36 个测试，全绿。
- Task 16 suffix-invariant 测试单独提交，作为 Red Line 1 守护。
