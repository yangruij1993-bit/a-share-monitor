"""生成 api_capabilities.yaml。

per spec §3.5.1 Phase A: 冻结字段、单位、代码映射、时间戳语义、频率、权限/限流、available_at。

build_capabilities 不需要真实 token：返回的是从代码常量推断的"契约能力声明"。
run_main（CLI）会真实调用每个 provider，把样本行数、样本最新日期、首次观测时间
一起写入 yaml；本模块的 build_capabilities 只产静态部分，便于离线测试。
"""
from __future__ import annotations

from flow_dashboard.data.sina_client import FUTURES_NODE_MARK


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
        "schema_version": "0.1.0a0",
        "tushare": TUSHARE_CAPABILITIES,
        "sina": SINA_CAPABILITIES,
    }
