# A 股流动性与 ETF 资金流日度跟踪仪表板—设计文档

## 0. 元信息

| 字段 | 内容 |
|---|---|
| Spec ID | `2026-08-12-ashare-flow-daily` |
| 产品名 | A 股流动性与 ETF 资金流日度跟踪仪表板 |
| 类型 | 自主研发类（数据产品，不是交易策略） |
| spec 版本 | v1.4（可执行性复审修订） |
| 撰写日期 | 2026-08-12 |
| 作者 | 量化研发 |
| 项目根目录 | `/Users/xinghuazhang/ygr-project/a股监控/`（独立于 `行业轮动/` 主项目） |
| 设计文档 | `A股监控/2026-08-12-ashare-flow-daily-design.md` |
| 参考原型 | <https://ashare-flow-weekly.pplx.app/> |
| 目标用户 | 内部自用 |
| 正式输出 | 每个数据交易日一份可版本化的静态自包含 HTML，另提供 `latest.html` |

### v1.4 更新摘要（相对 v1.3）

- ETF 分类由单一 `pit_category` 改为多维 PIT 标签表，允许汇金/宽基/科技/周期/港股等标签重叠，并要求证据与生效区间。
- 删除将静态 ETF→行业字典误作个股申万 PIT 映射的复制计划；个股行业历史映射成为 Phase C 独立数据 Gate。
- 新浪盘中快照使用独立的 `fetch_snapshot`/`load_snapshots` 契约，并与日终归档物理隔离为 `intraday_latest.html`。
- 基差公式明确为“贴水率”：正值表示贴水、负值表示升水；日终同时保存收盘口径与结算口径，主页主展示收盘口径。
- ETF 数据覆盖同时按数量、前一有效日份额和前一有效日 AUM 衡量；累计 Gate 不再只看标的数量。
- 明确 Phase B 的 15 个可见面板/页面组件，消除“ETF 份额”范围歧义。
- 复用代码改为逐函数白名单迁移，不整体复制带 Oracle、静态名单或策略分类的旧模块。
- 补充两融证券类型过滤与未映射桶、公募月末日期对齐、`etf_share_size` 显式字段请求和单位对账。

### v1.3 更新摘要（相对 v1.2）

- 数据源由“Tushare 单源”修订为分层双源：**Tushare 是日终正式层，新浪行情是盘中预览层**。新浪数据不得覆盖或重述日终正式数据。
- 盘中 IC/IM 基差仍按每 15 分钟刷新；Phase A 必须冻结新浪现货/期货代码、返回字段、时间戳语义、请求约束和同步报价容差。
- 将 s7 从误写的“ETF 年内收益分布”修正为“主动权益公募存续基金年内收益分布”。
- 删除不存在的 `行业轮动/src/factor_mining/csi500_timing_core.py` 复制依赖；本项目新建最小化指数行情 provider。
- 明确原版页面只作为信息架构与视觉参考；核心结论和 KPI 使用可追溯的确定性规则生成，不继承原版人工投资判断。
- 增加原版到新版的板块映射，明确 27 图是通过数据 Gate 后的最大目标信息架构，不是 Phase B 的一次性交付承诺。

### v1.2 更新摘要（相对 v1.1）

- 项目整体从 `行业轮动/` 迁出到独立的 `A股监控/` 目录，与主项目解耦；该版本原计划从 `行业轮动/src/data/etf.py`、`poll_tushare_etf_share_size.py`、`csi500_timing_core.py`、`mapping.py` 复制到本项目 `src/data/` 下，其中失效路径和目标目录已由 v1.3 修正。
- 盘中刷新频率决策为 **每 15 分钟**；该版本曾将主数据源定为 Tushare 单源，已由 v1.3 的“日终 Tushare + 盘中新浪”分层方案替代。
- 删除板块新增 **IC 期限结构实时信号面板**（不跟踪择约信号，仅做基差展示）。
- 板块删除清单同步：客户结算资金、私募备案/情绪、海外中国基金、2020-21 主动基金加权净值、ETF 持有人结构、IC 信号面板，共 6 项。

### 0.1 范围与非目标

本项目的主体是数据获取、口径规整、日度可视化和数据健康监控。日度页是主产品，周度页只是由同一日频底表派生的聚合视图。本项目不下单、不产生仓位或策略净值，也不声称所展示指标具有 alpha。

首版不包含：

- 自动交易、仓位管理或风控指令；
- 未经可得性验证的 Wind/iFinD 预期分红数据；
- 无可验证原始字段支持的“产业资本完成减持额”或“主动公募净申赎”伪精确指标；
- 将盘后份额更新包装成“盘中 ETF 净流入”。
- 任何 IC/IM 择约标签、仓位建议或其他交易信号（IC 期限结构实时信号面板已确认不开发，仅保留基差展示）。

### 0.2 原型页面删除板块清单（共 6 项）

原型页面 `ashare-flow-weekly.pplx.app` 中的下列板块在首版中**不开发**，理由是无法落到本项目可用数据源或与项目目标不符：

1. **客户结算资金占比** — 中登公司已停止公开披露该明细，无可得数据源。
2. **私募备案/情绪指标** — 私募备案数据披露粒度与频率不满足日度跟踪需求。
3. **海外中国基金净流入** — 缺少稳定的 API 数据源，人工拼接风险大。
4. **2020-21 主动基金加权净值** — 历史样本固定，不构成持续跟踪价值。
5. **ETF 持有人结构（季度披露）** — 频率与日度跟踪不匹配，按用户决策删除（月度代理指标保留）。
6. **IC 期限结构实时信号面板** — 这不是原版页面中的独立可见图表，而是曾讨论的扩展功能；用户决策不嵌入择约策略信号，仅保留 IC/IM 基差作为市场观察数值。

## 1. 数据契约（Data Contract）

### 1.1 数据对象与主键

| 对象 | 主数据源 | 原始频率 | 主键 | 最少字段 | 用途 |
|---|---|---:|---|---|---|
| ETF 基本信息 | Tushare `fund_basic` | 不定期 | `ts_code` | 代码、名称、成立/上市/到期日、管理人、基金类型 | PIT 标的池与分类 |
| ETF 份额规模 | Tushare `etf_share_size`；`fund_share` 仅历史补充 | 日度/源端实际入库频率 | `ts_code, trade_date` | `total_share`（万份）、`total_size`（万元）、`nav`（元） | ETF 份额变化与同源净值 |
| ETF 净值 | Tushare `fund_nav`（补充/对账） | 日度 | `ts_code, nav_date, ann_date` | `ann_date`, `unit_nav`, `accum_nav`, `adj_nav` | 历史净值补充、复权候选与对账 |
| ETF 二级市场行情 | Tushare `fund_daily` | 日度 | `ts_code, trade_date` | OHLC、成交量/额 | 图表对照与数据质量检查 |
| 融资融券汇总 | Tushare `margin` | 日度 | `exchange_id, trade_date` | `rzye`, `rzmre`, `rzche`（元） | 市场杠杆资金 |
| 个股两融 | Tushare `margin_detail` | 日度 | `ts_code, trade_date` | `rzye`, `rzmre`, `rzche`（元） | 行业聚合 |
| 申万一级 PIT 映射 | Phase C 待验证的申万历史成分源 | 事件/快照 | `stock_code, effective_from` | 股票代码、行业、生效起止日、证据来源、首次确认时间 | 个股两融按行业聚合；当前静态 ETF 映射不可替代 |
| 股指期货合约（日终正式） | Tushare `fut_basic`, `fut_daily` | 日度 | `ts_code, trade_date` | 上市/到期日、OHLC、结算价、量、仓 | IC/IM 日终基差与合约元数据 |
| 现货指数（日终正式） | Tushare 指数日线 | 日度 | `ts_code, trade_date` | 收盘价 | 日终基差分母与右轴 |
| 股指期货报价（盘中预览） | 新浪行情 | 盘中快照 | `provider_code, quote_time` | 最新价、报价时间、昨结算/昨收（若提供）、交易状态 | IC/IM 盘中基差；仅 `intraday_preview` |
| 现货指数报价（盘中预览） | 新浪行情 | 盘中快照 | `provider_code, quote_time` | 最新点位、报价时间、交易状态 | 盘中基差分母；仅 `intraday_preview` |
| 股指期权 | Tushare `opt_basic`, `opt_daily` | 日度 | `ts_code, trade_date` | 看涨看跌、行权价、到期日、收盘/结算价、量、仓 | IV 曲线（数据验证后开启） |
| 无风险利率 | 中债到期收益率曲线/已有 provider | 日度 | `trade_date, tenor` | 年化收益率、复利口径 | IV |
| 公募基金基本信息/份额/净值 | Tushare `fund_basic`, `fund_share`, `fund_nav` | 源端披露频率 | 基本信息 `ts_code`；份额 `ts_code, trade_date`；净值 `ts_code, nav_date, ann_date` | 基金类型、成立日、份额、净值 | 公募观察板块（代理口径） |
| 减持事件 | Tushare `stk_holdertrade` 候选，`anns_d` 原公告对账 | 事件 | `ts_code, ann_date, holder_name, in_de, change_vol` | 公告日、方向、变动量、均价、起止日 | 受限功能；需验证是否能识别“已完成” |

ETF 标的池不使用“当前存续 ETF 倒填历史”。每只 ETF 仅从其当时已成立且已上市时起进入相应分类；退市/清盘后保留历史记录。汇金持有类别是人工审核的时点化标签，不把当前持仓名单倒填到公开披露日之前。

`fund_basic` 的当前快照只能确定成立/上市/到期边界，不能单独证明历史分类或汇金持有状态。历史分类必须来自带生效区间的独立表；无历史证据时从首次人工确认日起生效。

ETF 分类使用多维 PIT 标签表，而不是每只 ETF 每日只有一个 `pit_category`：

| 字段 | 含义 |
|---|---|
| `ts_code` | ETF 代码 |
| `dimension` | 标签维度，例如 `ownership`, `asset_scope`, `benchmark`, `strategy`, `theme` |
| `label` | 标签值，例如 `huijin`, `broad`, `csi300`, `technology`, `cyclical`, `hong_kong` |
| `effective_from`, `effective_to` | 左闭右开生效区间；`effective_to` 可为空 |
| `evidence_source` | 公告、基金资料、指数说明或人工审核记录的来源 |
| `confirmed_at` | 本系统首次确认该标签的带时区时间戳 |

同一 ETF 可在不同维度或同一非互斥维度拥有多个标签。`asset_scope` 和 `benchmark` 等互斥性由标签 schema 显式声明；`ownership`、`theme` 等允许与其他维度重叠。所有聚合必须指定 `dimension + label`，不得依赖隐式优先级把多标签压成单一类别。

### 1.2 频率、时间窗口与暖机

- 历史起点：各板块使用“源数据最早可用日 ~ 本次运行的 `as_of`”；不为凑齐统一起点而回填不可见数据。
- 图表展示窗口：日度默认 3 年，周度默认 3 年，月度默认 5 年；只影响渲染，不截断底层历史。
- warm-up：首发指标不需估计暖机。如未来增加滚动标准化、分位数或预测指标，必须在新 spec 中单独定义 warm-up，不得借用图表展示窗口。
- 周频聚合：余额/存量取当周最后一个有效交易日，流量/发生额对当周有效日求和；不用自然日 `DateOffset` 推演交易日。

### 1.3 数据可见性、缺失与单位

每个落盘表必须保留 `source_date`, `first_observed_at`, `available_at`, `fetched_at`, `source`, `source_version`, `is_stale` 和 `quality_flags`。

- `first_observed_at` 是本系统首次实际观测到该版数据的时间，由轮询日志生成，不能用名义数据日或 API 官方更新说明代填。
- `available_at` 优先使用源端可验证的发布时间；源端不提供时，使用 `first_observed_at` 作为保守上界。历史回补数据没有当时轮询证据时，`available_at` 设为本次回补获取时间并标注 `availability_observed=false`/`reconstructed_history`，不得用于声称历史当时可见。
- 归档报告的 `as_of` 过滤基于 `available_at <= run_at`，不基于名义数据日。重建的长历史图可使用回补数据，但必须标注“事后重建，非历史 vintage”，与真实归档快照分开。

- `etf_share_size` 官方当前说明为交易所于 T+1 约 08:30 更新 T 日数据，海外 ETF 可更晚；不得再按 T 日 19:00 设计。项目轮询曾观察到 T 日 21:00 仍不完整、T+1 09:30 才完整，与次日更新口径一致；仪表板仍以实际 `first_observed_at` 为准。
- `etf_share_size` 请求必须显式指定并校验 `trade_date,ts_code,etf_name,total_share,total_size,nav,close,exchange`；`nav`/`close` 缺失时写入质量标记。按原始单位验证 `total_size ≈ total_share × nav`，容差由 Phase A 冻结；不得因非默认字段未请求而静默生成全空估值。
- `etf_share_size` 为主源，`fund_share` 仅能补主源最早覆盖日之前的历史。两源重叠期先对齐单位并逐 ETF 对账；换源边界两侧数值不一致时，边界日流量输出 NaN 和 `source_switch_break`，禁止计入日/周/累计流量。
- `etf_share_size.nav` 作为主份额同源估值字段；`fund_nav.unit_nav` 只作历史补充或对账。使用 `fund_nav` 时必须保留 `ann_date`，其 `available_at` 不得早于公告时间。
- 份额差只有在前后两个 `source_date` 是相邻项目交易日时才可标为日度估算流量。中间缺日时只输出带 `period_start/period_end` 的多日区间变化，对缺失日及恢复日的日流量均设 NaN，不把多日变化全记到恢复披露日。
- 份额统一转成“份”再计算，金额统一存“元”，图表展示时再转“亿元”。原始单位同时写入 schema metadata。
- 日频金融数据仅对标的自身缺失日在其有效生命周期内 `ffill`；`bfill` 只能用于标识为源端延迟、且不会跨越上市/退市边界的非信号展示字段。不得对份额变化、事件金额或价格收益盲目 `bfill`。
- 个股两融与申万行业的连接使用 `effective_from <= trade_date < effective_to` 的 PIT 区间连接（开放区间视为尚未失效），不用当前行业分类倒填。
- 个股两融行业聚合前必须按证券主数据筛出 A 股普通股票；ETF/基金、债券及其他非普通股票进入 `excluded_non_equity`，普通股票但无有效 PIT 行业的进入 `unmapped_equity`。两类桶必须保留金额和数量，不得在对账中静默丢弃。
- `margin`/`margin_detail` 使用官方字段 `rzye`/融资余额、`rzmre`/融资买入额、`rzche`/融资偿还额，单位为元。主市场汇总是否包含 BSE 在 Phase A 冻结；未冻结前必须分交易所展示，不将不同范围拼成单一“全市场”数值。
- 上游回溯修订不就地改写已归档日报所用快照。重算时生成新版本，标注 `restated=true`，并保留板块级差异。
- 派生指标的 `available_at` 等于所有必需输入行版本 `available_at` 的最大值；任一输入在 `run_at` 后才可见，该派生值就不得进入当次报告。

### 1.4 实时层与日终层

- 日终正式数据：ETF 份额/净值、两融、现货收盘价、期货结算价等按各自实际 `available_at` 入库，是历史图的正式源。
- 盘中观察：新浪行情只负责同步报价的 IC/IM 基差，必须使用独立字段 `data_mode=intraday_preview`、`provider=sina`，不覆盖日终正式列。期权 IV 是否接入盘中层须另行冻结数据源，不默认由新浪提供。
- 盘中快照必须原样保存 `provider_code`、原始报价时间、系统接收时间和解析版本。若新浪响应不含可验证的源端报价时间，则该快照不得用于同步基差计算，只能标记 `quote_time_unverified`。
- 同一观察时点的现货与期货必须来自新浪行情，禁止将新浪盘中期货与 Tushare 日线现货混算。任一报价缺失、非交易状态或时差超限时，基差输出 NaN 并显示 stale/unsynchronized。
- 日终报告以 Tushare 现货收盘价与期货结算价重新计算正式基差；盘中快照作为独立审计记录保留，不“转正”为日终值。
- ETF 份额板块只展示“最新可得份额流量估值”，不生成盘中份额流量。
- 任何面板均不产生 `trade_signal` 或 `portfolio_weights`。

## 2. 指标逻辑（唯一公式源）

### 2.1 公式 pipeline

```yaml
- step_id: s1_etf_flow
  inputs: [share_count_t, share_count_prev, source_date_t, source_date_prev, trading_calendar, nav_t]
  formula: |
    is_consecutive = trading_day_position(source_date_t) - trading_day_position(source_date_prev) == 1
    delta_share_t = share_count_t - share_count_prev if is_consecutive else NaN
    etf_estimated_flow_cny_t = delta_share_t * nav_t
  output: {name: etf_estimated_flow_cny, shape: series}
  executable_explanation: |
    share_count_t 是数据层已由原始“万份”乘 10000 统一成“份”的份额；share_count_prev
    是同一 ETF 上一个实际披露观测。仅当两个数据日是相邻交易日时生成日流量。
    nav_t 优先使用与 share_count_t 同行同日的 etf_share_size.nav；历史补充才使用同日
    fund_nav.unit_nav，且必须满足其 ann_date/available_at 时点约束。缺失则该日流量为 NaN，
    不用二级市场收盘价代替。
    implementation guard: 数据层万份→份转换测试只执行一次；按 ts_code 向量化 groupby.shift(1)；
    用交易日 position 判断相邻；单位断言后再聚合。
  parameters: {share_count_unit: share, storage_unit: CNY, display_unit_divisor: 100000000}

- step_id: s2_flow_aggregation
  inputs: [etf_estimated_flow_cny, pit_labels, eligible_universe, prior_share, prior_aum, trade_calendar]
  formula: |
    members[d,c,t] = {i | pit_label[i,dimension=d,label=c] is effective at t}
    daily_flow[d,c,t] = sum_{i in members[d,c,t]}(etf_estimated_flow_cny[i,t], min_count=1)
    count_coverage[d,c,t] = observed_count[d,c,t] / eligible_count[d,c,t]
    prior_share_coverage[d,c,t] = sum(prior_share[i] for observed i) / sum(prior_share[i] for eligible i)
    prior_aum_coverage[d,c,t] = sum(prior_aum[i] for observed i) / sum(prior_aum[i] for eligible i)
    weekly_flow[d,c,w] = sum_{t in trading_week(w)} daily_flow[d,c,t], min_count=1
    cumulative_flow_ytd[d,c,t] = sum_{u=first_trading_day(year(t))}^{t} daily_flow[d,c,u]
      only if every required day meets the frozen coverage gate, else NaN
    cumulative_flow_3y[d,c,t] = sum_{u=first_trading_day_on_or_after(t-3 calendar years)}^{t} daily_flow[d,c,u]
      only if every required day meets the frozen coverage gate, else NaN
  output: {name: aggregated_etf_flow, shape: matrix}
  executable_explanation: |
    每个面板显式指定 dimension + label，只聚合当日已上市且对应标签已生效的 ETF；同一 ETF
    可以合法进入不同维度的多个面板，但同一 dimension + label 内只能计入一次。周频流量是周内
    日流量求和，不是只取周末观测。prior_share/prior_aum 使用当前日之前最近一个满足相邻交易日
    与数据可见性要求的正式观测；分母为零或不可得时对应加权覆盖率为 NaN。
    implementation guard: pandas groupby.sum 必须显式使用 min_count=1；输出
    eligible_count/observed_count/count_coverage/prior_share_coverage/prior_aum_coverage。覆盖不足时不得
    输出 0 或继续累加。累计 Gate 必须同时检查数量覆盖和前一有效日 AUM 加权覆盖；份额覆盖用于诊断。
  parameters: {count_coverage_gate: null, prior_aum_coverage_gate: null,
    cumulative_windows: [calendar_ytd, trailing_3_calendar_years]}

- step_id: s3_margin
  inputs: [margin_balance, margin_buy, margin_repay, security_master, pit_sw_l1]
  formula: |
    market_balance_t = sum_exchange(margin_balance[exchange,t])
    market_weekly_change_w = market_balance[last(w)] - market_balance[last(w-1)]
    industry_financing_net_flow[j,t] = sum_i(
      (margin_buy[i,t] - margin_repay[i,t]) * 1{security_type[i,t]=A_share_equity and industry[i,t]=j}
    )
    industry_weekly_financing_net_flow[j,w] = sum_{t in trading_week(w)} industry_financing_net_flow[j,t]
  output: {name: margin_panels, shape: matrix}
  executable_explanation: |
    交易所汇总先去重；个股对行业映射用当日可见 PIT 分类。`rzmre-rzche` 统一称“融资净流量”，
    不称“股票净买入”。对账恒等式为：行业合计 + unmapped_equity + excluded_non_equity ≈
    可比范围 margin_detail 合计；三部分均输出金额和记录数。
    implementation guard: 证券类型与 PIT 行业过滤前后均保留对账表，差异必须在容差内。
  parameters: {reconciliation_tolerance: null, market_scope: null}

- step_id: s4_basis
  inputs: [spot_price, futures_price, expiry_date, observation_date, quote_time_spot, quote_time_futures, contract_metadata]
  formula: |
    days_to_expiry = (expiry_date - observation_date).days
    discount_rate = (spot_price - futures_price) / spot_price
    annualized_discount_rate = discount_rate * 365 / days_to_expiry
    basis_points = futures_price - spot_price
  output: {name: futures_basis, shape: series}
  executable_explanation: |
    discount_rate > 0 表示期货贴水，discount_rate < 0 表示期货升水；`basis_points` 保留传统
    “期货-现货”点数符号。日终同时计算 `eod_close`（现货收盘价 + 期货收盘价）和
    `eod_settlement`（现货收盘价 + 期货结算价），主页主展示 `eod_close`，结算口径作为对照并
    明示非同步结算口径；盘中预览使用同一时戳附近的最新价。盘中与日终偏离率只比较临近收盘的
    盘中快照和 `eod_close`，不与 `eod_settlement` 比较。days_to_expiry <= 0 或 spot_price <= 0
    输出 NaN。implementation guard: 分母用 mask，不用 maximum(eps)。
  parameters: {calendar_annualizer: 365, contract_selector: null,
    roll_rule: null, max_quote_skew_seconds: null, dividend_adjustment: false}

- step_id: s5_option_iv
  inputs: [option_price, underlying_price, strike, maturity, risk_free_rate, dividend_yield, option_type]
  formula: null
  output: {name: option_iv, shape: series}
  executable_explanation: |
    期权标的和模型（Black-Scholes spot + q 或 Black-76 futures）尚未确认；首版代码禁止猜测。
    在 needs_human_review 关闭前该板块显示“未启用”。
  parameters: {solver: null, tolerance: null, max_iterations: null}

- step_id: s6_mutual_fund_proxies
  inputs: [fund_basic, fund_share, fund_nav]
  formula: |
    new_fund_count[m] = count(fund where found_date in m and category is equity_eligible)
    month_end_anchor[m] = last_project_trading_day(m)
    aligned_share_date[f,m] = latest visible share date <= month_end_anchor[m]
    aligned_nav_date[f,m] = latest visible nav date <= month_end_anchor[m]
    active_equity_aum_proxy[f,m] = disclosed_share[f,aligned_share_date] * unit_nav[f,aligned_nav_date]
      only if both lags and the share-nav date gap meet their frozen limits, else NaN
    active_equity_aum_change_proxy[m] = sum_f(
      aum_proxy[f,m] - aum_proxy[f,m-1]
    ) over the intersection of funds observed at both endpoints
  output: {name: mutual_fund_proxies, shape: matrix}
  executable_explanation: |
    只称“成立数量”和“存量变化代理”；没有募集份额/净申赎披露时不称“新发规模”或“净申赎”。
    份额和净值都必须经过 available_at <= run_at 过滤。月末锚定日之后披露的数据不得回填当期；
    份额滞后、净值滞后或两者日期差超过冻结阈值时不计算该基金当期 AUM。AUM 变化只对前后
    两端均满足新鲜度并有观测的共同基金求和，新成立/终止基金单独报告，不与存续基金变化混合。
    implementation guard: 类别映射、两端覆盖率、份额/净值日期分布、超期数量和进出池数量必须同图展示。
  parameters: {equity_category_mapping: null, max_share_lag_days: null,
    max_nav_lag_days: null, max_share_nav_gap_days: null}

- step_id: s7_active_fund_ytd_return_distribution
  inputs: [adjusted_nav, first_valid_nav_date_of_year, pit_active_equity_category, fund_lifecycle]
  formula: |
    ytd_return[f,t] = adjusted_nav[f,t] / adjusted_nav[f,first_valid_nav_date_in_year] - 1
    distribution[c,t] = cross_section(
      ytd_return[f,t] where pit_active_equity_category[f,t] = c and fund_is_active[f,t]
    )
  output: {name: active_fund_ytd_return_distribution, shape: matrix}
  executable_explanation: |
    年初已成立基金以年内首个有效复权净值日为起点；年内新成立基金以成立后的首个有效
    复权净值日为起点，但单独标为 new_fund，不与完整 YTD 样本混合解读。仅展示截至 t
    仍存续且主动权益分类在 t 已生效的基金；不得使用当前分类倒填历史。
    implementation guard: 复权净值与分红处理方式必须由 Phase A 验证；存续完整样本和年内
    新成立样本分开输出，并展示样本数、净值覆盖率和最新净值日期分布。
  parameters: {adjustment_method: null}

- step_id: s8_holdings_reduction
  inputs: [event_amount_cny, event_available_at, event_status, trading_week]
  formula: |
    weekly_completed_reduction_cny[w] = sum(
      event_amount_cny where event_status = completed
      and event_available_at in trading_week(w), min_count=1
    )
  output: {name: weekly_completed_reduction_cny, shape: series}
  executable_explanation: |
    只能使用含公告日、完成状态、方向和数量/金额的可验证事件源。`stk_holdertrade`
    只作候选：若它无法可靠区分“完成”与“进行中/计划”，必须与 `anns_d` 原公告对账或禁用。
    implementation guard: event_source 未冻结前整个板块隐藏，不用股东户数或定期持股快照推导。
  parameters: {event_source: null, amount_fallback_rule: null}
```

### 2.2 受控的派生指标

- 主动权益公募存续基金年内收益分布按 s7 计算，仅做横截面描述；图上必须写明复权方式，并分开显示年初存续样本与年内新成立样本。
- 减持板块在事件源通过验证前不计算。`stk_holder_number` 是股东户数，`top10_floatholders` 是定期持股快照，二者不能直接推导公告完成减持金额。
- 正式基差首版不剥离预期分红，图标明“未调分红”。只有当 PIT 成分、公告日可见性、预计每股分红和折现模型均通过审计后，才增加调分红对照列。

### 2.3 Look-ahead 边界（Red Line 1）

本项目不产生交易信号，因此“估计日 / 执行日 / 持有收益日”不适用。历史页面的可见性边界为：

```text
source_date <= report_data_cutoff
available_at <= report_run_at
report_publication_time > report_run_at
```

向输入末尾追加未来数据，不得改变已归档日报的任一历史值，除非明确生成新的重述版本。交易日推进使用项目交易日索引，不用 `DateOffset` 或 `Timedelta` 猜测下一交易日。盘中预览必须标注报价时间和 `intraday_preview`，不回填为日终正式值。

## 3. 执行计划（Execution Plan）

### 3.1 运行入口与调度

| 入口 | 计划 | 职责 | 交易日保护 |
|---|---|---|---|
| `intraday` | **已决策：每 15 分钟，新浪行情** | IC/IM 盘中基差预览 | runner 检查交易日、早午盘、交易状态、报价时戳和现期同步性；launchd 只负责唤起 |
| `eod_preview` | T 日 19:00 后 | 拉取已可得日频数据，生成 T 日 partial 预发布 | ETF 份额未入库时明示 partial，不将 T-1 标成 T |
| `daily_finalize` | T+1 交易日 09:30 后 | 重拉 ETF 份额等次日源，定稿 T 日报告 | 根据实际 `first_observed_at` 判断完整性；未齐仍保留 partial |
| `monthly` | 每月第一个交易日 09:00 后 | 公募代理指标与分类表 | 数据未披露则保留上期并显示原始 source_date |

不设 ETF 份额盘中任务。盘中频率已决策为每 15 分钟，IC/IM 盘中报价使用新浪行情；Tushare 只承担日终正式数据。Phase A 需冻结新浪的代码映射、请求批量、频率、超时、响应结构、时间戳语义和失败退避策略。期权 IV 在 s5 未决项关闭并另行确定盘中数据源后，才决定是否加入该入口。

### 3.2 模块与产物

```text
src/flow_dashboard/
├── data/                 # Tushare 日终 provider、新浪盘中 provider、schema、PIT 可见性与增量缓存
├── indicators/           # ETF flow、margin、basis、fund proxies
├── render/               # Plotly figures + HTML assembly
└── pipeline.py           # intraday / eod_preview / daily_finalize / monthly
scripts/flow_dashboard/       # 四个入口脚本（含 monthly）
scripts/launchd/              # launchd plist
tests/flow_dashboard/         # 契约、口径、时点、对账、渲染测试
data/flow_dashboard/          # 可复用增量 parquet + manifest
output/ashare_flow_daily/     # report_<data_date>_vNN.html + latest.html
                               # intraday_latest.html 为盘中独立入口，不指向日终归档
docs/资金流跟踪/              # README/运维说明；若后续有研发结论，单独写策略研发报告
```

### 3.2.1 与 `行业轮动/` 主项目的解耦关系

本项目物理位置独立于 `行业轮动/` 主项目，不复用其 Python 包路径。旧项目代码只允许按下列白名单逐函数迁移（非软链、非跨项目 import、非整文件复制），每个迁移函数必须先移除 Oracle、静态标的池、策略分类、旧缓存路径和其他主项目依赖，再补契约测试：

| 来源（行业轮动/） | 目标（A股监控/） | 用途 |
|---|---|---|
| `src/data/etf.py` 中经审计的 Tushare 请求/规范化函数 | `src/flow_dashboard/data/etf.py` | `fund_basic`、`fund_nav`、`fund_daily`、`fund_share`、`etf_share_size` 包装；不迁移 Oracle 和静态名单 |
| `scripts/poll_tushare_etf_share_size.py` 中的轮询日志函数 | `scripts/flow_dashboard/poll_etf_share_size.py` | `etf_share_size` 可得性采样；不迁移策略白名单和旧输出路径 |

`src/flow_dashboard/data/index_provider.py` 在本项目内按最小契约新建，负责 Tushare 日终指数行情；不从带有交易信号逻辑的 `csi500_timing_core.py` 复制或裁剪。`src/flow_dashboard/data/sina_realtime.py` 同样在本项目内新建，只负责新浪行情响应获取、原始字段留存和规范化，不包含基差计算。

`src/flow_dashboard/data/industry_mapping.py` 在 Phase C 内新建。`行业轮动/src/data/mapping.py` 是静态 ETF→申万指数展示字典，不是个股 PIT 行业映射，不得复制为本项目的行业历史源。Phase C Gate 必须先验证能否取得带历史生效区间的申万个股成分；若只能取得当前快照，行业历史面板保持未启用。

复制后必须改造的内容：

1. **去掉对 `行业轮动/src/` 的 sys.path 注入**，改用本项目相对 import。
2. **数据库/缓存路径**指向本项目 `data/flow_dashboard/`，不与主项目共用。
3. **Tushare token** 独立环境变量 `ASHARE_FLOW_TUSHARE_TOKEN`，不复用主项目变量。
4. 复制代码只保留通用数据访问能力，不引入主项目的策略、信号或仓位逻辑。

日频/低频数据加载器的公共契约为 `load(start, end, as_of, universe=None, use_cache=True)`，其中 `as_of` 是带 Asia/Shanghai 时区的完整时间戳，等于本文的 `report_run_at`，不是只含日期的截止日。返回值必须经 schema 校验，并在 loader 内执行 `available_at <= as_of`；不允许不同源在同列混用单位。

新浪实时 provider 使用独立契约：

```python
fetch_snapshot(provider_codes, observed_at) -> QuoteBatch
load_snapshots(start_at, end_at, as_of, provider_codes=None) -> DataFrame
```

`fetch_snapshot` 只返回本次网络响应解析出的新快照，不得用缓存伪装本次报价；网络失败即返回显式失败状态。`load_snapshots` 才允许读取历史快照，并仍执行 `available_at <= as_of`。`start_at/end_at/observed_at/as_of` 均为带 Asia/Shanghai 时区的完整时间戳。

`report_<data_date>_vNN.html` 中的 `data_date` 是本期主报告交易日 T，不是 T+1 定稿运行日。每个板块仍另显示自己的 `latest_source_date` 和 `available_at`；低频板块不会因文件名为 T 而伪装成 T 日数据。

### 3.3 发布与并发安全

- 每次运行先在同目录 staging 文件生成完整 HTML，通过完整性检查后原子 `replace` 成归档文件。
- `latest.html` 使用相对目标的临时 symlink 后原子替换；不在用户可读文件上就地覆写。
- `intraday` 只原子更新 `intraday_latest.html`，不得创建或改写 `report_<data_date>_vNN.html` 和 `latest.html`。`latest.html` 仅指向最近一次成功的 `eod_preview` 或 `daily_finalize` 归档版本。
- 四个 runner 共用文件锁；无法获锁时记录 `skipped_due_to_lock`，不并发改 manifest。
- Plotly JS 在单份 HTML 中只内嵌一次。每张图包含数据日期、最近成功获取时间、单位和覆盖率。正式文件不得引用 CDN 或其他网络资源，断网打开时图表和交互仍完整可用。
- 同一报告日的补跑生成新版本，不覆盖旧版；每版保存输入数据文件的 path/size/mtime/content hash、源版本、`run_at`、参数和板块状态 manifest。

### 3.4 交易映射、成本与输出

- `position_sizing`: 无。本仪表板不产生 `portfolio_weights`。
- 正式 HTML 不含任何择约 label、`official_trade_signal` 或仓位建议；盘中基差只是市场观察数值。
- 交易费用：展示层不计算收益，因此无扣费对象。如未来将某项指标开发为回测/交易信号，必须单独建自主策略研发 spec，并设置非零佣金和滑点；不在本数据产品 spec 中猜测交易参数。

### 3.5 分期与验收门

1. **Phase A—数据可得性 Gate**：用真实账户对 Tushare API 拉取小样本，并对新浪公开行情响应做交易时段小样本采集；冻结字段、单位、代码映射、时间戳语义、频率、权限/访问约束、限流与 `available_at`。Gate 未过的板块不进入实现。Phase A 必须落盘 `api_capabilities.yaml`、ETF 分类生效区间表、源切换对账报告、覆盖率基线和可得性轮询记录，作为 Phase B 输入。
2. **Phase B—可发布 MVP**：交付下列 15 个可见面板/页面组件，以及原子发布和数据健康能力；不在 `contract_selector/roll_rule` 确认前拼接或命名“当季连续基差”。
   1. 日度 ETF：汇金宽基（1）、科技/TMT 对照（1）、全市场合计/宽基/行业主题/分类累计（4）、周期日度/累计（2）、单只 ETF TOP15（1），共 9 个。港股 ETF 合计/分类/TOP10 属于 Phase C，不计入 Phase B。
   2. 周度 ETF：宽基、行业主题、分类累计、月度合计，共 4 个。
   3. 两融：分交易所融资余额与周变化，共 1 个；行业板块和热力留到 Phase C。
   4. 衍生品：IC、IM 逐合约分段基差合并为 1 个“期货基差”组件，内含两个子图；盘中新浪预览与日终 Tushare 正式值分层展示。
   5. 数据健康：独立页面/区域，不计入上述 15 个图表组件，但属于 Phase B 必交付。
3. **Phase C—扩展板块**：个股两融行业热力、公募代理指标、港股 ETF 分类。
4. **Phase D—受限板块**：期权 IV、预期分红调整基差、减持事件；仅在各自 `needs_human_review` 关闭后实现。

共通验收标准：

- 公式单测与单位测试全部通过；边界包含缺失、重复、零/负分母、上市/退市日。
- 后缀不变测试通过：向输入末尾追加任意未来数据，已归档日报的历史值必须逐元素不变，除非明示生成重述版本。
- ETF 聚合前后金额差为零（浮点容差内）；两融明细与市场汇总差异可解释且在预设阈值内。
- 任意单一上游失败时，HTML 仍可打开且对应板块显示 stale；不把旧数据标成今日数据。
- 重复执行同一 `as_of` 产物内容稳定；中途失败不破坏上一份 `latest.html`。
- 性能预算由 Phase A 基准测试后冻结；未冻结前不把“日终 < 5 分钟/盘中 < 30 秒”作为已证实验收门槛。运行超过冻结预算时保留上一版并告警。

### 3.6 摘要与结论层

- 新版保留原版页面的 KPI 卡片和“本期摘要”位置，但内容只能由当前归档版本中的结构化指标按确定性规则生成；首版不调用生成式模型撰写投资判断。
- 每条摘要必须保存 `rule_id`、引用的指标键、数据日期和输入版本；页面数值与摘要引用值必须通过一致性测试。
- 摘要只描述可验证事实，例如“较前一周增加”“覆盖率下降”或“最新数据仍为 T-1”。不得自动生成“护盘”“兑现”“拥挤高点”“接力棒切换”等动机、因果或交易含义判断。
- 任一必需输入为 partial、stale、unsynchronized 或低于覆盖门槛时，对应 KPI/摘要显示数据状态，不生成方向性结论。

## 4. 风险控制（Risk Management）

### 4.1 运行风控

- 每个板块分别记录 freshness，不设一个“全局最新日”掩盖低频源。
- 源端失败最多重试 3 次（指数退避，单次不阻塞超过 60 秒）；其后使用最近成功缓存并标红。
- 数据校验失败与 API 失败分类记录。前者不得用“旧缓存”静默掩盖。
- 日志写入 `logs/flow_dashboard/`，不记录 token、cookie 或完整请求头。

### 4.2 Quant Development Red Lines 对齐

| Red Line | 对齐方式 |
|---|---|
| 1. 绝不使用未来函数 | 虽然不下单，仍以 `available_at <= run_at` 做历史可见性过滤；归档快照不因未来数据回填而静默改写，并通过后缀不变测试。 |
| 2. 处理生存者偏差 | ETF 与行业分类使用 PIT 生效区间，保留清盘/退市历史；缺失填充不跨越生命周期。 |
| 3. 资金管理 | 当前产物不下单、不计算策略收益。未来若进入回测/交易，必须新建 spec 并使用非零佣金与滑点，不在本 spec 中预设交易参数。 |
| 4. 最大回撤统一日度口径 | 当前仪表板不生成净值或 MaxDD。如后续增加业绩板块，只允许基于日度盯市净值计算，禁止用周末/调仓点净值代替。 |

### 4.3 统计指标口径

本项目不报告年化收益、Sharpe、Calmar、胜率或 MaxDD，因为它不是一次策略回测。仪表板也不引入已有 IC 策略的历史业绩注释，避免把市场观察页误读为策略绩效页。

## 5. needs_human_review

以下条目关闭前，对应功能不得进入正式代码或对外标成已完成：

```yaml
- field_path: data_contract.sina_realtime_provider
  reason: 盘中源已决策为新浪行情，日终正式源仍为 Tushare。Phase A 仍需冻结新浪每 15 分钟周期内的代码映射、响应字段与编码、源端时间戳语义、请求批量/频率、超时和失败退避，并确认内部使用符合当时可见的访问条款；这些非正式接口特征可能变化，必须由原始响应样本和契约测试约束。不得通过规避访问控制、验证码或封禁机制获取数据。
  questions:
    - IC/IM 各月份合约及中证500/中证1000现货指数分别使用哪些新浪代码，合约上市和到期时如何维护映射？
    - 响应中的报价时间、交易日期和交易状态如何解析；是否同时支持批量请求现货与期货？
    - 15 分钟窗口内的请求预算、超时和并发数是多少；响应结构变化时如何触发 schema failure？
    - 当前访问条款、robots/接口限制和内部使用边界是否允许该调用方式；若不允许，盘中板块使用哪个合规替代源？

- field_path: data_contract.pit_sw_l1_history
  reason: 当前可复用的 `行业轮动/src/data/mapping.py` 只是静态 ETF→申万指数映射，不是个股历史 PIT 成分。Phase C 在历史生效区间来源验证前不能实现行业两融历史聚合。
  questions:
    - 哪个数据源能提供 `stock_code, sw_l1, effective_from, effective_to` 及可审计证据？
    - 若只能取得当前快照，是否接受 Phase C 只从首次观测日起积累，不回补此前行业历史？

- field_path: logic_pipeline[s3_margin].parameters.reconciliation_tolerance
  reason: 对账容差尚未由实测冻结，且 margin 汇总与 margin_detail 可能存在覆盖口径差异。
  questions:
    - Phase A 样本对账后，应使用多少绝对金额和相对比例双阈值？

- field_path: logic_pipeline[s3_margin].parameters.market_scope
  reason: 市场融资汇总需冻结 SSE/SZSE/BSE 的纳入范围，且汇总表与明细表的可比边界可能不同。
  questions:
    - 主页“市场融资余额”是沪深还是沪深京？历史上 BSE 加入时如何标记口径断点？

- field_path: future_extensions.dividend_adjusted_basis
  reason: 首发口径已冻结为 dividend_adjustment=false；项目尚未确认可用的 PIT 预期分红源，因此只将调分红对照视为后续扩展。
  questions:
    - 后续是否需要调分红对照列？如需要，使用哪个带历史可得时间的预期分红源？

- field_path: logic_pipeline[s4_basis].parameters.contract_selector
  reason: 目标图表使用“当季合约”，但尚未定义季月代码、到期周的切换日、缺失时候选顺序和连续曲线拼接规则。
  questions:
    - IC/IM 当季合约是指最近 3/6/9/12 月合约，还是 CFFEX 当季连续映射？
    - 应在到期日、到期前一交易日还是事前固定天数切到下季？换约日图表是保留断点还是分段展示？

- field_path: logic_pipeline[s4_basis].parameters.max_quote_skew_seconds
  reason: 盘中现货和期货报价不同步会制造虚假基差，但允许时差尚无实测证据。
  questions:
    - Phase A 记录报价延迟分布后，最大允许时差是多少秒？超限时应隐藏数值还是显示 stale？

- field_path: logic_pipeline[s5_option_iv]
  reason: 未冻结期权品种、标的、价格字段、股息率和模型，`cn_gdp` 也不是无风险利率数据。
  questions:
    - 首版要展示哪个指数期权品种，应用 BS spot + q 还是 Black-76 futures？
    - 期权价格用收盘价还是结算价，无风险曲线的具体 provider 和复利口径是什么？

- field_path: logic_pipeline[s6_mutual_fund_proxies].parameters.equity_category_mapping
  reason: “主动权益”类别映射、份额披露频率与新发募集规模字段尚未验证。
  questions:
    - 哪些 Tushare fund_type 纳入主动权益，联接基金、FOF、QDII 和被动指数基金如何排除？
    - 如无可验证募集规模，是否接受首版只展示新成立数量和 AUM 变化代理？

- field_path: logic_pipeline[s2_flow_aggregation].parameters.coverage_gates
  reason: 累计流量在 ETF 覆盖不全时不应继续累加，但可接受的数量覆盖率和前一有效日 AUM 加权覆盖率门槛尚无实测证据。
  questions:
    - Phase A 后日度、周度和累计图的 `count_coverage` 与 `prior_aum_coverage` 门槛分别是多少？低于门槛时是断线还是只标 partial？

- field_path: logic_pipeline[s6_mutual_fund_proxies].parameters.date_alignment
  reason: 月末 AUM 代理已要求份额和净值按月末锚定日向后看禁止、向前找最近可见值，但可接受的份额滞后、净值滞后和两者日期差需要由披露分布冻结。
  questions:
    - Phase A/Phase C 样本统计后，`max_share_lag_days`、`max_nav_lag_days`、`max_share_nav_gap_days` 分别设为多少？

- field_path: logic_pipeline[s7_active_fund_ytd_return_distribution].parameters.adjustment_method
  reason: 主动权益基金年内收益分布需冻结可验证的复权净值序列、分红处理方式和同日多公告版本选择规则。
  questions:
    - 应使用 `fund_nav.adj_nav`，还是由单位净值与分红事件自建总回报序列？同一净值日多条公告按何种 PIT 规则选择？

- field_path: logic_pipeline[s8_holdings_reduction].parameters.event_source
  reason: 原稿所列 `stk_holder_number`/`top10_floatholders` 不能推导公告完成减持金额；官方 `stk_holdertrade` 是候选事件源，但尚需与 `anns_d` 原公告验证它是否可靠识别“已完成”状态和金额。
  questions:
    - Phase A 抽样对账后，`stk_holdertrade` 能否独立支持“公告完成减持额”？若不能，是否接入 `anns_d` 解析，或从正式范围删除该板块？

- field_path: data_contract.etf_universes
  reason: 汇金、宽基、行业/主题、科技、周期和港股 ETF 需要多维、时点化的代码与标签表。
  questions:
    - 首版各 `dimension + label` 的代码、名称、生效日、退出日、证据来源和互斥规则是什么？

- field_path: data_contract.etf_share_source_switch
  reason: "etf_share_size 与 fund_share 的重叠差异分布尚未对账，不能先验冻结自动拼接容差。"
  questions:
    - Phase A 逐 ETF 对账后，是否需要每只 ETF 独立换源日，以及多大差异可判定两源可连续拼接？

- field_path: execution_plan.performance_budget
  reason: 日终和盘中性能门槛尚无当前机器、实际标的池和 API 限流下的基准测试证据。
  questions:
    - Phase A 基准测试后，日终与盘中单次运行预算分别是多少？

- field_path: execution_plan.phase_b.scope
  reason: 完整设想为 27 张图，不宜在数据 Gate 前一次性实现。
  questions:
    - 是否同意先发布 Phase B MVP，再以数据可得性决定 Phase C/D？
```

## 6. 研报复现段

不适用。参考网页只是产品信息架构原型，本项目不声称复现其数据、图形或投资结论。如后续要复现原网页/研报，必须单独新建“研报复现类” spec 和复现报告。

## 7. 自主研发合规

### 7.1 研发动机

核心假设是：ETF 份额变化估算流量、杠杆资金、期货基差、期权定价和公募份额代理指标能从不同角度描述资金状态；把它们放在同一个可审计时点的日度仪表板中，能提高人工研究效率。该假设不等于“这些指标有 alpha”，首版不做预测性声明。

### 7.2 参数管理

- 仪表板参数只包含展示窗口、数据健康阈值和刷新周期，以运维证据选择，不以投资收益优化。
- 两融对账阈值、基差合约选择、期权模型等在实测前为 `null`，不从常识猜值。

### 7.3 稳健性与数据产品验证

本项目不用 IS/Validation/pseudo-OOS 挑选 alpha 参数；稳健性重点是数据和运行可靠性：

- 对每个源保留至少 10 个交易日的可得性轮询记录，统计延迟分布和缺失率。
- 固定历史快照做 golden-file 对账，接口/分类变更后必须显式接受差异。
- 每月审计 ETF 分类覆盖率；每季审计港股 ETF 池和汇金标签的 PIT 生效区间。
- 盘中基差与收盘后正式基差可记录偏离率，但只作报价同步性和预览质量指标。

### 7.4 失败场景与后续改进

- 份额数据延迟或回溯修订：显示真实 `source_date/available_at`，不追求伪实时；保留版本以便追溯。
- 新浪盘中行情不稳定或响应结构变化：保留最近成功快照并标 stale，但不继续据此计算新的基差；不用异步时戳报价混算。日终正式层继续由 Tushare 独立运行。
- 仪表板过大：优先保留数据健康、ETF 流量、两融和 IC/IM 纯基差图；低频/未验证板块延后加载或删除。
- 若用户可能将盘中基差预览当成交易信号：通过颜色、文案、独立字段和不同存储路径四重隔离，并固定显示“市场观察，非交易建议”。

## 附录 A：目标信息架构

完整愿景为 **27 张图**（日度 12 + 周度 15）。**日度 tab 是主页，每个交易日更新；周度 tab 只是由日度底表派生的聚合视图。**这是信息架构，不代表 Phase B 一次性实现全部板块。

### 日度 tab（12 图）

1. 汇金宽基 ETF（1 图）。
2. 科技赛道 ETF 与中证 TMT（1 图）。
3. ETF 日度份额变化估算流量结构（4 图）。
4. 周期主题 ETF（2 图）。
5. 单只 ETF 流量 TOP15（1 图）。
6. 港股 ETF 合计/分类/TOP10（3 图）。

### 周度聚合 tab（15 图）

1. 国家队/杠杆资金（4 图）：汇金宽基 ETF 周度流量、融资余额周变化、板块两融变化、申万一级两融热力。
2. 主动公募代理（3 图）：新成立数量（募集规模待验证）、主动权益 AUM 变化代理、存续基金年内收益分布。
3. ETF 被动资金（4 图）：宽基周度流量、行业/主题周度流量、分类累计流量、月度合计流量。
4. 产业资本（1 图）：减持事件源通过验证后才开启。
5. 期货/期权（3 图）：IC 当季基差、IM 当季基差、期权 IV（待验证）。

## 附录 B：通用避坑清单对照

- [x] 未决常数/公式进入 `needs_human_review`，未直接进代码。
- [x] 以 `available_at <= run_at` 限定历史可见性，交易日推进使用项目交易日索引。
- [x] 首发无估计 warm-up；未来滚动指标必须在新 spec 中单独定义。
- [x] 本项目无中间权重/资产权重映射，无隐式 normalize/clip。
- [x] 基差/IV 分母用 mask 处理，不用 `maximum(eps)` 改变符号。
- [x] 本项目不生成 Sharpe/MaxDD；未来若扩展，需重新按日度收益和日度盯市净值审计。
- [x] 如未来接入回测/交易，佣金和滑点不得默认为零。

## 附录 C：原版页面到新版的板块映射

原版页面的数据与投资结论不作为新版的事实来源；下表只定义产品结构的继承关系。`条件保留`表示仅在对应 Phase Gate 通过后出现，否则页面显示“未启用”或不渲染该板块。

| 原版板块 | 新版状态 | Phase / 口径变化 |
|---|---|---|
| 汇金持有类宽基 ETF 净申购 | 保留 | Phase B；改称“份额变化估算流量”，使用 PIT 汇金标签 |
| 客户结算资金占比 | 删除 | 无稳定可得源 |
| 市场融资余额变化 | 保留 | Phase B；先分交易所，市场范围经 Phase A 冻结后再汇总 |
| 分板块融资余额变化、申万行业热力 | 保留 | Phase C；个股明细按 PIT 行业聚合 |
| 权益公募新发规模 | 改造 | Phase C；无募集规模时只展示新成立数量 |
| 主动权益存量净申赎 | 改造 | Phase C；只称共同样本 AUM 变化代理 |
| 2020–21 主动基金加权净值 | 删除 | 固定历史样本，不持续跟踪 |
| 主动权益产品年内收益分布 | 保留 | Phase C；按 s7 的复权净值和 PIT 主动权益分类计算 |
| 私募备案、私募情绪 | 删除 | 频率/数据源不满足要求 |
| 宽基、行业/主题 ETF 周度/月度/累计流量 | 保留 | Phase B；全部由日度份额变化估算流量聚合 |
| 海外中国基金净流入 | 删除 | 无稳定 API 数据源 |
| 公告完成减持规模 | 条件保留 | Phase D；事件状态和金额经原公告对账后开启 |
| IC/IM 当季基差 | 改造 | Phase B；盘中新浪预览、日终 Tushare 正式；正值为贴水、负值为升水，首版未调分红且逐合约分段 |
| 股指期权 IV | 条件保留 | Phase D；模型、价格字段、利率与行情源冻结后开启 |
| 汇金、科技、日度结构、周期、单只 ETF TOP15 | 保留 | Phase B；统一使用份额变化估算流量，删除原版因果/信号文案 |
| 港股 ETF 合计与分类 | 保留 | Phase C；PIT 分类；新版另增单只产品 TOP10 |
| ETF 持有人结构 | 删除 | 季度频率不匹配 |
| IC 期限结构择约信号 | 删除 | 非原版独立图；不进入本数据产品，只保留纯基差观察 |

附录 A 的 27 图是上述“保留 + 改造 + 条件保留”全部通过 Gate 后的最大目标信息架构。Phase B 的承诺范围仍以 3.5 节为准；条件板块未通过 Gate 不计为 Phase B 缺陷。
