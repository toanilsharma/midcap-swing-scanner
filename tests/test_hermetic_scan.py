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
    open_pos, warn_lines = main.evaluate_open_positions_events()
    landmines = main.compute_landmines(watchlist, getattr(main, "_LAST_ON_DECK", []), open_pos)
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
        "landmines": getattr(main, "_LANDMINES", landmines),
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
        "scanned_count", "leaders_board", "inst_summary", "deals_stale", "landmines"
    }
    assert "on_deck" in data
    assert isinstance(data["on_deck"], list)
    assert "leaders_board" in data
    assert isinstance(data["leaders_board"], list)
    assert "inst_summary" in data
    assert isinstance(data["inst_summary"], dict)
    assert "deals_stale" in data
    assert "landmines" in data
    assert isinstance(data["landmines"], list)
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
        "rs_rating", "base_maturity", "days_in_base", "inst_footprint", "next_event", "event_blocked_reason"
    }
    assert expected_fields.issubset(sig.keys()), f"Signal missing expected fields: {expected_fields - set(sig.keys())}"
    assert "rs_rating" in sig
    assert isinstance(sig["base_maturity"], int)
    assert isinstance(sig["days_in_base"], int)
    assert "inst_footprint" in sig
    assert "next_event" in sig
    assert "event_blocked_reason" in sig

    if data["watchlist"]:
        wl0 = data["watchlist"][0]
        assert "rs_rating" in wl0
        assert isinstance(wl0["base_maturity"], int)
        assert isinstance(wl0["days_in_base"], int)
        assert "inst_footprint" in wl0
        assert "next_event" in wl0
        assert "event_blocked_reason" in wl0

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


def test_event_entry_blocks(tmp_cwd: Any, monkeypatch: pytest.MonkeyPatch):
    """
    Test 10 requirement:
    A synthetic symbol with a LOCKIN 2 days out => entry blocked.
    Mirrors the S2 earnings-unknown-block test.
    """
    monkeypatch.setenv("QUIET", "1")
    monkeypatch.setenv("SKIP_GIT_PUSH", "1")

    # Set up LOCKIN event 2 days in the future for AAA.NS (which would normally generate a signal)
    today = datetime.datetime.now(main.IST_TZ).date()
    lockin_date = (today + datetime.timedelta(days=2)).isoformat()
    events_data = {
        "AAA.NS": [
            {
                "type": "LOCKIN",
                "date": lockin_date,
                "note": "Promoter lockin expiry"
            }
        ]
    }
    with open("events.json", "w", encoding="utf-8") as f:
        json.dump(events_data, f)

    # 1. scan_symbol must return None because entry is blocked by near-term LOCKIN
    sig = main.scan_symbol("AAA.NS")
    assert sig is None, "scan_symbol MUST return None when a known event is within 7 days (blackout)"

    # 2. diagnose must report event_blocked_reason
    diag = main.diagnose("AAA.NS")
    assert diag is not None
    assert diag["event_blocked_reason"] is not None
    assert "LOCKIN" in diag["event_blocked_reason"]
    assert "2d" in diag["event_blocked_reason"]
    assert diag["next_event"]["days_to_event"] == 2


def test_event_open_warns_not_exits(tmp_cwd: Any, monkeypatch: pytest.MonkeyPatch):
    """
    Test 10 requirement:
    Held symbol with imminent event => warn_event true AND position still open
    with original stop/target, i.e. NOT force-closed.
    """
    monkeypatch.setenv("QUIET", "1")
    monkeypatch.setenv("SKIP_GIT_PUSH", "1")

    today = datetime.datetime.now(main.IST_TZ).date()
    event_date = (today + datetime.timedelta(days=2)).isoformat()

    # Create open position for HOLD_SYM
    initial_pos = [
        {
            "symbol": "HOLD_SYM",
            "entry_date": "2026-10-15",
            "entry_price": 500.0,
            "qty": 10,
            "stop": 465.0,
            "planned_stop": 465.0,
            "target": 570.0,
            "tags": ["swing"]
        }
    ]
    with open("open_positions.json", "w", encoding="utf-8") as f:
        json.dump(initial_pos, f)

    # Put AGM event 2 days out for HOLD_SYM
    events_data = {
        "HOLD_SYM": [
            {
                "type": "AGM",
                "date": event_date,
                "note": "Annual General Meeting"
            }
        ]
    }
    with open("events.json", "w", encoding="utf-8") as f:
        json.dump(events_data, f)

    # Run open positions evaluation
    positions, warn_lines = main.evaluate_open_positions_events()

    # 1. Assert warn_event is True
    assert len(positions) == 1
    pos = positions[0]
    assert pos["warn_event"] is True
    assert pos["next_event"]["type"] == "AGM"
    assert pos["next_event"]["days_to_event"] == 2
    assert len(warn_lines) == 1
    assert "🔔 HOLD_SYM event (AGM) in 2 days — review hold" in warn_lines[0]

    # 2. Position is STILL OPEN with original parameters (never auto-exited or modified)
    assert pos["symbol"] == "HOLD_SYM"
    assert pos["qty"] == 10
    assert pos["entry_price"] == 500.0
    assert pos["stop"] == 465.0
    assert pos["target"] == 570.0

    # 3. Verify file on disk is also updated with warn_event
    with open("open_positions.json", "r", encoding="utf-8") as f:
        saved_positions = json.load(f)
    assert len(saved_positions) == 1
    assert saved_positions[0]["warn_event"] is True


def test_hermetic_empty_events_no_crash(tmp_cwd: Any, monkeypatch: pytest.MonkeyPatch):
    """
    Hermetic test with empty events.json:
    next_event is null, landmines is empty, scan still generates JSON, no crash.
    """
    monkeypatch.setenv("QUIET", "1")
    monkeypatch.setenv("SKIP_GIT_PUSH", "1")

    with open("events.json", "w", encoding="utf-8") as f:
        json.dump({}, f)

    signals, watchlist, count, mkt_ok = execute_full_scan_pipeline()

    assert os.path.exists(main.SCAN_RESULTS_FILE)
    with open(main.SCAN_RESULTS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "landmines" in data
    assert data["landmines"] == []

    for sig in data["signals"]:
        assert sig["next_event"] is None
        assert sig["event_blocked_reason"] is None

    for wl in data["watchlist"]:
        assert wl["next_event"] is None
        assert wl["event_blocked_reason"] is None



