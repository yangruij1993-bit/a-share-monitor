# launchd 调度说明

## 安装
```bash
cp scripts/launchd/com.ygr.ashare-flow.*.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.ygr.ashare-flow.intraday.plist
launchctl load ~/Library/LaunchAgents/com.ygr.ashare-flow.morning-first.plist
launchctl load ~/Library/LaunchAgents/com.ygr.ashare-flow.daily-finalize.plist
launchctl load ~/Library/LaunchAgents/com.ygr.ashare-flow.monthly.plist
launchctl load ~/Library/LaunchAgents/com.ygr.hk-short.eod.plist
```

## 查看运行
```bash
launchctl list | grep ashare-flow
tail -f logs/flow_dashboard/intraday.log
tail -f logs/flow_dashboard/daily_finalize.log
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

## 日报时序

- 18:45 港股任务只更新缓存，不发布整份报表。
- 次日 08:00 生成前一日首版；缺失数据会在 manifest 的 `missing_sources` 中列出，并标记 partial。
- 09:15 仅当 08:00 未生成完整报告时补跑。个股两融明细的近期空结果会重试。
- 19:30 的 `com.ygr.ashare-flow.eod-preview` 不再加载。

## 注意：绝对路径
plist 中 `ProgramArguments` 和日志路径是绝对路径，绑定到当前部署机器
`/Users/xinghuazhang/ygr-project/a股监控/`。在其他机器部署时需要全局替换该前缀。
