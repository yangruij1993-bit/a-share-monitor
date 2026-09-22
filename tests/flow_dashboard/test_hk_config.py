"""hk_short 配置契约测试。"""
from flow_dashboard import config


def test_hk_watch_list_frozen():
    assert len(config.HK_WATCH_LIST) == 8
    codes = [c for _, c in config.HK_WATCH_LIST]
    assert codes == ["0700.HK", "9988.HK", "3690.HK", "1810.HK",
                     "0981.HK", "9992.HK", "2800.HK", "3033.HK"]


def test_hk_thresholds_frozen():
    t = config.HK_THRESHOLDS
    assert t["mkt_sfc_delta_bp"] == 3.0
    assert t["stock_sfc_delta_bp"] == 5.0
    assert t["weekly_intensity_high"] == 1.25
    assert t["ssr_pct_high"] == 80.0
    assert t["price_ret_bp"] == 100.0
    assert t["participation_high"] == 1.20
    assert t["etf_interference"] == 0.30
    assert t["ssr_pct_min_obs"] == 20
    assert t["ssr_pct_window"] == 60
    assert t["sfc_min_comparable"] == 100
    assert t["sfc_min_coverage"] == 0.80


def test_hk_cache_dir_and_secids():
    assert config.HK_SHORT_CACHE_DIR.name == "cache"
    assert config.HK_INDEX_SECIDS == {"HSI": "100.HSI", "HSTECH": "124.HSTECH"}
