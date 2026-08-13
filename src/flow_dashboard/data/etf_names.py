# src/flow_dashboard/data/etf_names.py
"""ETF 代码 → 中文名 映射（用于面板 legend / hover）。

仅覆盖 pit_labels.csv 中现役标的。新增 ETF 时同步加这里。
"""
from __future__ import annotations

ETF_NAMES: dict[str, str] = {
    # —— 宽基（4 只代表） ——
    "510050.SH": "50ETF",
    "510300.SH": "300ETF",
    "510500.SH": "500ETF",
    "159915.SZ": "创业板ETF",
    # —— 科技/TMT（3 只规模最大） ——
    "512480.SH": "半导体ETF",
    "159995.SZ": "芯片ETF",
    "515000.SH": "科技ETF",
    # —— 行业（8 只代表） ——
    "512660.SH": "军工ETF",
    "512800.SH": "银行ETF",
    "512000.SH": "券商ETF",
    "515170.SH": "食品饮料ETF",
    "512010.SH": "医药ETF",
    "515030.SH": "新能源车ETF",
    "512400.SH": "有色金属ETF",
    "512200.SH": "房地产ETF",
    # —— 周期（2 只代表） ——
    "515220.SH": "钢铁ETF",
    "515210.SH": "煤炭ETF",
}


def etf_display_name(ts_code: str) -> str:
    """ts_code → 中文名；未登记的回退到 ts_code 本身。"""
    return ETF_NAMES.get(ts_code, ts_code)
