"""带重试的 HTTP 客户端（东财限流 → 指数退避；SFC 候选 URL 404 = 正常探测）。

源验证 §1：东财 push2/hk 系接口间歇性空响应，实测 sleep 5-8s 后重试成功。
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable

import requests

log = logging.getLogger(__name__)


def fetch_text(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    max_retries: int = 3,
    backoff_base: float = 5.0,
    timeout: float = 90.0,
) -> str:
    """GET → 文本。空响应/5xx/网络错误重试，耗尽后抛 RuntimeError。"""
    last: Exception | str = "?"
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(url, params=params, headers=headers, timeout=timeout)
            if r.status_code == 200 and r.text.strip():
                return r.text
            last = f"status={r.status_code} len={len(r.text)}"
        except Exception as e:  # noqa: BLE001 — 网络错误统一重试
            last = e
        if attempt < max_retries:
            wait = backoff_base * (2 ** (attempt - 1))
            log.warning(
                "fetch %s attempt %d failed (%s); backoff %.0fs",
                url[:120],
                attempt,
                last,
                wait,
            )
            time.sleep(wait)
    raise RuntimeError(f"fetch failed after {max_retries} retries: {url} last={last}")


def try_get(
    url: str,
    *,
    headers: dict | None = None,
    max_retries: int = 3,
    backoff_base: float = 2.0,
    timeout: float = 90.0,
) -> requests.Response | None:
    """GET；404 → None（候选 URL 探测语义）；5xx/网络错误重试后抛错。"""
    last: Exception | str = "?"
    for attempt in range(1, max_retries + 1):
        try:
            r = requests.get(url, headers=headers, timeout=timeout)
            if r.status_code == 200:
                return r
            if r.status_code == 404:
                return None
            last = f"status={r.status_code}"
        except Exception as e:  # noqa: BLE001
            last = e
        if attempt < max_retries:
            time.sleep(backoff_base * (2 ** (attempt - 1)))
    raise RuntimeError(f"try_get failed after {max_retries} retries: {url} last={last}")


def fetch_json(
    url: str,
    *,
    params: dict | None = None,
    headers: dict | None = None,
    max_retries: int = 3,
    backoff_base: float = 5.0,
    timeout: float = 90.0,
    validate: Callable[[dict], bool] | None = None,
) -> dict:
    """GET → JSON；validate 返回 False 视为失败并重试（东财 data:null 限流形态）。"""
    last: Exception | str = "?"
    for attempt in range(1, max_retries + 1):
        try:
            text = fetch_text(
                url, params=params, headers=headers, max_retries=1, timeout=timeout
            )
            j = json.loads(text)
            if validate is not None and not validate(j):
                raise ValueError(f"payload validation failed: {text[:120]}")
            return j
        except Exception as e:  # noqa: BLE001
            last = e
        if attempt < max_retries:
            wait = backoff_base * (2 ** (attempt - 1))
            log.warning(
                "fetch_json %s attempt %d failed (%s); backoff %.0fs",
                url[:120],
                attempt,
                last,
                wait,
            )
            time.sleep(wait)
    raise RuntimeError(
        f"fetch_json failed after {max_retries} retries: {url} last={last}"
    )
