"""sina_providers 契约测试。

fetch_snapshot:
- 返回 QuoteBatch，含 received_at、observed_at、provider、parse_version
- 每条 quote 含 provider_code、quote_time、last_price、status
- 网络失败时 status='network_error'，quotes 为空列表
load_snapshots:
- 从磁盘读 parquet（不存在返回空 DataFrame）
- 执行 available_at <= as_of 过滤
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from flow_dashboard.data.sina_providers import (
    fetch_snapshot,
    fetch_futures_snapshot,
    load_snapshots,
    QuoteBatch,
)


@pytest.mark.live
def test_fetch_snapshot_spot_indices(tushare_token):
    batch = fetch_snapshot(
        provider_codes=["sh000905", "sh000852"],
        observed_at=pd.Timestamp("2026-08-12 15:00:00", tz="Asia/Shanghai"),
    )
    assert isinstance(batch, QuoteBatch)
    assert batch.provider == "sina"
    assert batch.observed_at.tzinfo is not None
    assert batch.received_at <= pd.Timestamp.now(tz="Asia/Shanghai")
    assert batch.parse_version == "sina_v1"
    assert len(batch.quotes) == 2
    q0 = batch.quotes[0]
    assert "provider_code" in q0
    assert "last_price" in q0
    assert "quote_time" in q0
    assert "status" in q0


@pytest.mark.live
def test_fetch_futures_snapshot_ic(tushare_token):
    batch = fetch_futures_snapshot(
        variety="IC",
        observed_at=pd.Timestamp("2026-08-12 15:00:00", tz="Asia/Shanghai"),
    )
    assert isinstance(batch, QuoteBatch)
    assert batch.provider == "sina"
    assert len(batch.quotes) >= 1
    q0 = batch.quotes[0]
    assert q0["provider_code"].startswith("sina_fut_IC")


def test_load_snapshots_missing_file_returns_empty(tmp_path):
    df = load_snapshots(
        start_at=pd.Timestamp("2026-08-12 09:00", tz="Asia/Shanghai"),
        end_at=pd.Timestamp("2026-08-12 15:00", tz="Asia/Shanghai"),
        as_of=pd.Timestamp("2026-08-12 16:00", tz="Asia/Shanghai"),
        storage_dir=tmp_path,
    )
    assert df.empty
    assert "provider_code" in df.columns
