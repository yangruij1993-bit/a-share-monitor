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


def ensure_dirs() -> None:
    """幂等创建项目所需目录。"""
    for d in (DATA_DIR, CACHE_DIR, EVIDENCE_DIR, LOG_DIR):
        d.mkdir(parents=True, exist_ok=True)
