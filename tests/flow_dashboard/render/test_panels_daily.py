"""10 个日度 ETF 面板测试（行业为父类，科技/周期为子类专项）。"""
from __future__ import annotations

import pandas as pd
import pytest

from flow_dashboard.render.panels_daily import (
    render_huijin_broad_daily,
    render_tech_tmt_daily,
    render_tech_cumulative_daily,
    render_industry_core_cumulative_daily,
    render_total_market_daily,
    render_broad_daily,
    render_industry_theme_daily,
    render_category_cumulative_daily,
    render_cycle_daily,
    render_cycle_cumulative_daily,
    render_top15_etf_daily,
)


def _flow_df(labels: list[str], n_days: int = 5, dimension: str = "asset_scope"):
    rows = []
    base = pd.Timestamp("2026-08-05")
    for label in labels:
        for i in range(n_days):
            rows.append({
                "trade_date": base + pd.Timedelta(days=i),
                "ts_code": f"X{i}.{label}",
                "label": label,
                "etf_estimated_flow_cny": (i + 1) * 1e8 * (1 if label != "tech" else -1),
                "share_in_shares": 100e8,
                "total_size_cny": 100e8 * 3,
                "cumulative_flow_cny": (i + 1) * 1e8,
                "dimension": dimension,
            })
    return pd.DataFrame(rows)


def _bench_df(rows_spec: list[tuple[str, str, list[float]]]) -> pd.DataFrame:
    """benchmark 维度流量行：rows_spec = [(ts_code, 指数label, [每日净流入亿])]。"""
    base = pd.Timestamp("2026-08-05")
    rows = []
    for ts_code, bench, flows in rows_spec:
        for i, v in enumerate(flows):
            rows.append({
                "trade_date": base + pd.Timedelta(days=i),
                "ts_code": ts_code,
                "label": bench,
                "dimension": "benchmark",
                "etf_estimated_flow_cny": v * 1e8,
            })
    return pd.DataFrame(rows)


PANEL_KWARGS = dict(data_date="2026-08-12", coverage=1.0, last_success_at="19:30")


def test_render_huijin_broad_daily_returns_html_fragment():
    """汇金面板按指数聚合：汇金标的的 benchmark 行加总为指数条。"""
    df = _bench_df([
        ("510300.SH", "csi300", [3.0]),
        ("510050.SH", "csi50", [5.0]),
    ])
    df = pd.concat([df, pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-05"), "ts_code": "510300.SH",
         "label": "huijin", "dimension": "ownership", "etf_estimated_flow_cny": 3e8},
        {"trade_date": pd.Timestamp("2026-08-05"), "ts_code": "510050.SH",
         "label": "huijin", "dimension": "ownership", "etf_estimated_flow_cny": 5e8},
    ])], ignore_index=True)
    html = render_huijin_broad_daily(df, **PANEL_KWARGS)
    assert "汇金" in html  # 标题含「汇金」
    assert "Plotly.newPlot" in html
    assert 'id="panel-huijin-broad-daily"' in html


def test_render_total_market_daily_returns_html_fragment():
    df = _flow_df(["broad", "industry", "tech"])
    html = render_total_market_daily(df, **PANEL_KWARGS)
    assert "全市场合计" in html or "合计" in html


def test_render_total_market_daily_dedups_multi_label_rows():
    """同一 ETF 多标签行（explode 产物）只计一次，不得重复加总。"""
    day = pd.Timestamp("2026-08-05")
    rows = []
    for label, dimension in [("huijin", "ownership"), ("broad", "asset_scope"),
                             ("csi300", "benchmark")]:
        rows.append({
            "trade_date": day, "ts_code": "510300.SH", "label": label,
            "dimension": dimension, "etf_estimated_flow_cny": 1e8,
        })
    html = render_total_market_daily(pd.DataFrame(rows), **PANEL_KWARGS)
    # 1e8 元 = 1.0 亿；若重复计数会变成 3.0
    assert '"y":[1.0]' in html
    assert '"y":[3.0]' not in html


def test_render_broad_daily_returns_html_fragment():
    """宽基面板按指数聚合（benchmark 维度），同指数全部 ETF 加总。"""
    df = _bench_df([
        ("510300.SH", "csi300", [1.0, 2.0]),
        ("510310.SH", "csi300", [4.0, 1.0]),
        ("510500.SH", "csi500", [5.0, -2.0]),
    ])
    html = render_broad_daily(df, **PANEL_KWARGS)
    assert "宽基" in html
    assert "Plotly.newPlot" in html
    # csi300 两只两日加总 = 5.0 / 3.0 亿；csi500 独立一条 = 5.0 / -2.0 亿
    assert '"y":[5.0,3.0]' in html
    assert '"y":[5.0,-2.0]' in html
    # 图例是指数显示名（沪深300 = 沪深300），不是 ETF 代码
    assert '"name":"\\u6caa\\u6df1300"' in html
    assert "510300.SH" not in html


def test_render_tech_tmt_daily_returns_html_fragment():
    """科技子类专项面板（含于行业全口径，单独细看）。"""
    df = _flow_df(["tech"])
    html = render_tech_tmt_daily(df, **PANEL_KWARGS)
    assert "科技" in html or "TMT" in html
    assert "Plotly.newPlot" in html


def test_render_tech_cumulative_daily_sums_and_accumulates():
    df = _flow_df(["tech"])
    html = render_tech_cumulative_daily(df, **PANEL_KWARGS)
    assert "科技" in html and "累计" in html
    assert "Plotly.newPlot" in html


def test_render_industry_core_cumulative_daily_one_line_per_etf():
    """传统行业累计对比：每只 ETF 一条折线，不含科技/周期标的。"""
    df = _flow_df(["industry", "tech", "cycle"])
    html = render_industry_core_cumulative_daily(df, **PANEL_KWARGS)
    assert "传统行业" in html and "累计" in html
    assert "Plotly.newPlot" in html
    # tech/cycle 的标的代码不应出现在图例中（_flow_df 的 ts_code 含标签后缀）
    assert "X0.tech" not in html
    assert "X0.cycle" not in html


def test_render_industry_theme_daily_includes_tech_and_cycle():
    """行业=父类全口径：industry / tech / cycle 标的都进入行业面板。"""
    df = _flow_df(["industry", "tech", "cycle"])
    html = render_industry_theme_daily(df, **PANEL_KWARGS)
    assert "行业" in html
    assert "Plotly.newPlot" in html
    assert "13 只" in html  # subtitle 标注全口径数量


def test_render_industry_theme_daily_core_only_still_renders():
    """只有旧 industry 标的时仍正常；三类皆无才 stale。"""
    df = _flow_df(["industry"])
    html = render_industry_theme_daily(df, **PANEL_KWARGS)
    assert "Plotly.newPlot" in html


def test_render_category_cumulative_daily_returns_html_fragment():
    df = _flow_df(["broad", "industry"])
    html = render_category_cumulative_daily(df, **PANEL_KWARGS)
    assert "资产类别" in html or "堆叠" in html


def test_render_category_cumulative_daily_merges_and_dedups():
    """growth→宽基、tech/cycle→行业，每只 ETF 每日只计一次，两段=全市场。"""
    day = pd.Timestamp("2026-08-05")
    rows = [
        # 创业板 ETF 同日挂 growth+broad 两个 asset_scope 标签（同一流量值）
        {"trade_date": day, "ts_code": "159915.SZ", "label": "growth",
         "dimension": "asset_scope", "etf_estimated_flow_cny": 1e8},
        {"trade_date": day, "ts_code": "159915.SZ", "label": "broad",
         "dimension": "asset_scope", "etf_estimated_flow_cny": 1e8},
        # 半导体 ETF（tech）与钢铁 ETF（cycle）都归入行业段
        {"trade_date": day, "ts_code": "512480.SH", "label": "tech",
         "dimension": "asset_scope", "etf_estimated_flow_cny": 2e8},
        {"trade_date": day, "ts_code": "515220.SH", "label": "cycle",
         "dimension": "asset_scope", "etf_estimated_flow_cny": 3e8},
        # 汇金维度应被排除
        {"trade_date": day, "ts_code": "510300.SH", "label": "huijin",
         "dimension": "ownership", "etf_estimated_flow_cny": 5e8},
    ]
    html = render_category_cumulative_daily(pd.DataFrame(rows), **PANEL_KWARGS)
    # 归一后只剩 宽基(1.0) 与 行业(2.0+3.0=5.0) 两个 trace；
    # plotly to_html 会把图例名转义为 \uXXXX（宽基 / 行业）
    assert '"name":"\\u5bbd\\u57fa"' in html
    assert '"name":"\\u884c\\u4e1a"' in html
    assert "growth" not in html
    assert "tech" not in html
    assert "cycle" not in html
    # 创业板只计一次：宽基柱 = 1.0 而非 2.0；行业段为 tech(2.0)+cycle(3.0) 两行
    # （同 x 由 Plotly 堆叠，段高 = 5.0；不会出现汇总前的 huijin 5.0 单值）
    assert '"y":[1.0]' in html
    assert '"y":[2.0,3.0]' in html


def test_render_cycle_daily_returns_html_fragment():
    df = _flow_df(["cycle"])
    html = render_cycle_daily(df, **PANEL_KWARGS)
    assert "周期" in html


def test_render_cycle_cumulative_daily_returns_html_fragment():
    df = _flow_df(["cycle"])
    html = render_cycle_cumulative_daily(df, **PANEL_KWARGS)
    assert "周期" in html
    assert "累计" in html


def test_render_top15_etf_daily_returns_html_fragment():
    df = _flow_df(["broad"] * 20)
    df["ts_code"] = [f"ETF{i:03d}.SH" for i in range(len(df))]
    html = render_top15_etf_daily(df, **PANEL_KWARGS)
    assert "TOP15" in html or "TOP" in html
    # TOP15 应被截断到前 15 只；ETF015（第 16 只）不应出现
    assert "ETF015" not in html


def test_render_top15_etf_daily_dedups_multi_label_rows():
    """多标签 ETF 不得重复上榜（explode 后同日多行只算一次）。"""
    day = pd.Timestamp("2026-08-05")
    rows = []
    # 一只多标签 ETF（3 行）+ 两只单标签 ETF → 榜单最多 3 个不同标的
    for label, dimension in [("huijin", "ownership"), ("broad", "asset_scope"),
                             ("csi50", "benchmark")]:
        rows.append({"trade_date": day, "ts_code": "510050.SH", "label": label,
                     "dimension": dimension, "etf_estimated_flow_cny": 9e8})
    for code in ("512660.SH", "512800.SH"):
        rows.append({"trade_date": day, "ts_code": code, "label": "industry",
                     "dimension": "asset_scope", "etf_estimated_flow_cny": 5e8})
    html = render_top15_etf_daily(pd.DataFrame(rows), **PANEL_KWARGS)
    assert html.count("510050.SH") <= 1  # hover 里最多出现一次


def test_render_top15_places_largest_at_top():
    """横向 TOP15 必须反转 y 轴：最大值画在视觉顶部。

    Plotly 横向 bar 默认第一个分类画在最底部；按 |净流入| 降序排序后
    不反转会让最大值（如周五 300ETF +130 亿）垫底，被误读为"最弱"。
    同时 x 轴必须是线性数值轴：apply_theme 默认 type="category"（为日期
    柱图设计）会把 15 个流量值当成等距类目，条长变成等差阶梯而非按
    数值比例，刻度出现 "130.167210600000003" 式原始浮点串。
    """
    day = pd.Timestamp("2026-08-05")
    rows = []
    for code, v in [("510300.SH", 130.0), ("510050.SH", 37.8), ("512880.SH", -0.3)]:
        rows.append({"trade_date": day, "ts_code": code, "label": "broad",
                     "dimension": "asset_scope", "etf_estimated_flow_cny": v * 1e8})
    html = render_top15_etf_daily(pd.DataFrame(rows), **PANEL_KWARGS)
    assert '"autorange":"reversed"' in html
    assert '"type":"linear"' in html  # x 轴线性，条长 ∝ 数值


def test_render_top15_skips_latest_date_with_only_nan_flow():
    """最新交易日流量全 NaN（份额先到、净值缺失）时回退到最新有效交易日。

    实测场景：10-11 仅 2 只深市 ETF 份额入库且 missing_nav → flow 全 NaN，
    直接按 trade_date.max() 切片会画出 2 根 null 柱（空图）。
    """
    d_valid = pd.Timestamp("2026-08-05")
    d_nan = pd.Timestamp("2026-08-06")
    rows = []
    for i in range(3):
        rows.append({"trade_date": d_valid, "ts_code": f"ETF{i:03d}.SH",
                     "label": "broad", "dimension": "asset_scope",
                     "etf_estimated_flow_cny": (i + 1) * 1e8})
    rows.append({"trade_date": d_nan, "ts_code": "159915.SZ", "label": "growth",
                 "dimension": "asset_scope", "etf_estimated_flow_cny": None})
    html = render_top15_etf_daily(pd.DataFrame(rows), **PANEL_KWARGS)
    # 回退到 08-05：3 根有效柱，而不是 1 根 null
    assert '"x":[null' not in html
    assert html.count("ETF00") >= 1
    # 副标题应标注实际数据日期，避免与报告日期混淆
    assert "08-05" in html


def test_render_handles_empty_df_gracefully():
    """spec §3.5 共通验收：上游失败时面板显式 stale，不渲染空 figure。"""
    empty = pd.DataFrame(columns=["trade_date", "ts_code", "label",
                                   "etf_estimated_flow_cny", "cumulative_flow_cny"])
    html = render_huijin_broad_daily(empty, data_date="2026-08-12",
                                     coverage=None, last_success_at=None)
    assert "stale" in html.lower() or "数据不可得" in html


def test_render_label_filter_yields_empty_sub_shows_stale():
    """df 非空但 label 过滤后无行：面板应 stale，不渲染空 figure。"""
    df = _flow_df(["broad"])  # df 有数据，但没有 huijin 标签
    html = render_huijin_broad_daily(df, **PANEL_KWARGS)
    assert "stale" in html.lower() or "数据不可得" in html
    # 不应该出现空 figure 的 Plotly 调用
    assert "Plotly.newPlot" not in html


def test_render_huijin_broad_daily_excludes_non_huijin():
    """汇金面板按指数聚合：非汇金标的（同指数其他 ETF）不得混入。"""
    df = _bench_df([
        ("510300.SH", "csi300", [3.0]),
        ("159919.SZ", "csi300", [7.0]),   # 同为沪深300但非汇金
        ("510050.SH", "csi50", [5.0]),
        ("512100.SH", "csi1000", [9.0]),  # 非汇金指数
    ])
    df = pd.concat([df, pd.DataFrame([
        {"trade_date": pd.Timestamp("2026-08-05"), "ts_code": "510300.SH",
         "label": "huijin", "dimension": "ownership", "etf_estimated_flow_cny": 3e8},
        {"trade_date": pd.Timestamp("2026-08-05"), "ts_code": "510050.SH",
         "label": "huijin", "dimension": "ownership", "etf_estimated_flow_cny": 5e8},
    ])], ignore_index=True)
    html = render_huijin_broad_daily(df, **PANEL_KWARGS)
    # 汇金标的按指数聚合：沪深300 只含 510300 的 3.0（非 10.0）、上证50 5.0
    assert '"y":[3.0]' in html
    assert '"y":[5.0]' in html
    assert '"y":[10.0]' not in html
    assert '"y":[9.0]' not in html
    # 图例为指数显示名：上证50（上=U+4E0A 证=U+8BC1）
    assert '"name":"\\u4e0a\\u8bc150"' in html
