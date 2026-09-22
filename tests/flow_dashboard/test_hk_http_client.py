"""http_client：重试、404 探测、JSON 校验。"""

import json

import pytest

from flow_dashboard.data.hk_short import http_client


class _Resp:
    def __init__(self, status=200, text="", content=b"", headers=None):
        self.status_code = status
        self.text = text
        self.content = content
        self.headers = headers or {}
        self.ok = status < 400


def test_fetch_text_retries_on_empty_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_get(url, params=None, headers=None, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            return _Resp(200, text="")  # 东财限流空响应
        return _Resp(200, text="<html>ok</html>")

    monkeypatch.setattr(http_client.requests, "get", fake_get)
    monkeypatch.setattr(http_client.time, "sleep", lambda s: None)
    out = http_client.fetch_text("http://x", max_retries=3, backoff_base=0)
    assert out == "<html>ok</html>"
    assert calls["n"] == 2


def test_fetch_text_raises_after_max_retries(monkeypatch):
    monkeypatch.setattr(
        http_client.requests, "get", lambda *a, **k: _Resp(500, text="boom")
    )
    monkeypatch.setattr(http_client.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError):
        http_client.fetch_text("http://x", max_retries=2, backoff_base=0)


def test_try_get_returns_none_on_404(monkeypatch):
    monkeypatch.setattr(http_client.requests, "get", lambda *a, **k: _Resp(404))
    assert http_client.try_get("http://x") is None


def test_try_get_returns_response_with_last_modified(monkeypatch):
    r = _Resp(
        200,
        text="a,b",
        content=b"a,b",
        headers={"Last-Modified": "Fri, 18 Sep 2026 07:41:00 GMT"},
    )
    monkeypatch.setattr(http_client.requests, "get", lambda *a, **k: r)
    out = http_client.try_get("http://x")
    assert out is not None
    assert out.headers["Last-Modified"].startswith("Fri")


def test_fetch_json_validates_payload(monkeypatch):
    bad = _Resp(200, text=json.dumps({"rc": 0, "data": None}))
    good = _Resp(200, text=json.dumps({"rc": 0, "data": {"klines": ["x"]}}))
    seq = {"i": 0}

    def fake_get(*a, **k):
        seq["i"] += 1
        return bad if seq["i"] == 1 else good

    monkeypatch.setattr(http_client.requests, "get", fake_get)
    monkeypatch.setattr(http_client.time, "sleep", lambda s: None)
    j = http_client.fetch_json("http://x", validate=lambda j: j.get("data"))
    assert j["data"]["klines"] == ["x"]
