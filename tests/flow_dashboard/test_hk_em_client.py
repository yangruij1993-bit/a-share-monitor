"""em_client：HTML 解析、万/亿金额、翻页发现、未完成K线丢弃。"""
import pandas as pd
import pytest

from flow_dashboard.data.hk_short import em_client

ROW_TMPL = (
    "<tr><td><span>{i}</span></td>"
    '<td><a href="/q/{code}.html">{code}</a></td>'
    '<td><a href="/q/{code}.html">{name}</a></td>'
    "<td><span>315.000</span></td>"          # 最新价（查询时点价，应被丢弃）
    "<td><span>{shares}</span></td>"          # 沽空数量
    "<td><span>313.221</span></td>"           # 沽空平均价
    "<td><span>{amt}</span></td>"             # 沽空金额
    "<td><span>{tov}</span></td>"             # 总成交金额
    "<td><span>{ssr}%</span></td>"
    "<td><span>2026-09-18</span></td></tr>"
)

HTML_2ROWS = (
    '<html><table><tbody>'
    + ROW_TMPL.format(i=1, code="00700", name="腾讯控股",
                      shares="2,033,300", amt="6.37亿", tov="36.94亿", ssr="17.25")
    + ROW_TMPL.format(i=2, code="09881", name="中芯国际",
                      shares="1,090,000", amt="7427.37万", tov="640508607", ssr="11.60")
    + "</tbody></table>"
    '<div class="pagerbox"><a href="sellshort_2.html">2</a>'
    '<a href="sellshort_15.html">15</a></div></html>'
)

HTML_1ROW = (
    '<html><table><tbody>'
    + ROW_TMPL.format(i=1, code="00700", name="腾讯控股",
                      shares="2,033,300", amt="6.37亿", tov="36.94亿", ssr="17.25")
    + "</tbody></table></html>"
)

HTML_PAGER2 = (
    '<html><table><tbody>'
    + ROW_TMPL.format(i=1, code="00700", name="腾讯控股",
                      shares="2,033,300", amt="6.37亿", tov="36.94亿", ssr="17.25")
    + ROW_TMPL.format(i=2, code="09988", name="阿里巴巴-W",
                      shares="1,000,000", amt="1.00亿", tov="10.00亿", ssr="10.00")
    + "</tbody></table>"
    '<div class="pagerbox"><a href="sellshort_2.html">2</a></div></html>'
)


def test_parse_amount_suffixes():
    assert em_client.parse_amount("7427.37万") == pytest.approx(74273700.0)
    assert em_client.parse_amount("1.23亿") == pytest.approx(123000000.0)
    assert em_client.parse_amount("640,508,607") == pytest.approx(640508607.0)
    assert em_client.parse_amount("6.37亿") == pytest.approx(637000000.0)


def test_parse_sellshort_html_drops_query_time_price():
    df = em_client.parse_sellshort_html(HTML_2ROWS)
    assert len(df) == 2
    r = df.iloc[0]
    assert r["code"] == "00700"
    assert r["name"] == "腾讯控股"
    assert r["short_shares"] == 2033300.0
    assert r["short_amount"] == pytest.approx(637000000.0)
    assert r["turnover"] == pytest.approx(3694000000.0)
    assert r["ssr_pct"] == 17.25
    assert r["source_date"] == "2026-09-18"
    assert "last_price" not in df.columns  # 查询时点价必须丢弃（源验证 §1）


def test_max_page_from_pagerbox():
    assert em_client._max_page(HTML_2ROWS) == 15
    assert em_client._max_page("<html>no pager</html>") == 1


def test_fetch_sellshort_day_paginates(monkeypatch):
    calls = []

    def fake_page(page, params):
        calls.append((page, params["sdate"], params["edate"], params["code"]))
        return HTML_PAGER2 if page == 1 else HTML_1ROW

    monkeypatch.setattr(em_client, "_fetch_page_text", fake_page)
    df = em_client.fetch_sellshort_day("2026-09-18")
    assert [c[0] for c in calls] == [1, 2]        # 第 1 页 pagerbox 发现共 2 页
    assert all(c[1] == c[2] == "2026-09-18" and c[3] == "" for c in calls)
    assert (df["trade_date"] == pd.Timestamp("2026-09-18")).all()
    assert len(df) == 3                           # 第 1 页 2 行 + 第 2 页 1 行


def test_fetch_sellshort_stock_range_query(monkeypatch):
    calls = []

    def fake_page(page, params):
        calls.append(params)
        return HTML_1ROW

    monkeypatch.setattr(em_client, "_fetch_page_text", fake_page)
    df = em_client.fetch_sellshort_stock("00700", "2026-05-01", "2026-09-18")
    assert calls[0]["code"] == "00700"
    assert calls[0]["sdate"] == "2026-05-01" and calls[0]["edate"] == "2026-09-18"
    # 区间查询行内自带日期列 → trade_date 取自 source_date
    assert (df["trade_date"] == pd.to_datetime(df["source_date"])).all()


def _kline_json():
    return {"rc": 0, "data": {"code": "100.HSI", "klines": [
        "2026-09-17,1,26450.1,26500.0,26400.0,1000,100000",
        "2026-09-18,1,26500.1,26600.0,26480.0,1200,120000",
    ]}}


def test_fetch_kline_drops_incomplete_today(monkeypatch):
    monkeypatch.setattr(
        em_client.http_client, "fetch_json",
        lambda *a, **k: _kline_json())
    # 抓取时点 15:00（<16:10 HKT）→ 丢掉当日未完成行（源验证 §5）
    df = em_client.fetch_kline(
        "100.HSI", "2026-09-01", "2026-09-18",
        now=pd.Timestamp("2026-09-18 15:00:00", tz="Asia/Shanghai"))
    assert df["trade_date"].max() == pd.Timestamp("2026-09-17")
    # 16:30（收市后）→ 保留当日行
    df2 = em_client.fetch_kline(
        "100.HSI", "2026-09-01", "2026-09-18",
        now=pd.Timestamp("2026-09-18 16:30:00", tz="Asia/Shanghai"))
    assert df2["trade_date"].max() == pd.Timestamp("2026-09-18")


def test_fetch_total_shares_pins_secid_and_validation(monkeypatch):
    captured = {}

    def fake_fetch_json(url, *, params=None, headers=None, **k):
        captured["url"] = url
        captured["params"] = params
        captured["validate"] = k.get("validate")
        return {"data": {"f84": 9095085993}}

    monkeypatch.setattr(em_client.http_client, "fetch_json", fake_fetch_json)
    out = em_client.fetch_total_shares("00700")
    assert out == 9095085993 and isinstance(out, int)
    assert captured["params"]["secid"] == "116.00700"   # 5 位 zfill + 116. 前缀
    assert captured["params"]["fields"] == "f84"
    # validate 必须拒绝东财限流形态 data:null，接受正常载荷
    assert not captured["validate"]({"rc": 0, "data": None})
    assert captured["validate"]({"rc": 0, "data": {"f84": 1}})
