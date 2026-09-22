"""theme tabs：结构、默认首个激活、legacy 路径不受影响。"""

import re

from flow_dashboard.render.theme import build_html_skeleton


def _skeleton(**kw):
    return build_html_skeleton(
        title="t",
        body="<p>legacy</p>",
        data_date="2026-09-18",
        last_success_at="2026-09-18 19:00",
        **kw,
    )


def test_legacy_skeleton_has_no_tabs():
    html = _skeleton(nav_sections=[("section-etf", "01 ETF")])
    assert "tab-bar" not in html
    assert "<p>legacy</p>" in html
    assert 'class="section-nav"' in html  # 旧导航条仍在


def test_tabs_structure_and_default_active():
    html = _skeleton(
        tabs=[
            {
                "id": "ashare",
                "name": "A股资金流",
                "body": "<div>A股内容</div>",
                "nav_sections": [("section-etf", "01 ETF")],
            },
            {
                "id": "hk-short",
                "name": "港股沽空",
                "body": "<div>港股内容</div>",
                "nav_sections": [("section-hk-conclusion", "HK 结论")],
            },
        ]
    )
    assert 'class="tab-bar"' in html
    assert 'data-tab="ashare"' in html and 'data-tab="hk-short"' in html
    assert 'id="tab-ashare"' in html and 'id="tab-hk-short"' in html
    # 服务端默认激活第一个 tab（无 JS 也可看）
    assert 'id="tab-ashare" class="tab-panel active"' in html
    assert 'id="tab-hk-short" class="tab-panel"' in html
    # 每个 tab 内有自己的 section-nav
    assert html.count('class="section-nav"') == 2
    assert "A股内容" in html and "港股内容" in html
    # legacy body 不进 tab 模式
    assert "<p>legacy</p>" not in html
    # JS：hash 记忆 + Plotly resize
    assert "Plotly.Plots.resize" in html
    assert "hashchange" in html


def test_tab_js_keeps_current_tab_on_non_tab_hash():
    html = _skeleton(
        tabs=[
            {
                "id": "ashare",
                "name": "A股资金流",
                "body": "<div>A股内容</div>",
                "nav_sections": [("section-etf", "01 ETF")],
            },
            {
                "id": "hk-short",
                "name": "港股沽空",
                "body": "<div>港股内容</div>",
                "nav_sections": [("section-hk-conclusion", "HK 结论")],
            },
        ]
    )
    # JS 无法在单测中执行，对 _tabFromHash 函数体做文本契约钉死：
    # hash 不匹配 #tab-（如点击 section-nav 锚点 #section-*）时不得切换 tab，
    # 否则用户在港股 tab 点锚点会被强行切回 A股 tab。
    m = re.search(r"function _tabFromHash\(\)\{(.*?)\}", html, flags=re.DOTALL)
    assert m, "_tabFromHash 函数缺失"
    body = m.group(1)
    guard = re.search(r"if\s*\(!m\)\s*return\s*;", body)
    assert guard, "缺少 if (!m) return; 守卫"
    assert "_showTab(" not in body[: guard.start()], "守卫之前不得调用 _showTab"


def test_tabs_html_escaping():
    html = _skeleton(
        tabs=[
            {"id": "a<x", "name": "A&股", "body": "<div>b</div>"},
            {"id": "b", "name": "B", "body": "<div>c</div>"},
        ]
    )
    # 内嵌的 plotly 压缩 bundle 恰含 "a<x" 子串（如 qa<xn.length()），
    # 负向断言先剔除 <script> 块，只校验本模块生成的标记。
    markup = re.sub(r"<script>.*?</script>", "", html, flags=re.DOTALL)
    assert "A&amp;股" in markup and "a<x" not in markup  # name/id 转义
    assert "a&lt;x" in markup  # id 转义后进入 data-tab/id/href
