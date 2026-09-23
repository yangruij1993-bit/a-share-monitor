#!/usr/bin/env python3
"""SFC 全宇宙总股本回填（天软 cjpy，替代被挡的东财 f84）。

用法（项目 venv python）：
  .venv/bin/python3 scripts/flow_dashboard/backfill_cjpy_shares.py [--refresh]

- 总股本因子来自天软（StockTotalShares3/StockTotalValue3）。cjpy 只装在系统
  Python 3.14（/Library/Frameworks/...），token 在 cjpy 本地配置；本脚本以
  subprocess 调用同文件 `--worker` 模式（3.14 解释器执行）取数。
- RMB 柜台（8xxxx·-R）直查失败时按 '0'+后4位 映射港元柜台借股本；
  GEM 8xxxx（名不带 -R）不做映射，避免错配。
- 幂等：同日重跑经 (code, source_date) merge 覆盖；--refresh 忽略当日已有
  cjpy 行重拉。总市值仅落审计 CSV，缓存只写 total_shares（市值由
  隐含价×股本在指标层推导，见 hk_short_metrics.sfc_market_series）。
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

import pandas as pd

log = logging.getLogger(__name__)

CJPY_PYTHON = "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3"
FACTORS = ["总股本", "总市值"]


def _run_worker(items: list[dict], python_bin: str, batch: int = 50) -> dict:
    """调用 3.14 worker 批量取因子；items=[{sfc,hk}]，返回 {rows,missing}。"""
    with tempfile.TemporaryDirectory() as td:
        codes_path = Path(td) / "codes.json"
        out_path = Path(td) / "out.json"
        codes_path.write_text(json.dumps(items, ensure_ascii=False), encoding="utf-8")
        cmd = [
            python_bin,
            str(Path(__file__).resolve()),
            "--worker",
            str(codes_path),
            str(out_path),
            "--batch",
            str(batch),
        ]
        subprocess.run(cmd, check=True)
        return json.loads(out_path.read_text(encoding="utf-8"))


def _worker(codes_path: str, out_path: str, batch: int) -> int:
    """由 3.14 解释器执行：cjpy 分批取因子，写 JSON。不得 import flow_dashboard。"""
    import time

    import cjpy

    items = json.loads(Path(codes_path).read_text(encoding="utf-8"))
    date = pd.Timestamp.now().strftime("%Y%m%d")
    rows, missing = [], []
    for i in range(0, len(items), batch):
        chunk = items[i : i + batch]
        df = cjpy.get_factor_data(
            code=[c["hk"] for c in chunk], date=date, factors=list(FACTORS)
        )
        got: dict[str, dict] = {}
        if df is not None and len(df):
            for rec in df.to_dict("records"):
                hk = str(rec.get("代码", ""))
                try:
                    shares = float(rec.get("总股本"))
                    mcap = float(rec.get("总市值"))
                except (TypeError, ValueError):
                    continue
                got[hk] = {"name": str(rec.get("名称", "")), "shares": shares, "mcap": mcap}
        for c in chunk:
            hit = got.get(c["hk"])
            if hit and hit["shares"] > 0:
                rows.append(
                    {
                        "sfc": c["sfc"],
                        "hk": c["hk"],
                        "name": hit["name"],
                        "total_shares": hit["shares"],
                        "total_mcap_wan": hit["mcap"],
                    }
                )
            else:
                missing.append(c)
        time.sleep(0.3)
    Path(out_path).write_text(
        json.dumps({"rows": rows, "missing": missing}, ensure_ascii=False),
        encoding="utf-8",
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--python", default=CJPY_PYTHON)
    parser.add_argument("--cache-dir", default=None)
    parser.add_argument("--worker", nargs=2, metavar=("CODES_JSON", "OUT_JSON"))
    parser.add_argument("--batch", type=int, default=50)
    args = parser.parse_args(argv)
    if args.worker:
        return _worker(args.worker[0], args.worker[1], args.batch)

    # 项目内依赖仅装在 venv，worker（3.14 解释器）不得触达
    sys.path.insert(0, str(PROJECT_ROOT / "src"))
    from flow_dashboard.config import HK_SHORT_CACHE_DIR, HK_WATCH_LIST
    from flow_dashboard.data.hk_short.loaders import (
        SFC_FILE,
        SHARES_FILE,
        _annotate,
        _merge,
        _read,
        _write,
    )
    from flow_dashboard.indicators.hk_short_metrics import is_rmb_counter

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    cdir = Path(args.cache_dir) if args.cache_dir else HK_SHORT_CACHE_DIR
    now = pd.Timestamp.now(tz="Asia/Shanghai")
    today = now.tz_localize(None).normalize()

    sfc = _read(cdir / SFC_FILE)
    if sfc.empty:
        log.error("SFC 缓存为空，先跑 backfill_hk_short.py")
        return 1
    latest_pd = sfc["position_date"].max()
    uni = sfc[sfc["position_date"] == latest_pd][["code", "name"]].drop_duplicates(
        "code"
    )
    watch = [{"code": str(c).split(".")[0].zfill(5), "name": n} for n, c in HK_WATCH_LIST]
    uni = pd.concat(
        [uni, pd.DataFrame(watch).drop_duplicates("code")], ignore_index=True
    )

    cached = _read(cdir / SHARES_FILE)
    if not args.refresh and not cached.empty:
        done = set(
            cached.loc[
                (cached["source"] == "cjpy")
                & (pd.to_datetime(cached["source_date"]) == today),
                "code",
            ]
        )
        if done:
            uni = uni[~uni["code"].isin(done)]
    if uni.empty:
        log.info("全部已覆盖，无需拉取")
        return 0

    items = [{"sfc": r.code, "hk": f"HK{r.code}"} for r in uni.itertuples()]
    log.info("直查 %d 只（%s 期宇宙+watch）", len(items), latest_pd.date())
    res = _run_worker(items, args.python, args.batch)
    rows, missing = res["rows"], res["missing"]

    alias_items = [
        {"sfc": m["sfc"], "hk": f"HK0{m['sfc'][1:]}"}
        for m in missing
        if is_rmb_counter(m["sfc"], uni.set_index("code")["name"].get(m["sfc"], ""))
    ]
    if alias_items:
        log.info("RMB 柜台别名回退 %d 只", len(alias_items))
        res2 = _run_worker(alias_items, args.python, args.batch)
        rows += res2["rows"]
        missing = res2["missing"] + [
            m for m in missing if not any(a["sfc"] == m["sfc"] for a in alias_items)
        ]

    if not rows:
        log.warning("未取到任何股本；missing=%d", len(missing))
        return 1
    audit = pd.DataFrame(rows)
    audit.to_csv(cdir / "hk_shares_cjpy_audit.csv", index=False, encoding="utf-8-sig")
    snap = _annotate(
        audit[["sfc", "total_shares"]].rename(columns={"sfc": "code"}),
        source="cjpy",
        version="cjpy_shares_v1",
        available_at=now,
        fetched_at=now,
    )
    snap["source_date"] = today
    merged = _merge(cached, snap, keys=["code", "source_date"])
    _write(merged, cdir / SHARES_FILE)
    log.info(
        "完成：%d 只入库（其中别名 %d），缺 %d 只：%s",
        len(rows),
        len(alias_items) - len(res2.get("missing", alias_items)) if alias_items else 0,
        len(missing),
        ", ".join(m["sfc"] for m in missing[:10]),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
