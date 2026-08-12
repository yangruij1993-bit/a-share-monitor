"""Phase B pipeline 入口：intraday / eod_preview / daily_finalize / monthly。

实现由后续 task 填充；本 stub 仅声明函数签名。
"""
from __future__ import annotations


def run_intraday(*, as_of, force: bool = False) -> str:
    raise NotImplementedError


def run_eod_preview(*, data_date, as_of, force: bool = False) -> str:
    raise NotImplementedError


def run_daily_finalize(*, data_date, as_of, force: bool = False) -> str:
    raise NotImplementedError


def run_monthly(*, as_of, force: bool = False) -> str:
    raise NotImplementedError
