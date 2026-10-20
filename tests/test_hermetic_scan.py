"""
TEST 5 - tests/test_hermetic_scan.py
End-to-end integration scan verification under 100% hermetic offline conditions.
- Uses synthetic textbook long and downtrend DataFrames.
- Asserts scan_results.json generation and schema integrity.
- Confirms proactive sends when unmuted vs silence when QUIET=1.
- Confirms single combined message when digest=True.
"""

import datetime
import json
import os
from typing import Any, Dict, List, Tuple
import pytest
import main
from tests.test_rules_golden import build_scenario_dataframe




def execute_full_scan_pipeline() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], int, bool]:
    """
    Executes the scanner, watchlist generation, digest aggregation, and dashboard publishing
    identically to the production main scan workflow.
    """
    settings = main.load_alert_settings()
    is_digest = settings.get("digest", False)

    # 1. Run scanner
    signals, scanned_count, is_mkt_ok = main.run_scanner()

    # 2. Watchlist
    watchlist = main.get_watchlist_candidates()
    if main.SEND_WATCHLIST:
        wl_text = main.build_watchlist_text(watchlist)
        if is_digest:
            main._DIGEST_MESSAGES.append(("watchlist", wl_text))
        else:
            main.send_telegram(wl_text, kind="proactive", msg_type="watchlist")

    # 3. Digest aggregation if enabled
    if is_digest and main._DIGEST_MESSAGES:
        enable_flags = settings.get("enable", {})
        valid_parts = [
            text for mtype, text in main._DIGEST_MESSAGES
            if enable_flags.get(mtype, True) and text.strip()
        ]
        if valid_parts:
            separator = "\n\n" + ("-" * 30) + "\n\n"
            combined = separator.join(valid_parts)
            main.send_telegram(combined, kind="proactive", msg_type="scan")
        main._DIGEST_MESSAGES.clear()

    # 4. Save scan_results.json
    now_str = datetime.datetime.now(main.IST_TZ).isoformat()
    scan_data = {
        "updated_at": now_str,
        "market_ok": is_mkt_ok,
        "signals": signals,
        "watchlist": watchlist,
        "on_deck": getattr(main, "_LAST_ON_DECK", []),
        "scanned_count": scanned_count,
        "leaders_board": getattr(main, "_LEADERS_BOARD", []),
        "inst_summary": getattr(main, "_INST_SUMMARY", {"accumulation": 0, "churn": 0, "unknown": scanned_count}),
        "deals_stale": getattr(main, "_DEALS_STALE", True),
    }
    with open(main.SCAN_RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump(scan_data, f, indent=2, ensure_ascii=False)

    return signals, watchlist, scanned_count, is_mkt_ok


def test_hermetic_scan_unmuted(tmp_cwd: Any, spy_posts: list, pin_ist_time: Any, monkeypatch: pytest.MonkeyPatch):
    """
    Unmuted daytime scan (QUIET=0, 14:00 IST):
    - scan_results.json is generated with valid structure.
    - AAA.NS (textbook uptrend) appears in signals; BBB.NS (downtrend) does NOT.
    - Full signal schema is present.
    - Proactive Telegram sends dispatched (>= 1).
    """
    monkeypatch.setenv("QUIET", "0")
    pin_ist_time("2026-10-18 14:00")
    settings = dict(main.DEFAULT_ALERT_SETTINGS)
    settings["quiet_start"] = "off"
    settings["quiet_end"] = "off"
    settings["digest"] = False
    main.save_alert_settings(settings)

    signals, watchlist, count, mkt_ok = execute_full_scan_pipeline()

    # Assert file exists and parses
    assert os.path.exists(main.SCAN_RESULTS_FILE)
    with open(main.SCAN_RESULTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert set(data.keys()) == {
        "updated_at", "market_ok", "signals", "watchlist", "on_deck",
        "scanned_count", "leaders_board", "inst_summary", "deals_stale"
    }
    assert "on_deck" in data
    assert isinstance(data["on_deck"], list)
    assert "leaders_board" in data
    assert isinstance(data["leaders_board"], list)
    assert "inst_summary" in data
    assert isinstance(data["inst_summary"], dict)
    assert "deals_stale" in data
    assert data["market_ok"] is True
    assert data["scanned_count"] == 2

    # Verify symbol presence
    signal_symbols = [s["Symbol"] for s in data["signals"]]
    assert "AAA.NS" in signal_symbols, "Uptrend textbook stock AAA.NS must trigger a signal"
    assert "BBB.NS" not in signal_symbols, "Downtrend stock BBB.NS must not trigger a signal"

    # Verify signal dictionary schema
    sig = data["signals"][0]
    expected_fields = {
        "Signal Date", "Symbol", "Sector", "Type", "Close", "Entry",
        "Stop", "Target", "Qty", "Risk Per Unit", "Risk Amount", "ATR14", "RSI14",
        "rs_rating", "base_maturity", "days_in_base", "inst_footprint"
    }
    assert expected_fields.issubset(sig.keys()), f"Signal missing expected fields: {expected_fields - set(sig.keys())}"
    assert "rs_rating" in sig
    assert isinstance(sig["base_maturity"], int)
    assert isinstance(sig["days_in_base"], int)
    assert "inst_footprint" in sig

    if data["watchlist"]:
        wl0 = data["watchlist"][0]
        assert "rs_rating" in wl0
        assert isinstance(wl0["base_maturity"], int)
        assert isinstance(wl0["days_in_base"], int)
        assert "inst_footprint" in wl0

    # Telegram sends should have fired
    assert len(spy_posts) >= 1, "Expected at least 1 proactive Telegram alert when unmuted"


def test_hermetic_scan_quiet_env_generates_file_without_telegram(
    tmp_cwd: Any,
    spy_posts: list,
    pin_ist_time: Any,
    monkeypatch: pytest.MonkeyPatch
):
    """
    Muted scan (QUIET=1):
    - scan_results.json STILL generated and valid.
    - spy_posts is completely EMPTY (zero HTTP calls).
    """
    monkeypatch.setenv("QUIET", "1")
    pin_ist_time("2026-10-18 14:00")
    settings = dict(main.DEFAULT_ALERT_SETTINGS)
    settings["digest"] = False
    main.save_alert_settings(settings)

    signals, watchlist, count, mkt_ok = execute_full_scan_pipeline()

    assert os.path.exists(main.SCAN_RESULTS_FILE)
    with open(main.SCAN_RESULTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert len(data["signals"]) == 1
    assert data["signals"][0]["Symbol"] == "AAA.NS"
    assert len(spy_posts) == 0, "No proactive alerts allowed when QUIET=1"


def test_hermetic_scan_digest_combines_proactive_sends(
    tmp_cwd: Any,
    spy_posts: list,
    pin_ist_time: Any,
    monkeypatch: pytest.MonkeyPatch
):
    """
    Digest mode (digest=True, QUIET=0):
    - Combines scan results + watchlist into exactly ONE proactive message instead of multiple.
    """
    monkeypatch.setenv("QUIET", "0")
    pin_ist_time("2026-10-18 14:00")
    settings = dict(main.DEFAULT_ALERT_SETTINGS)
    settings["quiet_start"] = "off"
    settings["quiet_end"] = "off"
    settings["digest"] = True
    main.save_alert_settings(settings)

    main._DIGEST_MESSAGES.clear()
    execute_full_scan_pipeline()

    # Assert exactly 1 combined send was made
    assert len(spy_posts) == 1, f"Expected exactly 1 combined digest message, got {len(spy_posts)}"
    combined_body = spy_posts[0][1]["text"]
    assert "AAA" in combined_body


def test_rs_graceful_small_universe(tmp_cwd: Any, monkeypatch: pytest.MonkeyPatch):
    """
    With N=2 symbols (eval universe < 30), rs_rating must gracefully degrade
    to None on all outputs with no exception and no division by zero.
    """
    monkeypatch.setenv("QUIET", "1")
    signals, watchlist, count, mkt_ok = execute_full_scan_pipeline()

    with open(main.SCAN_RESULTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 1. Assert keys exist and rs_rating is None for small universe
    assert len(data["signals"]) > 0
    for sig in data["signals"]:
        assert "rs_rating" in sig
        assert sig["rs_rating"] is None
        assert isinstance(sig["base_maturity"], int)
        assert isinstance(sig["days_in_base"], int)

    assert len(data["watchlist"]) > 0
    for wl in data["watchlist"]:
        assert "rs_rating" in wl
        assert wl["rs_rating"] is None
        assert isinstance(wl["base_maturity"], int)
        assert isinstance(wl["days_in_base"], int)

    # 2. leaders_board is empty list
    assert "leaders_board" in data
    assert data["leaders_board"] == []


def test_inst_footprint_failopen_unknown(tmp_cwd: Any, monkeypatch: pytest.MonkeyPatch):
    """
    Hermetic test: with NO deals.json present in tmp_cwd:
    - Every symbol => inst_footprint 'unknown'.
    - inst_summary => {'accumulation': 0, 'churn': 0, 'unknown': N}.
    - deals_stale => True.
    - scan still writes JSON, no crash.
    """
    monkeypatch.setenv("QUIET", "1")
    monkeypatch.setenv("SKIP_GIT_PUSH", "1")

    # Confirm deals.json is absent in hermetic test sandbox
    assert not os.path.exists("deals.json")

    signals, watchlist, count, mkt_ok = execute_full_scan_pipeline()

    assert os.path.exists(main.SCAN_RESULTS_FILE)
    with open(main.SCAN_RESULTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["deals_stale"] is True
    assert data["inst_summary"] == {"accumulation": 0, "churn": 0, "unknown": count}

    for sig in data["signals"]:
        assert sig["inst_footprint"] == "unknown"

    for wl in data["watchlist"]:
        assert wl["inst_footprint"] == "unknown"

    for od in data.get("on_deck", []):
        assert od["inst_footprint"] == "unknown"


