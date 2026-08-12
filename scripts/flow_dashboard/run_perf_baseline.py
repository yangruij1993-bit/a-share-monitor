"""性能基线脚本：跑一次 eod_preview + intraday + monthly，记录耗时分布。

per spec §3.5 共通验收：未冻结前不强加 < 5min 阈值；本脚本只落实测分布。

用法：
    python scripts/flow_dashboard/run_perf_baseline.py

输出：
1. stdout 打印 perf_baseline 的 YAML 段。
2. 将同一份 perf dict 追加写入
   ``data/flow_dashboard/phase_a_evidence/api_capabilities.yaml`` 的
   ``perf_baseline_phase_b`` 键（已存在则覆盖该键，其它键保留）。

注意：脚本写入真实 OUTPUT_DIR（非 /tmp）。intraday 输出是幂等的
``intraday_latest.html``，eod_preview 自动递增版本号，monthly 仅刷新分类
快照。这些产物本身就是 Phase B baseline 的证据，故保留。
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd  # noqa: E402
import yaml  # noqa: E402

from flow_dashboard.config import (  # noqa: E402
    EVIDENCE_DIR, OUTPUT_DIR, RUNNERS_LOCK, TIMEZONE,
)
from flow_dashboard.pipeline import (  # noqa: E402
    run_eod_preview, run_intraday, run_monthly,
)


def _time_runner(name: str, fn, perf: dict) -> None:
    """统一计时包装：捕获异常并以 ``<name>_seconds`` / ``<name>_error`` 落盘。"""
    t0 = time.perf_counter()
    try:
        fn()
    except Exception as exc:  # noqa: BLE001 — 任意 runner 错误都视为 baseline 数据
        perf[f"{name}_error"] = f"{type(exc).__name__}: {exc}"
    perf[f"{name}_seconds"] = time.perf_counter() - t0


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    as_of = pd.Timestamp.now(tz=TIMEZONE)
    data_date = as_of.strftime("%Y-%m-%d")

    perf: dict = {
        "as_of": as_of.isoformat(),
        "data_date": data_date,
        "tushare_token_set": bool(__import__("os").environ.get("ASHARE_FLOW_TUSHARE_TOKEN")),
    }

    _time_runner(
        "intraday",
        lambda: run_intraday(
            as_of=as_of, output_dir=OUTPUT_DIR, lock_path=RUNNERS_LOCK,
        ),
        perf,
    )
    _time_runner(
        "eod_preview",
        lambda: run_eod_preview(
            data_date=data_date, as_of=as_of,
            output_dir=OUTPUT_DIR, lock_path=RUNNERS_LOCK,
        ),
        perf,
    )
    _time_runner(
        "monthly",
        lambda: run_monthly(as_of=as_of, output_dir=OUTPUT_DIR),
        perf,
    )

    print("perf_baseline:")
    print(yaml.safe_dump(perf, allow_unicode=True, sort_keys=False))

    # 追加到 api_capabilities.yaml（覆盖 perf_baseline_phase_b 键，保留其它）
    cap_path = EVIDENCE_DIR / "api_capabilities.yaml"
    if cap_path.exists():
        cap = yaml.safe_load(cap_path.read_text(encoding="utf-8")) or {}
        cap["perf_baseline_phase_b"] = perf
        cap_path.write_text(
            yaml.safe_dump(cap, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        print(f"appended perf_baseline_phase_b → {cap_path}")
    else:
        print(f"WARN: {cap_path} not found; perf dict only printed to stdout")


if __name__ == "__main__":
    main()
