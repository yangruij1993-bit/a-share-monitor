"""早报是否需要 09:15 补跑。"""
import pandas as pd

from flow_dashboard.pipeline import missing_report_sources


def test_missing_report_sources_checks_every_required_row():
    day = pd.Timestamp("2026-10-13")
    etf = pd.DataFrame({"trade_date": [day, day - pd.Timedelta(days=1)],
                        "ts_code": ["A", "B"]})
    nav = pd.DataFrame({"nav_date": [day, day], "ts_code": ["A", "B"]})
    margin = pd.DataFrame({"trade_date": [day, day],
                           "exchange_id": ["SSE", "SZSE"]})
    detail = pd.DataFrame({"trade_date": [day], "ts_code": ["000001.SZ"]})

    missing = missing_report_sources(
        day, ["A", "B"], etf, nav, margin, detail
    )
    assert missing == ["etf_share:B", "margin:BSE"]


def test_missing_report_sources_checks_nav_and_detail():
    day = pd.Timestamp("2026-10-13")
    etf = pd.DataFrame({"trade_date": [day], "ts_code": ["A"]})
    nav = pd.DataFrame({"nav_date": [day - pd.Timedelta(days=1)], "ts_code": ["A"]})
    margin = pd.DataFrame({"trade_date": [day] * 3,
                           "exchange_id": ["SSE", "SZSE", "BSE"]})
    assert missing_report_sources(day, ["A"], etf, nav, margin, pd.DataFrame()) == [
        "fund_nav:A", "margin_detail"
    ]
