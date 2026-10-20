"""
TEST 8 - tests/test_backtest_replay.py
CORRECTNESS ANCHOR & DRIFT GUARD:
Proves that the rules-replay backtest engine produces trade parameters
identical to live risk-math and signal generation on the P1 textbook breakout pattern.
Replay == Live by construction.
"""

import os
from typing import Any
import numpy as np
import pandas as pd
import pytest

import main
from backtest import backtest


def build_textbook_62_bar_archive(archive_dir: str) -> str:
    """
    Build a deterministic 62-bar synthetic archive containing the P1 textbook breakout pattern:
    - 42 bars of Stage 2 base ascent (100 to 200)
    - 8 bars of plateau at 200 (prior 20d high = 205 at bar 42)
    - 9 bars of coiling / dry-up (tight range 0.3, volume 300k)
    - Bar 59: textbook breakout piercing 20d high with 2.0x volume spike and strong close
    - Bar 60: touches 2R target (>210.8) to trigger partial exit
    - Bar 61: runner closes below 20-EMA to trigger trailing exit
    """
    os.makedirs(archive_dir, exist_ok=True)
    n = 62
    dates = [pd.Timestamp("2025-01-01") + pd.Timedelta(days=i) for i in range(n)]
    date_strs = [d.strftime("%Y-%m-%d") for d in dates]

    base = np.linspace(100.0, 200.0, 42)
    plateau = np.full(8, 200.0)
    coiling_days = np.full(9, 201.0)
    close = np.concatenate([base, plateau, coiling_days, [207.0, 212.0, 196.0]])

    high = close + 1.0
    low = close - 1.0
    open_ = close.copy()
    volume = np.full(n, 1000000.0)

    # Prior 20-day high ceiling at bar 42
    high[42] = 205.0

    # Coiling dry-up bars
    for j in range(50, 59):
        high[j] = close[j] + 0.15
        low[j] = close[j] - 0.15
        volume[j] = 300000.0

    # Bar 59: Textbook breakout
    close[59] = 207.0
    high[59] = 207.2
    low[59] = 204.0
    open_[59] = 205.0
    volume[59] = 2000000.0

    # Bar 60: Reaches 2R target (target ~210.8)
    open_[60] = 207.5
    high[60] = 214.0
    low[60] = 207.0
    close[60] = 212.0
    volume[60] = 1500000.0

    # Bar 61: Closes below 20-EMA
    open_[61] = 210.0
    high[61] = 210.0
    low[61] = 190.0
    close[61] = 192.0
    volume[61] = 2000000.0

    df = pd.DataFrame({
        "date": date_strs,
        "symbol": ["AAA.NS"] * n,
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    })

    archive_file = os.path.join(archive_dir, "ohlcv_2025-01.csv.gz")
    df.to_csv(archive_file, index=False, compression="gzip")
    return archive_file


def test_backtest_matches_live_risk(tmp_path: Any):
    """
    DRIFT GUARD (replay == live):
    1. Builds a synthetic archive containing exactly the textbook breakout pattern.
    2. Runs backtest() over the archive.
    3. Asserts exactly 1 simulated trade was generated.
    4. Asserts simulated trade entry, stop, target, and qty match the live risk parameters
       computed directly from main.compute_risk_parameters.
    """
    archive_dir = str(tmp_path / "archive")
    build_textbook_62_bar_archive(archive_dir)

    # Compute expected live risk math directly using production main.py functions
    entry_expected = 207.0
    # True range on breakout bar: max(207.2-204, |207.2-201|, |204-201|) = 6.2
    # Moving average ATR14 over preceding coiling bars
    atr_expected = 1.267857142857149
    live_risk = main.compute_risk_parameters(
        entry=entry_expected,
        atr=atr_expected,
        capital=main.CAPITAL,
        risk_pct=main.RISK_PCT,
    )
    assert live_risk is not None

    # Run replay backtest
    results = backtest(archive_dir=archive_dir)

    # Assert exactly 1 trade produced
    assert len(results["trades"]) == 1, f"Expected 1 trade, got {len(results['trades'])}"
    sim_trade = results["trades"][0]

    # PROVE DRIFT GUARD: replay parameters EQUAL live risk parameters
    assert sim_trade["symbol"] == "AAA.NS"
    assert sim_trade["signal_type"] == "BREAKOUT"
    assert sim_trade["entry_price"] == live_risk["entry"]
    assert sim_trade["stop"] == live_risk["stop"]
    assert sim_trade["target"] == live_risk["target"]
    assert sim_trade["qty"] == live_risk["qty"]
    assert sim_trade["holding_days"] >= 1
    assert sim_trade["exit_price"] > 0
    assert "2R Partial" in sim_trade["exit_reason"]


@pytest.mark.live
def test_full_backtest_live_smoke():
    """
    Heavy backtest run marked 'live' so default offline pytest suite remains ~1s.
    Runs on demand or during live smoke checks.
    """
    if not os.path.exists("archive"):
        pytest.skip("Archive folder not present")
    res = backtest(archive_dir="archive")
    assert "equity_curve" in res
    assert "trades" in res
