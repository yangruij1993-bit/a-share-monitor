"""项目级配置：环境变量、路径、时区。

token 解耦：spec §3.2.1 要求 ASHARE_FLOW_TUSHARE_TOKEN 独立，不复用主项目 TUSHARE_TOKEN。
若仅检测到 TUSHARE_TOKEN，抛出明确的 SetupError，提示用户复制一份到新变量名。
"""
from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data" / "flow_dashboard"
CACHE_DIR = DATA_DIR / "cache"
EVIDENCE_DIR = DATA_DIR / "phase_a_evidence"
LOG_DIR = PROJECT_ROOT / "logs" / "flow_dashboard"

TIMEZONE = "Asia/Shanghai"


class SetupError(RuntimeError):
    """环境未就绪，提示用户手动配置。"""


def get_tushare_token() -> str:
    """读取 ASHARE_FLOW_TUSHARE_TOKEN；不存在时抛 SetupError。"""
    token = os.environ.get("ASHARE_FLOW_TUSHARE_TOKEN")
    if not token:
        if os.environ.get("TUSHARE_TOKEN"):
            raise SetupError(
                "检测到 TUSHARE_TOKEN 但未检测到 ASHARE_FLOW_TUSHARE_TOKEN。\n"
                "请运行: export ASHARE_FLOW_TUSHARE_TOKEN=\"$TUSHARE_TOKEN\""
            )
        raise SetupError(
            "未设置 ASHARE_FLOW_TUSHARE_TOKEN 环境变量。"
        )
    return token


OUTPUT_DIR = PROJECT_ROOT / "output" / "ashare_flow_daily"
MANIFEST_DIR = OUTPUT_DIR / "manifest"
STAGING_DIR = OUTPUT_DIR / "staging"
INTRADAY_OUTPUT = OUTPUT_DIR / "intraday_latest.html"
RUNNERS_LOCK = OUTPUT_DIR / "runners.lock"


def ensure_output_dirs() -> None:
    """幂等创建 Phase B 输出目录。"""
    for d in (OUTPUT_DIR, MANIFEST_DIR, STAGING_DIR):
        d.mkdir(parents=True, exist_ok=True)


def ensure_dirs() -> None:
    """幂等创建项目所需目录。"""
    for d in (DATA_DIR, CACHE_DIR, EVIDENCE_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)
    ensure_output_dirs()
    HK_SHORT_CACHE_DIR.mkdir(parents=True, exist_ok=True)


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
    return f"116.{hk_code.split('.')[0]}"


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
