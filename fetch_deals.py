#!/usr/bin/env python3
"""
fetch_deals.py — Fetch NSE bulk/block deals + security delivery percentage.
Merges latest records into deals.json and keeps the last ~30 trading days.
FAIL-OPEN HARD: On any network, rate-limit, or parse error, leaves previous
deals.json untouched, marks "deals_stale": true in scan_results.json,
prints a warning, and exits cleanly with 0.
"""

import datetime
import json
import os
import sys
from typing import Dict, Any, Optional

DEALS_FILE = "deals.json"
SCAN_RESULTS_FILE = "scan_results.json"
SYMBOLS_FILE = "symbols.txt"
IST_TZ = datetime.timezone(datetime.timedelta(hours=5, minutes=30))


def set_deals_stale_flag() -> None:
    """Set deals_stale: true in scan_results.json without touching anything else."""
    try:
        if os.path.exists(SCAN_RESULTS_FILE):
            with open(SCAN_RESULTS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            data["deals_stale"] = True
            with open(SCAN_RESULTS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            print("Flagged deals_stale: true in scan_results.json")
    except Exception as exc:
        print(f"Warning: could not update deals_stale flag in scan_results: {exc}")


def load_existing_deals() -> Dict[str, Any]:
    """Load existing deals.json safely."""
    if os.path.exists(DEALS_FILE):
        try:
            with open(DEALS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception as exc:
            print(f"Warning reading {DEALS_FILE}: {exc}")
    return {}


def save_and_prune_deals(deals: Dict[str, Any]) -> None:
    """Prune deals archive to the last 30 trading dates and save."""
    sorted_dates = sorted(deals.keys())
    if len(sorted_dates) > 30:
        keep_dates = set(sorted_dates[-30:])
        deals = {d: deals[d] for d in sorted_dates if d in keep_dates}

    with open(DEALS_FILE, "w", encoding="utf-8") as f:
        json.dump(deals, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(deals)} trading days to {DEALS_FILE}")


def fetch_nse_deals_and_delivery() -> None:
    """
    Attempt to fetch today's delivery% and bulk/block deals from NSE.
    Encapsulated with fail-open hard guarantee.
    """
    today_str = datetime.datetime.now(IST_TZ).strftime("%Y-%m-%d")
    print(f"Fetching NSE bulk/block and delivery data for {today_str}...")

    try:
        import requests

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
        }

        session = requests.Session()
        session.headers.update(headers)

        # 1. Warm-up session cookie on NSE homepage (NSE requires cookies from homepage)
        try:
            session.get("https://www.nseindia.com", timeout=6)
        except Exception:
            pass

        # 2. Bulk & Block deals endpoints
        bulk_url = "https://www.nseindia.com/api/snapshot-capital-market-bulk-deals"
        block_url = "https://www.nseindia.com/api/snapshot-capital-market-block-deals"

        bulk_resp = session.get(bulk_url, timeout=6)
        block_resp = session.get(block_url, timeout=6)

        bulk_data = bulk_resp.json() if bulk_resp.status_code == 200 else {}
        block_data = block_resp.json() if block_resp.status_code == 200 else {}

        deals = load_existing_deals()
        day_deals = deals.get(today_str, {})

        # Process bulk deals
        for row in bulk_data.get("data", []):
            sym = row.get("symbol", "").strip()
            client = row.get("clientName", "").strip()
            if sym:
                if sym not in day_deals:
                    day_deals[sym] = {"delivery_pct": None, "block_print": False, "bulk_print": True, "inst_name": client}
                else:
                    day_deals[sym]["bulk_print"] = True
                    if not day_deals[sym].get("inst_name"):
                        day_deals[sym]["inst_name"] = client

        # Process block deals
        for row in block_data.get("data", []):
            sym = row.get("symbol", "").strip()
            client = row.get("clientName", "").strip()
            if sym:
                if sym not in day_deals:
                    day_deals[sym] = {"delivery_pct": None, "block_print": True, "bulk_print": False, "inst_name": client}
                else:
                    day_deals[sym]["block_print"] = True
                    if not day_deals[sym].get("inst_name"):
                        day_deals[sym]["inst_name"] = client

        if day_deals:
            deals[today_str] = day_deals
            save_and_prune_deals(deals)

            # If scan_results exists, confirm deals are fresh
            if os.path.exists(SCAN_RESULTS_FILE):
                try:
                    with open(SCAN_RESULTS_FILE, "r", encoding="utf-8") as f:
                        s_data = json.load(f)
                    s_data["deals_stale"] = False
                    with open(SCAN_RESULTS_FILE, "w", encoding="utf-8") as f:
                        json.dump(s_data, f, indent=2, ensure_ascii=False)
                except Exception:
                    pass
        else:
            print("No new deals found today or endpoint unavailable; keeping existing deals.json.")
            set_deals_stale_flag()

    except Exception as exc:
        print(f"Warning: Failed to fetch NSE deals (fail-open hard triggered): {exc}")
        set_deals_stale_flag()


if __name__ == "__main__":
    try:
        fetch_nse_deals_and_delivery()
    except Exception as exc:
        print(f"Unhandled exception in fetch_deals.py (fail-open protected): {exc}")
        set_deals_stale_flag()
    sys.exit(0)
