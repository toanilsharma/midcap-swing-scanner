"""
TEST 6 - tests/test_schema_drift.py
Guards against schema drift and field renaming between the Python backend and Netlify dashboard.
Asserts the exact set of keys in scan_results.json, signals, and watchlist candidates.
"""

import json
import os
from typing import Any
import pytest
from tests.test_hermetic_scan import execute_full_scan_pipeline


EXPECTED_TOP_LEVEL_KEYS = {
    "updated_at",
    "market_ok",
    "signals",
    "watchlist",
    "on_deck",
    "scanned_count",
    "leaders_board",
    "inst_summary",
    "deals_stale",
    "landmines",
}

EXPECTED_SIGNAL_KEYS = {
    "Signal Date",
    "Symbol",
    "Sector",
    "Type",
    "Close",
    "Entry",
    "Stop",
    "Target",
    "Qty",
    "Risk Per Unit",
    "Risk Amount",
    "ATR14",
    "RSI14",
    "rs_rating",
    "base_maturity",
    "days_in_base",
    "inst_footprint",
    "next_event",
    "event_blocked_reason",
}

EXPECTED_WATCHLIST_KEYS = {
    "Symbol",
    "Sector",
    "SectorBullish",
    "Trend",
    "Coiling",
    "DistToBreakout%",
    "Close",
    "VolDryup",
    "RsiInRange",
    "RSI14",
    "ATR14",
    "score",
    "grade",
    "Score",
    "Grade",
    "rs_rating",
    "base_maturity",
    "days_in_base",
    "inst_footprint",
    "next_event",
    "event_blocked_reason",
}

EXPECTED_POSITION_KEYS = {
    "symbol",
    "entry_date",
    "entry_price",
    "qty",
    "stop",
    "planned_stop",
    "target",
    "tags",
    "warn_event",
    "next_event",
}

EXPECTED_BACKTEST_TOP_LEVEL_KEYS = {
    "period",
    "trades",
    "equity_curve",
    "win_rate",
    "avg_win_R",
    "avg_loss_R",
    "expectancy_R",
    "profit_factor",
    "max_drawdown_pct",
    "by_grade",
    "by_signal_type",
    "tail_capture",
}


def test_schema_keys_exact_match(tmp_cwd: Any, monkeypatch: pytest.MonkeyPatch):
    """
    Ensures that scan_results.json top-level, signals, and watchlist entries
    produce the exact contract expected by dashboard/app.js.
    """
    monkeypatch.setenv("QUIET", "1")
    monkeypatch.setenv("SKIP_GIT_PUSH", "1")

    signals, watchlist, count, mkt_ok = execute_full_scan_pipeline()

    with open("scan_results.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. Top-level keys
    actual_top_keys = set(data.keys())
    assert actual_top_keys == EXPECTED_TOP_LEVEL_KEYS, (
        f"Top-level schema drift detected!\n"
        f"Missing: {EXPECTED_TOP_LEVEL_KEYS - actual_top_keys}\n"
        f"Unexpected: {actual_top_keys - EXPECTED_TOP_LEVEL_KEYS}"
    )

    # 2. Signals schema
    assert len(data["signals"]) > 0, "Expected at least one signal in hermetic scan"
    for sig in data["signals"]:
        actual_sig_keys = set(sig.keys())
        assert actual_sig_keys == EXPECTED_SIGNAL_KEYS, (
            f"Signal item schema drift in {sig.get('Symbol')}!\n"
            f"Missing: {EXPECTED_SIGNAL_KEYS - actual_sig_keys}\n"
            f"Unexpected: {actual_sig_keys - EXPECTED_SIGNAL_KEYS}"
        )

    # 3. Watchlist schema
    assert len(data["watchlist"]) > 0, "Expected at least one watchlist candidate in hermetic scan"
    for wl in data["watchlist"]:
        actual_wl_keys = set(wl.keys())
        assert actual_wl_keys == EXPECTED_WATCHLIST_KEYS, (
            f"Watchlist item schema drift in {wl.get('Symbol')}!\n"
            f"Missing: {EXPECTED_WATCHLIST_KEYS - actual_wl_keys}\n"
            f"Unexpected: {actual_wl_keys - EXPECTED_WATCHLIST_KEYS}"
        )


def test_backtest_schema_drift_tolerant(tmp_cwd: Any):
    """
    Guards backtest_results.json top-level schema contract.
    Asserts exact allowed top-level keys when present, and proves that
    an absent file (no archive yet) is cleanly tolerated without crashing.
    """
    # 1. Tolerant when absent
    assert not os.path.exists("backtest_results.json")
    # Absent file must be tolerated by frontend/backend when no archive exists

    # 2. Exact contract match when generated
    from backtest import backtest
    empty_res = backtest(archive_dir="non_existent_archive")
    assert set(empty_res.keys()) == EXPECTED_BACKTEST_TOP_LEVEL_KEYS

    with open("backtest_results.json", "w", encoding="utf-8") as f:
        json.dump(empty_res, f, indent=2)

    with open("backtest_results.json", "r", encoding="utf-8") as f:
        loaded = json.load(f)

    actual_bt_keys = set(loaded.keys())
    assert actual_bt_keys == EXPECTED_BACKTEST_TOP_LEVEL_KEYS, (
        f"backtest_results.json schema drift detected!\n"
        f"Missing: {EXPECTED_BACKTEST_TOP_LEVEL_KEYS - actual_bt_keys}\n"
        f"Unexpected: {actual_bt_keys - EXPECTED_BACKTEST_TOP_LEVEL_KEYS}"
    )

