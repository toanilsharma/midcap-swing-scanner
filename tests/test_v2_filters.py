"""
Unit tests for Version 2 Fail-Closed Gating & Filtering Engine:
- Sector Strength Filter (Strictly fail-closed on missing data or downtrends)
- Liquidity Filter (Fail-closed: requires ₹20 Crores 50-day average turnover)
- Relative Strength vs Benchmark (Outperforms index over 50 bars)
- Earnings Blackout Filter (Blocks entries within 7 days prior to earnings)
"""

import datetime
import numpy as np
import pandas as pd
import pytest

from core.filters import (
    check_sector_strength,
    check_liquidity,
    check_relative_strength,
    check_earnings_blackout,
    get_sector_symbol,
)


def test_sector_symbol_mapping():
    """Verify sector mapping for key liquid symbols and fallback."""
    assert get_sector_symbol("COFORGE.NS") == "^CNXIT"
    assert get_sector_symbol("FEDERALBNK.NS") == "^NSEBANK"
    assert get_sector_symbol("MANKIND.NS") == "^CNXPHARMA"
    # Unmapped or energy/consumption symbols map to ^NSEI
    assert get_sector_symbol("RELIANCE.NS") == "^NSEI"
    assert get_sector_symbol("UNKNOWN_SYM.NS") == "^NSEI"


def test_sector_strength_fail_closed_on_missing_or_short_data():
    """
    CRITICAL NON-NEGOTIABLE GUARANTEE:
    If sector data is None, empty, or has fewer than 200 bars, it MUST FAIL CLOSED.
    It must NEVER return True or approve a trade.
    """
    # 1. None DataFrame
    is_ok, reason, sec_sym = check_sector_strength("COFORGE.NS", None)
    assert not is_ok
    assert reason == "BLOCKED_SECTOR_DATA_UNAVAILABLE"
    assert sec_sym == "^CNXIT"

    # 2. Empty DataFrame
    is_ok, reason, sec_sym = check_sector_strength("COFORGE.NS", pd.DataFrame())
    assert not is_ok
    assert reason == "BLOCKED_SECTOR_DATA_UNAVAILABLE"

    # 3. Short DataFrame (< 200 bars)
    short_df = pd.DataFrame({
        "Close": [100.0] * 150,
        "SMA50": [95.0] * 150,
        "SMA200": [90.0] * 150,
    })
    is_ok, reason, sec_sym = check_sector_strength("COFORGE.NS", short_df)
    assert not is_ok
    assert reason == "BLOCKED_SECTOR_DATA_UNAVAILABLE"


def test_sector_strength_uptrend_vs_downtrend():
    """
    Verify sector uptrend (Close > SMA50 > SMA200 and Close > SMA200)
    vs downtrend or MA bearish cross.
    """
    n = 220
    # Scenario A: Valid Sector Uptrend
    uptrend_df = pd.DataFrame({
        "Close": [120.0] * n,
        "SMA50": [110.0] * n,
        "SMA200": [100.0] * n,
    })
    is_ok, reason, _ = check_sector_strength("COFORGE.NS", uptrend_df)
    assert is_ok
    assert reason == "SECTOR_IN_UPTREND"

    # Scenario B: Bearish Sector (Close < SMA50)
    bearish_df = pd.DataFrame({
        "Close": [105.0] * n,
        "SMA50": [110.0] * n,
        "SMA200": [100.0] * n,
    })
    is_ok, reason, _ = check_sector_strength("COFORGE.NS", bearish_df)
    assert not is_ok
    assert reason == "BLOCKED_SECTOR_DOWNTREND"

    # Scenario C: SMA Death Cross (SMA50 < SMA200)
    death_cross_df = pd.DataFrame({
        "Close": [95.0] * n,
        "SMA50": [98.0] * n,
        "SMA200": [102.0] * n,
    })
    is_ok, reason, _ = check_sector_strength("COFORGE.NS", death_cross_df)
    assert not is_ok
    assert reason == "BLOCKED_SECTOR_DOWNTREND"


def test_liquidity_filter_fail_closed():
    """
    Verify 50-day average daily turnover filter (₹20 Crores min = 200,000,000).
    """
    # 1. Short data (< 50 bars) -> Fail closed
    short_df = pd.DataFrame({
        "Close": [100.0] * 30,
        "Volume": [10000000.0] * 30,
    })
    is_ok, _, reason = check_liquidity(short_df)
    assert not is_ok
    assert "BLOCKED_INSUFFICIENT_HISTORY" in reason

    # 2. Turnover < 20 Crores (e.g. 100 * 1,000,000 = 10 Cr) -> Fail closed
    low_liq_df = pd.DataFrame({
        "Close": [100.0] * 60,
        "Volume": [1000000.0] * 60,  # 10 Crores daily turnover
    })
    is_ok, turnover, reason = check_liquidity(low_liq_df)
    assert not is_ok
    assert turnover == 100000000.0
    assert "BLOCKED_LOW_TURNOVER" in reason

    # 3. Turnover >= 20 Crores (e.g. 500 * 500,000 = 25 Cr) -> Pass
    high_liq_df = pd.DataFrame({
        "Close": [500.0] * 60,
        "Volume": [500000.0] * 60,  # 25 Crores daily turnover
    })
    is_ok, turnover, reason = check_liquidity(high_liq_df)
    assert is_ok
    assert turnover == 250000000.0
    assert reason == "LIQUIDITY_OK"


def test_relative_strength_filter():
    """
    Verify 50-day stock return vs index return.
    """
    n = 60
    # Stock up 20% over last 50 days (100 -> 120)
    stock_df = pd.DataFrame({
        "Close": np.linspace(100.0, 120.0, n),
    })
    # Index up 5% over last 50 days (100 -> 105)
    index_df = pd.DataFrame({
        "Close": np.linspace(100.0, 105.0, n),
    })

    is_ok, s_ret, idx_ret, reason = check_relative_strength(stock_df, index_df, lookback=50)
    assert is_ok
    assert s_ret > idx_ret
    assert reason == "RELATIVE_STRENGTH_BEATS_INDEX"

    # Index outperforming stock (Stock up 5%, Index up 15%)
    weak_stock_df = pd.DataFrame({
        "Close": np.linspace(100.0, 105.0, n),
    })
    strong_index_df = pd.DataFrame({
        "Close": np.linspace(100.0, 115.0, n),
    })
    is_ok, s_ret, idx_ret, reason = check_relative_strength(weak_stock_df, strong_index_df, lookback=50)
    assert not is_ok
    assert s_ret < idx_ret
    assert reason == "BLOCKED_WEAKER_THAN_INDEX"


def test_earnings_blackout_filter():
    """
    Verify blackout blocking when an event is within 7 days.
    """
    ref_date = datetime.date(2026, 11, 23)
    events_data = {
        "MANKIND.NS": [
            {"date": "2026-11-26", "type": "EARNINGS"},  # 3 days away -> MUST BLOCK
        ],
        "GLENMARK.NS": [
            {"date": "2027-01-20", "type": "EARNINGS"},  # 58 days away -> PASS
        ],
    }

    # Mankind should be blocked
    is_blocked, reason, ev = check_earnings_blackout("MANKIND.NS", events_data, blackout_days=7, ref_date=ref_date)
    assert is_blocked
    assert reason == "BLOCKED_EARNINGS_IN_3D"
    assert ev["days_to_event"] == 3

    # Glenmark should pass
    is_blocked, reason, ev = check_earnings_blackout("GLENMARK.NS", events_data, blackout_days=7, ref_date=ref_date)
    assert not is_blocked
    assert reason is None

    # Symbol with no events should pass
    is_blocked, reason, ev = check_earnings_blackout("UNKNOWN.NS", events_data, blackout_days=7, ref_date=ref_date)
    assert not is_blocked
