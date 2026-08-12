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

## 注意：绝对路径
plist 中 `ProgramArguments` 和日志路径是绝对路径，绑定到当前部署机器
`/Users/xinghuazhang/ygr-project/a股监控/`。在其他机器部署时需要全局替换该前缀。
