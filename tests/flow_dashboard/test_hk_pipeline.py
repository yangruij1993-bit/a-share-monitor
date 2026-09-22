"""pipeline 集成港股 tab：tabs 结构、双日期 manifest、report_date 归档名。"""

import json
from pathlib import Path

import pandas as pd

from flow_dashboard.pipeline import _run_eod_preview_inner, run_eod_preview


def _mock_ashare_empty(monkeypatch):
    """A股 loaders 全部空表（复用 test_pipeline_eod_preview.py 的 mock 模式）。"""
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_etf_share_for_pipeline",
        lambda codes, start, end, as_of: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_margin_for_pipeline",
        lambda start, end, as_of: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_fut_daily_for_pipeline",
        lambda ts_code, start, end, as_of: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_index_daily_for_pipeline",
        lambda ts_code, start, end, as_of: pd.DataFrame(),
    )
    monkeypatch.setattr(
        "flow_dashboard.pipeline._load_fund_nav_for_pipeline",
        lambda codes, start, end, as_of: pd.DataFrame(),
    )


def test_eod_preview_renders_both_tabs_and_dual_dates(tmp_path, monkeypatch):
    _mock_ashare_empty(monkeypatch)
    monkeypatch.setattr(
        "flow_dashboard.pipeline._render_hk_tab_for_pipeline",
        lambda as_of: ('<div id="hk-x">港股内容</div>', "2026-09-18"),
    )
    output_dir = tmp_path / "x"
    path = run_eod_preview(
        data_date="2026-08-12",
        as_of=pd.Timestamp("2026-08-12 19:30", tz="Asia/Shanghai"),
        output_dir=output_dir,
        lock_path=output_dir / "runners.lock",
    )
    assert "report_2026-08-12_v01.html" in path.name  # A股触发 → report_date=data_date
    html = path.read_text()
    assert 'class="tab-bar"' in html
    assert 'data-tab="ashare"' in html and 'data-tab="hk-short"' in html
    assert 'id="tab-ashare" class="tab-panel active"' in html  # 服务端默认激活 A股
    assert "港股内容" in html
    assert "市场流动性日报 — 2026-08-12" in html
    manifest = json.loads((output_dir / "manifest" / "2026-08-12_v01.json").read_text())
    assert manifest["panel_status"]["ashare_data_date"] == "2026-08-12"
    assert manifest["panel_status"]["hk_data_date"] == "2026-09-18"
    assert "panel-hk-conclusion" in manifest["panels"]
    assert manifest["source_versions"]["hk_short"] == "hk_short_v1"


def test_report_date_controls_archive_and_title(tmp_path, monkeypatch):
    """港股 runner 触发时 report_date != A股 data_date → 归档名/标题用 report_date。"""
    _mock_ashare_empty(monkeypatch)
    monkeypatch.setattr(
        "flow_dashboard.pipeline._render_hk_tab_for_pipeline",
        lambda as_of: ("<div>hk</div>", None),
    )
    output_dir = tmp_path / "y"
    path = _run_eod_preview_inner(
        "2026-08-12",
        pd.Timestamp("2026-08-13 18:45", tz="Asia/Shanghai"),
        output_dir,
        None,
        report_date="2026-08-13",
    )
    assert "report_2026-08-13_v01.html" in path.name
    html = path.read_text()
    assert "市场流动性日报 — 2026-08-13" in html
    manifest = json.loads((output_dir / "manifest" / "2026-08-13_v01.json").read_text())
    assert manifest["panel_status"]["ashare_data_date"] == "2026-08-12"
    assert manifest["panel_status"]["hk_data_date"] is None


def test_hk_tab_helper_delegates_to_panels(tmp_path, monkeypatch):
    """_render_hk_tab_for_pipeline 只读缓存委托 render_hk_short_body。"""
    from flow_dashboard.pipeline import _render_hk_tab_for_pipeline

    monkeypatch.setattr(
        "flow_dashboard.render.panels_hk_short.render_hk_short_body",
        lambda *, as_of, cache_dir=None: ("<b>HK</b>", "2026-09-18"),
    )
    html, d = _render_hk_tab_for_pipeline(
        pd.Timestamp("2026-09-18 19:00", tz="Asia/Shanghai")
    )
    assert html == "<b>HK</b>" and d == "2026-09-18"


def test_hk_eod_short_circuits_on_non_trading_day(tmp_path, monkeypatch):
    """周六休市且 SFC 无逾期 → 不抓数据不渲染，直接返回 latest.html。"""
    from flow_dashboard import hk_short_pipeline as hp

    monkeypatch.setattr(hp, "_sfc_missing", lambda *, as_of, cache_dir=None: False)

    def boom(*a, **k):
        raise AssertionError("non-trading day must not fetch/render")

    monkeypatch.setattr(hp, "_fetch_hk_increments", boom)
    monkeypatch.setattr("flow_dashboard.pipeline._run_eod_preview_inner", boom)
    out = hp.run_hk_short_eod(
        as_of=pd.Timestamp("2026-09-19 18:45", tz="Asia/Shanghai"),  # 周六
        output_dir=tmp_path,
        lock_path=tmp_path / "runners.lock",
    )
    assert out.name == "latest.html"


def test_hk_eod_fetches_and_publishes_on_trading_day(tmp_path, monkeypatch):
    from flow_dashboard import hk_short_pipeline as hp

    _mock_ashare_empty(monkeypatch)
    monkeypatch.setattr(
        "flow_dashboard.pipeline._render_hk_tab_for_pipeline",
        lambda as_of: ("<div>hk</div>", "2026-09-18"),
    )
    fetched = {}

    def fake_fetch(as_of):
        fetched["called"] = str(pd.Timestamp(as_of).date())

    monkeypatch.setattr(hp, "_fetch_hk_increments", fake_fetch)
    out = hp.run_hk_short_eod(
        as_of=pd.Timestamp("2026-09-18 18:45", tz="Asia/Shanghai"),  # 周五
        output_dir=tmp_path,
        lock_path=tmp_path / "runners.lock",
    )
    assert fetched["called"] == "2026-09-18"
    # report_date = 2026-09-18（触发当日即交易日）
    assert "report_2026-09-18_v01.html" in out.name


def test_hk_eod_skipped_due_to_lock(tmp_path, monkeypatch):
    import fcntl

    from flow_dashboard import hk_short_pipeline as hp

    lock_path = tmp_path / "runners.lock"
    lock_path.touch()
    held = open(lock_path, "w")  # noqa: SIM115 — fd 需跨 run_hk_short_eod 调用保持打开以模拟持锁
    fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # 模拟 A股 runner 持锁
    monkeypatch.setattr(
        hp,
        "_fetch_hk_increments",
        lambda as_of: (_ for _ in ()).throw(AssertionError()),
    )
    out = hp.run_hk_short_eod(
        as_of=pd.Timestamp("2026-09-18 18:45", tz="Asia/Shanghai"),
        output_dir=tmp_path,
        lock_path=lock_path,
    )
    assert out.name == "latest.html"  # 保留现有页面
    fcntl.flock(held.fileno(), fcntl.LOCK_UN)
    held.close()


def test_sfc_missing_grace_window(tmp_path, monkeypatch):
    from flow_dashboard import hk_short_pipeline as hp
    from flow_dashboard.data.hk_short import loaders

    # 缓存最新一期 = 09-11；最新已完成周 = 09-18，其宽限期至 09-25 EOD
    loaders._write(
        pd.DataFrame(
            {
                "position_date": [pd.Timestamp("2026-09-11")],
                "checked_at": [pd.Timestamp("2026-09-18")],
            }
        ),
        tmp_path / loaders.SFC_NONE_FILE,
    )
    loaders._write(
        pd.DataFrame(
            {
                "code": ["00700"],
                "position_date": [pd.Timestamp("2026-09-11")],
                "published_at": [pd.Timestamp("2026-09-11 15:41", tz="Asia/Shanghai")],
                "available_at": [pd.Timestamp("2026-09-11 15:41", tz="Asia/Shanghai")],
                "fetched_at": [pd.Timestamp("2026-09-11 19:00", tz="Asia/Shanghai")],
            }
        ),
        tmp_path / loaders.SFC_FILE,
    )
    # 09-21 周一：09-18 报告的宽限期未到（至 09-25）→ 不算 missing
    assert not hp._sfc_missing(
        as_of=pd.Timestamp("2026-09-21 18:45", tz="Asia/Shanghai"), cache_dir=tmp_path
    )
    # 09-28 周一：宽限期已过仍缺 09-18 → missing（休市日也要跑，补抓 SFC）
    assert hp._sfc_missing(
        as_of=pd.Timestamp("2026-09-28 18:45", tz="Asia/Shanghai"), cache_dir=tmp_path
    )


def test_launchd_plist_and_runner_script_present():
    root = Path(__file__).resolve().parents[2]
    plist = root / "scripts/launchd/com.ygr.hk-short.eod.plist"
    runner = root / "scripts/flow_dashboard/run_hk_short_eod.py"
    assert plist.exists() and runner.exists()
    text = plist.read_text()
    assert "com.ygr.hk-short.eod" in text
    assert "<integer>18</integer>" in text and "<integer>45</integer>" in text
    assert "run_hk_short_eod.py" in text
    assert "<key>Weekday</key>" not in text  # 无 Weekday：休市日靠 runner 日历短路
    assert "run_hk_short_eod" in runner.read_text()


def test_hk_tab_render_failure_does_not_block_ashare_publish(tmp_path, monkeypatch):
    """港股 tab 渲染抛异常不得阻塞 A股 发布（设计 §3 隔离）。"""
    _mock_ashare_empty(monkeypatch)

    def boom(as_of):
        raise RuntimeError("corrupted parquet")

    monkeypatch.setattr("flow_dashboard.pipeline._render_hk_tab_for_pipeline", boom)
    output_dir = tmp_path / "z"
    path = run_eod_preview(
        data_date="2026-08-12",
        as_of=pd.Timestamp("2026-08-12 19:30", tz="Asia/Shanghai"),
        output_dir=output_dir,
        lock_path=output_dir / "runners.lock",
    )
    html = path.read_text()
    assert 'data-tab="ashare"' in html  # A股 tab 照常
    assert "数据待更新" in html  # 港股 tab 显示横幅
    manifest = json.loads((output_dir / "manifest" / "2026-08-12_v01.json").read_text())
    assert manifest["panel_status"]["hk_data_date"] is None


def test_backfill_cli_wires_windows(tmp_path, monkeypatch):
    """backfill CLI 把窗口参数传给各 loader（SFC 用周数、K线用 secids）。"""
    import importlib.util

    root = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "backfill_hk_short", root / "scripts/flow_dashboard/backfill_hk_short.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    calls = {}

    def fake_loader(name):
        def f(**kw):
            calls[name] = kw

        return f

    monkeypatch.setattr(
        mod,
        "_loaders",
        lambda: {
            "em_day": fake_loader("em_day"),
            "em_watch": fake_loader("em_watch"),
            "hkex": fake_loader("hkex"),
            "sfc": fake_loader("sfc"),
            "kline": fake_loader("kline"),
            "shares": fake_loader("shares"),
            "los": fake_loader("los"),
        },
    )
    mod.main(
        [
            "--as-of",
            "2026-09-18 19:00",
            "--em-days",
            "10",
            "--hkex-days",
            "5",
            "--sfc-weeks",
            "4",
            "--kline-days",
            "30",
            tmp_path.as_posix(),
        ]
    )
    assert calls["em_day"]["start"] == pd.Timestamp("2026-09-08")
    assert calls["hkex"]["start"] == pd.Timestamp("2026-09-13")
    assert calls["sfc"]["weeks"] == 4
    assert calls["kline"]["start"] == pd.Timestamp("2026-08-19")
    assert "116.00700" in calls["kline"]["secids"]
    assert "100.HSI" in calls["kline"]["secids"]
    assert [
        c
        for _, c in __import__(
            "flow_dashboard.config", fromlist=["HK_WATCH_LIST"]
        ).HK_WATCH_LIST
    ] == calls["shares"]["codes"]
