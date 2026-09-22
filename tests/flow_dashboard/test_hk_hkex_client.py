"""hkex_client：dayquot 段解析（含切块/&amp;/杂散%）、LOS xlsx 解析。"""
import io
import zipfile

import pandas as pd
import pytest

from flow_dashboard.data.hk_short import hkex_client

# 模拟真实坑：段内 <pre><font> 切块、&amp;、行首 %、千分位数字
DAYQUOT_FIXTURE = """<html><body>
<h3>MARKET HIGHLIGHTS</h3>
<h3>SHORT SELLING TURNOVER - DAILY REPORT</h3>
<pre><font size='1'>
   1 CKH HOLDINGS            1,090,000      74,273,675     8,613,270      640,508,607
   2 YOFC &amp; CO            12,500         312,500        90,000        4,500,000
%  3 TOM GROUP LTD           5,000          10,000         3,000         1,500,000
</font></pre><pre><font size='1'>
   4 WH GROUP                8,000          20,000         2,000         1,000,000
</font></pre>
<h3>PREVIOUS DAY'S ADJUSTED SHORT SELLING TURNOVER</h3>
<pre><font size='1'>
   1 CKH HOLDINGS            1,100,000      75,000,000     8,600,000     640,000,000
</font></pre>
</body></html>"""


def test_parse_dayquot_daily_and_adjusted():
    daily, prev = hkex_client.parse_dayquot(
        DAYQUOT_FIXTURE, data_date="2026-09-18",
        prev_date="2026-09-17")
    assert len(daily) == 4
    assert len(prev) == 1  # 段尾无固定边界，靠行正则特异性截住
    r = daily[daily["code"] == "00002"].iloc[0]
    assert r["name"] == "YOFC & CO"          # &amp; 已 unescape
    assert r["short_shares"] == 12500.0
    assert r["short_amount"] == 312500.0
    assert r["turnover"] == 4500000.0
    assert r["trade_date"] == pd.Timestamp("2026-09-18")
    assert daily.iloc[2]["code"] == "00003"  # 行首 % 已清除，行仍解析
    rp = prev.iloc[0]
    assert rp["code"] == "00001"
    assert rp["short_shares"] == 1100000.0  # 修正值
    assert rp["trade_date"] == pd.Timestamp("2026-09-17")


def test_parse_dayquot_missing_section_returns_empty():
    daily, prev = hkex_client.parse_dayquot("<html>nothing</html>",
                                            data_date="2026-09-18",
                                            prev_date="2026-09-17")
    assert daily.empty and prev.empty


def _build_los_xlsx() -> bytes:
    sheet = (
        '<?xml version="1.0"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        "<sheetData>"
        '<x:row r="1"><x:c r="A1"><x:v>List of Securities</x:v></x:c></x:row>'
        '<x:row r="2"><x:c r="A2"><x:v>Updated as at 21/09/2026</x:v></x:c></x:row>'
        '<x:row r="3"><x:c r="A3"><x:v>Stock Code</x:v></x:c>'
        '<x:c r="B3"><x:v>Name</x:v></x:c><x:c r="C3"><x:v>Category</x:v></x:c>'
        '<x:c r="D3"><x:v>Sub-Category</x:v></x:c></x:row>'
        '<x:row r="4"><x:c r="A4" t="str"><x:v>700</x:v></x:c>'
        '<x:c r="B4" t="str"><x:v>TENCENT</x:v></x:c>'
        '<x:c r="C4" t="str"><x:v>Equity</x:v></x:c>'
        '<x:c r="D4" t="str"><x:v>Securities</x:v></x:c></x:row>'
        '<x:row r="5"><x:c r="A5" t="str"><x:v>2800</x:v></x:c>'
        '<x:c r="B5" t="str"><x:v>TRACKER FUND</x:v></x:c>'
        '<x:c r="C5" t="str"><x:v>Exchange Traded Products</x:v></x:c>'
        '<x:c r="D5" t="str"><x:v>ETF</x:v></x:c></x:row>'
        "</sheetData></worksheet>"
    ).encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    return buf.getvalue()


def test_parse_list_of_securities():
    df, eff = hkex_client.parse_list_of_securities(_build_los_xlsx())
    assert eff == "Updated as at 21/09/2026"
    assert len(df) == 2
    r = df[df["code"] == "02800"].iloc[0]
    assert r["category"] == "Exchange Traded Products"
    assert set(hkex_client.etf_set(df)) == {"02800"}
    assert hkex_client.reit_set(df) == set()
