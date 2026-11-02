# A 股流动性与资金流监控

A 股流动性与 ETF 资金流日度跟踪仪表板：自动抓取行情、ETF 份额、融资融券、港股沽空等数据，生成单页 HTML 日报。

## 功能面板

- **资金流总览**：宽基/行业 ETF 资金流（宽基池 73 只、9 只指数聚合），TOP15 横向对比
- **融资融券**：全市场/创业板融资余额长期趋势、两融明细、行业两融
- **港股沽空**：HKEX 沽空 EOD 追踪，18:45 更新缓存
- **健康度与覆盖**：数据源可用性、PIT 标签、来源切换对账

## 安装

要求 Python ≥ 3.13。

```bash
git clone https://github.com/yangruij1993-bit/a-share-monitor.git
cd a-share-monitor

# uv（推荐）
uv venv && source .venv/bin/activate
uv pip install -e .

# 或 pip
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

## 配置 Tushare Token

数据抓取依赖 [Tushare Pro](https://tushare.pro/)，需自备 token：

```bash
cp .env.example .env
# 编辑 .env，填入你的 token
```

或在 shell 中导出：

```bash
export ASHARE_FLOW_TUSHARE_TOKEN="你的token"
```

> 注意：环境变量名必须是 `ASHARE_FLOW_TUSHARE_TOKEN`，只设 `TUSHARE_TOKEN` 会报错提示。

## 日常使用

| 入口 | 用途 |
|---|---|
| `scripts/flow_dashboard/run_intraday.py` | 盘中刷新，产出 `output/ashare_flow_daily/intraday_latest.html` |
| `scripts/flow_dashboard/run_daily_finalize.py` | 生成前一日完整日报（`--retry-if-partial` 补跑缺失数据） |
| `scripts/flow_dashboard/run_eod_preview.py` | EOD 预览 |
| `scripts/flow_dashboard/run_monthly.py` | 月度报告 |
| `scripts/flow_dashboard/run_hk_short_eod.py` | 港股沽空 EOD（18:45，港股休市日自动短路） |
| `scripts/flow_dashboard/poll_etf_share_size.py` | 轮询一次 ETF 份额数据 |

示例：

```bash
python scripts/flow_dashboard/run_daily_finalize.py --data-date 2026-10-30
```

## 定时调度（macOS launchd）

`scripts/launchd/` 提供 launchd plist 与说明，安装方式见 `scripts/launchd/README.md`。

**plist 中的绝对路径绑定到原部署机器**（`/Users/xinghuazhang/ygr-project/a股监控`），在其他机器部署需全局替换该前缀（工作目录、`.venv` 路径、日志路径）。

非交易日由 runner 内部读交易日历自动短路，launchd 每日触发即可。

## 测试

```bash
pip install -e ".[dev]"
pytest
```

需要真实 token 或网络访问的测试标记为 `live`，缺 token 时自动跳过。

## 项目结构

```
src/flow_dashboard/        # 核心包：数据抓取、指标计算、渲染
  data/                    # Tushare/新浪/HKEX 等客户端与加载器
  indicators/              # 资金流、两融、港股沽空指标
  render/                  # Plotly 面板与单页 HTML 组装
scripts/flow_dashboard/    # CLI 入口（launchd 调用）
scripts/launchd/           # macOS 定时任务配置
data/flow_dashboard/       # Phase A 证据文件（提交在库）
output/                    # 运行产出（gitignore）
```
