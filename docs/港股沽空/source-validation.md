# 港股沽空监控 数据源验证报告（source spike）

日期：2026-09-21
状态：已冻结（对应设计文档 §5.1 验证门）
验证方式：只读探测 + 2026-09-18 单日对账；所有 URL 均为实测可用。

## 0. 结论摘要

| 数据集 | 主源 | 备源/对账源 | 历史深度 | 结论 |
|---|---|---|---|---|
| 逐证券日频卖空（股票口径） | 东财 sellshort（HTML 分页） | HKEX dayquot | ≥1 年 | 通过，≥80 交易日门槛 ✓ |
| 全口径逐证券卖空（含 ETF/ETP/REIT） | HKEX dayquot 归档 + ashtmain 当日 | 无（独占） | 滚动 ~61 自然日 ≈ 41 交易日 | 通过（用途限定，见 §7 偏差） |
| SFC 周度须申报淡仓 CSV | SFC 官网 CSV（无鉴权） | 无（权威独占） | 至 2012 年 | 通过 |
| 恒指/恒生科技/个股/ETF 日线 | 东财 push2his kline | — | HSI 8970 天 | 通过 |
| 总股本 | 东财 push2 quote f84 | — | 当前值 | 通过 |
| ETF/REIT 证券主表 | HKEX ListOfSecurities.xlsx | — | 每日更新（生效日期在文件内） | 通过 |

对账（§5.1 ≤0.5% 门）：2026-09-18 共同证券 742 只，总额相对差 0.000001%；随机 20 只（seed=20260921）最差 0.089%（小额万位舍入）。**通过**。

关键口径发现：**东财 sellshort 只含股票（主板+GEM，含 RMB 柜台），不含 ETF/ETP/REIT/L&I**；HKEX 官方日报为全口径。两者不是矛盾，是覆盖范围不同。该发现导致市场层指标口径调整，见 §7。

## 1. DS1 逐证券日频卖空（股票口径）— 主源：东财

### URL

- 单日全市场第 1 页：`https://hk.eastmoney.com/sellshort.html?sdate=YYYY-MM-DD&edate=YYYY-MM-DD`
- 第 2..N 页（静态文件，`&page=` 参数无效）：`https://hk.eastmoney.com/sellshort_{N}.html?code=&sdate=YYYY-MM-DD&edate=YYYY-MM-DD`
- 单只股票历史：`https://hk.eastmoney.com/sellshort.html?code=XXXXX&sdate=YYYY-MM-DD&edate=YYYY-MM-DD`（同样 `sellshort_{N}.html` 翻页）
- 页数从页内 `pagerbox` 的分页链接解析；当前单日全市场 15 页 × 50 行

### 响应与字段

服务端渲染 HTML 表格，列：序号｜股票代码(5 位含前导 0)｜股票名称｜最新价｜沽空数量(股)｜沽空平均价｜沽空金额(港元)｜总成交金额(港元)｜沽空占成交比例%｜日期。

- 金额列后缀解析：`7427.37万` → ×1e4；`1.23亿` → ×1e8
- ⚠️ 「最新价」是**查询时点价**，非该历史日期的收盘价。回补历史时价格一律走行情接口（DS5），不得用此列
- 行示例（2026-09-18，00001 长和）：沽空 1,090,000 股 / 74,273,675 港元 / 总成交 640,508,607 / SSR 11.60%

### 历史与限流

- 历史：2025-09-30 → 现在（00700 实测约 1 年），满足 ≥80 交易日
- 限流：push2/hk 系接口存在间歇性空响应（rate limit），实测 sleep 5–8s 后重试成功。loader 必须 retry + 指数退避（≥3 次）
- 需带 `User-Agent`；跟随 https 重定向（`-L`）

### 口径（重要）

股票口径：主板 + GEM 股票，含 RMB 柜台（81810 XIAOMI-WR、80016 SHK PPT-R 等）。**不含 ETF、杠杆反向产品（L&I）、REIT、窝轮/牛熊证**。全市场（当日全部证券）单日约 745 只；3 只 GEM 股（8137/8279/8299）出现在东财但 HKEX 日报未列（合计约 HK$1.3mn，占总额 0.003%，忽略）。

## 2. DS2 全口径逐证券卖空（含 ETF）— 主源：HKEX 官方

### URL

- 归档（每个交易日一个静态文件）：`https://www.hkex.com.hk/eng/stat/smstat/dayquot/d{YYMMDD}e.htm`（如 `d260918e.htm`；`e`=英文版；周六/周日/节假日 404）
- 当日盘后汇总（归档生成前的当日版本）：`https://www.hkex.com.hk/eng/stat/smstat/ssturnover/ncms/ashtmain.htm`（ncms 目录仅保留当日）

### 归档窗口（实测 2026-09-21）

滚动约 **61 个自然日**：d260722e.htm=200，d260717e.htm=404（7 月 20 日为周日）。约 41 个交易日。**超过该窗口的全口径历史不可回补，这是 HKEX 侧硬限制。**

### 响应与解析

单文件 ~26MB HTML。关键段：

1. `MARKET HIGHLIGHTS`：全市场 Sec. Traded / Today's Turnover(HK$/Shares/Deals)（如 2026-09-18 总成交 HK$ 266,512,528,155）
2. `SHORT SELLING TURNOVER - DAILY REPORT`：逐证券 `CODE | NAME | Short(SH) | Short($) | Total(SH) | Total($)` —— 分子分母同文件同口径，843 只证券（2026-09-18），总额 HK$ 45,152,303,516
3. `PREVIOUS DAY'S ADJUSTED SHORT SELLING TURNOVER`：T-1 修正值。**loader 在 T+1 抓取时必须用该段覆盖 T-1 缓存**

解析要点（实测踩坑）：段内文本被 `<pre><font size='1'>` 切成多块；需先 strip 全部 HTML 标签、`html.unescape`（`&amp;` 等）、去掉行首杂散 `%`，再按 `代码 + 名称 + 4 个千分位数字` 正则逐行匹配。股票名称可含 `&`、空格、连字符。

### 当日 2026-09-18 快照（用于 §6.2 阈值合理性）

- 全口径总沽空 HK$ 45.15bn；其中 ETF/ETP（411 只，见 DS6）HK$ 9.695bn = **21.5%**（30% 阈值有区分度）
- 逐证券成交额合计 HK$ 247.57bn（vs 市场总成交 266.51bn——差额为未进入卖空日报的证券成交）
- watch list 2800/3033 均在该报告中

## 3. DS3 主备源对账（2026-09-18）

| 指标 | 值 |
|---|---|
| 共同证券数 | 742 |
| 共同证券沽空总额 东财 vs HKEX | 35,392,651,200 vs 35,392,650,801，相对差 **0.000001%** |
| 随机 20 只（seed=20260921） | 最差相对差 **0.089%**（均为 <HK$1 万小额的万位舍入）；18/20 差异 ≤0.0002% |
| 覆盖差异 | HKEX 独有 101 只（ETF/ETP/L&I/REIT，HK$ 9.76bn）；东财独有 3 只 GEM（HK$1.3mn） |
| 结论 | **≤0.5% 门通过**。差异全部来自口径覆盖而非数值错误 |

**切换条件（冻结）**：东财连续 ≥3 次重试失败，或当日全市场总额与 HKEX 对账相对差 >0.5% 时，当日增量改用 HKEX dayquot/ashtmain 全量解析（股票口径照算，ETF 数据本来就以 HKEX 为源）。切换事件记入质量标记（`source` 列）。

## 4. DS4 SFC 周度须申报淡仓 CSV（权威独占）

### URL 模式（实测）

> **2026-09-22 更新（网站改版）**：下述"路径日期=公布日"的旧地址整体失效（302→HTML /404）。
> 改版后 CSV 路径按**报告期本身**组织（`spr/{position_date}/..._{position_date}.csv`），
> 每期一个确定性 URL，无需按公布日候选探测；`Last-Modified` 仍为公布时刻证据
> （实测 09-11 期 = 09-18 15:43 HKT）。未公布/缺失文件 302 跟随到 200 text/html
> 的 404 页，抓取前必须先验 Content-Type/首行再解析（`sfc_client._looks_like_sfc_csv`）。
> 新地址发现方式：官网汇总页
> `https://www.sfc.hk/en/Regulatory-functions/Market/Short-position-reporting/Aggregated-reportable-short-positions-of-specified-shares`
> 的 CSV 链接（带 `?rev=` 缓存参数，直接 GET 不带 rev 亦可）。

```
https://www.sfc.hk/-/media/EN/pdf/spr/{报告期年}/{报告期月}/{报告期日}/Short_Position_Reporting_Aggregated_Data_{报告期YYYYMMDD}.csv
```

- 路径日期 = 文件名日期 = position_date（周最后一个交易日）；公布时点 = position_date + 7 天的周五（由 Last-Modified 证据确认，勿倒推 available_at）
- 无鉴权，直接 GET；`Last-Modified` 响应头 = 公布时间证据（实测为公布周五 15:00–16:40 HKT）
- 例：`.../spr/2026/09/11/Short_Position_Reporting_Aggregated_Data_20260911.csv`
- 历史：至 2012 年（抽查 2024-01-05 ✓）；公众假日周（如 Boxing Day 2025-12-26）无报告/302

### CSV 格式

```
Date,Stock Code,Stock Name,Aggregated Reportable Short Positions (Shares),Aggregated Reportable Short Positions (HK$)
11/09/2026,1,CKH HOLDINGS,48162045,3315956798
```

- `Date` 为 DD/MM/YYYY；`Stock Code` 无前导零（`1`）；金额为港元
- position_date、页面公布时间 `published_at`（Last-Modified）、首次抓取 `first_observed_at` 三者分开存；`available_at = published_at`，**绝不按报告期 +固定天数倒推**（设计 §5）
- 宽限期（设计 §6.3）：position_date 后第 5 个香港交易日

### 申报门槛与进入/退出语义（SFC 官方 FAQ）

- 一般证券（非 CIS）：周最后一个交易日收盘时，净淡仓 ≥ 0.02% 市值 **或** HK$30mn（取较低者）即须申报
- CIS（含 ETF、REIT）：≥ HK$30mn
- 因此证券进入/退出周报 = 淡仓是否过门槛，**退出不代表回补到零**；市场层指标只能在"连续两期均出现"的可比集合上算（设计 §6.1 已如此规定）

## 5. DS5 行情与指数（东财）

- 日线 K：`https://push2his.eastmoney.com/api/qt/stock/kline/get?secid={S}&fields1=f1,f2,f3&fields2=f51,f52,f53,f54,f55,f56,f57&klt=101&fqt=0&beg=...&end=...`
  - 恒指 `secid=100.HSI`（8970 天）；**恒生科技 `secid=124.HSTECH`**（不是 100.）；港股个股/ETF `secid=116.XXXXX`（02800 盈富基金实测 ✓）
  - fields2：日期,开,收,高,低,成交量(股),成交额
  - ⚠️ 盘中调用会返回**当日未完成 K 线**，loader 必须丢弃未完成行（以 HK 收市 16:10 后成功抓取的行为准）
  - 同样有 rate limit：retry + 退避，带 `User-Agent` 与 `Referer: https://quote.eastmoney.com`
- 总股本：push2 quote 接口 `f84`（00700=9,095,085,993）；代码不确定时用 `https://searchapi.eastmoney.com/api/suggest/get?input=...&type=14` 的 QuoteID 反查

## 6. DS6 ETF/REIT 证券主表（HKEX List of Securities）

- URL：`https://www.hkex.com.hk/eng/services/trading/securities/securitieslists/ListOfSecurities.xlsx`（~1.4MB，无鉴权，**每日更新**；生效日期在 A2 单元格，实测 "Updated as at 21/09/2026"）
- 结构：zip 内 `xl/worksheets/sheet1.xml`，**inline strings**（`t="str"`，sharedStrings 为空，openpyxl 非必需——可用标准库 zipfile+re 解析）；表头在第 3 行：A=Stock Code，B=Name，C=Category，D=Sub-Category
- 分类分布（2026-09-21）：Equity 2815 / Derivative Warrants 7405 / CBBC 5926 / Debt 1320 / **Exchange Traded Products 411**（ETF 382 + L&I 29）/ REIT 11 / 其他
- **冻结规则**：ETF 集合 = `Category == 'Exchange Traded Products'`（411 只，含 L&I）；REIT 集合 = `Category == 'Real Estate Investment Trusts'`。全市场 ETF 沽空额 = Σ(dayquot 当日 ∩ ETF 集合)；watch list ETF（2800/3033）是该集合子集，不重复相加。主表每周抓一次，生效日期随数据留存。

## 7. 与设计文档的偏差（冻结口径，实施须遵守）

设计 §5 表格把"市场总沽空额、主板总成交额（算加权 SSR）"指向 HKEX 官方汇总。验证发现 HKEX 全口径逐证券数据只有 ~41 个交易日滚动窗口，**不满足设计 §5.1 的 80 交易日门槛**。为此冻结以下口径（不改变指标定义与状态机，只改变数据覆盖范围并显式标注）：

1. **市场层指标（市场加权 SSR、日/周沽空强度、前 20 日均值倍数）一律用股票口径**：分子=Σ东财当日沽空金额，分母=Σ东财当日总成交金额（同页两列，天然同口径；历史 ≥1 年，满足 60 日分位）。页面对应位置标注"股票口径，不含 ETF/ETP"
2. **今日全市场沽空额副指标**：主展示用股票口径（同上，可与自身 20 日均值比较）；旁边加注 HKEX 全口径总额与 ETF 占比（当日值）
3. **ETF 干扰证据（§6.3 第 6 步）**：当日 ETF 沽空额占比 = HKEX dayquot（或 ashtmain）当日值 ÷ 同文件总额。只需当日值，无需历史，41 天窗口不受影响
4. **watch list 中 ETF（2800/3033）逐日明细**：东财无 ETF，改从 HKEX dayquot 取（含卖空股数/金额与成交额）；上线初期仅能回补 ~41 天，其 SSR 60 日分位按 §6.1 显示"样本不足"并随每日增量累积，满 60 个观测后自动参与判定
5. **TOP20 榜单为股票口径**（东财当日全市场排序；对冲型 ETF 本不应进个股榜）
6. **全口径市场序列自上线起累积**（每日 dayquot 增量），满 60 个观测后可在市场总览图并行展示全口径 SSR（实现上先留字段，不阻塞首版）

若不接受偏差 1/2，备选方案是市场层全部用 HKEX 全口径并接受上线后 ~3 周"样本不足"，需回到设计文档修改后再实施。

## 8. available_at 取值规则（冻结）

| 数据 | available_at |
|---|---|
| 东财日频（卖空/K线/总股本） | 数据日期 16:10 HKT（HK 收市）。实际发布更晚：**卖空页 2026-09-22 实测 16:37 仍空、16:42 已发布**（~17:00-18:00 常态），18:45 runner 抓取即安全；数据未发布时页面 0 行，客户端须返回空表而非报错 |
| HKEX dayquot 归档 | 数据日期 17:30 HKT（ashtmain 当日版发布时点）；18:45 runner 安全 |
| SFC 周报 | `published_at` = 首次抓取时记录的响应 `Last-Modified`（position_date + 7 天的周五 15:00–16:40 HKT）。无法取得 header 时退化为 `first_observed_at` |

所有数据集通用列（设计 §5）：`source_date`、`available_at`、`first_observed_at`、`fetched_at`、`source`、`source_version` + 质量标记；PIT 过滤恒为 `available_at <= as_of`。

## 9. 未尽事项 / 风险

- HKEX dayquot 26MB/日：全量解析 OK，但增量拉取耗时 ~秒级，需设超时与重试；建议按段定位（锚点字符串）避免全文件正则
- 东财 HTML 结构变更风险：解析器需带冒烟测试（`@live` 标记），失败时走 §3 冻结的切换条件
- HKEX 官网对无 UA 请求可能 403：带 `User-Agent`
- SFC 假日周无报告（如 Boxing Day）：宽限期规则已覆盖，勿当缺失处理
- ListOfSecurities.xlsx 分类包含 "Trading Only" 等边缘 Equity 子类：不参与 ETF 集合，无需特殊处理
