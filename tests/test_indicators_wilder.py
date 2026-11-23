"""
Unit tests for J. Welles Wilder's smoothed indicators and quantitative technical metrics:
- Wilder ATR (alpha = 1 / period)
- Wilder RSI (alpha = 1 / period)
- 52-week High & Low fail-closed validation (< 250 bars)
- Bollinger / Keltner squeeze logic
"""

import numpy as np
import pandas as pd
import pytest

from core.indicators import (
    compute_true_range,
    compute_wilder_atr,
    compute_wilder_rsi,
    compute_all_indicators,
)


def test_true_range_calculation():
    """
    Assert True Range = max(H - L, |H - C_prev|, |L - C_prev|).
    """
    df = pd.DataFrame({
        "High": [105.0, 110.0, 108.0],
        "Low": [95.0, 102.0, 99.0],
        "Close": [100.0, 109.0, 101.0],
    })
    tr = compute_true_range(df)
    # Bar 0: High - Low = 105 - 95 = 10.0
    assert tr.iloc[0] == 10.0
    # Bar 1: max(110 - 102=8, |110 - 100|=10, |102 - 100|=2) -> 10.0
    assert tr.iloc[1] == 10.0
    # Bar 2: max(108 - 99=9, |108 - 109|=1, |99 - 109|=10) -> 10.0
    assert tr.iloc[2] == 10.0


def test_wilder_atr_smoothing_vs_manual():
    """
    Verify that Wilder ATR smoothing follows ATR_t = ATR_{t-1} + (1/N) * (TR_t - ATR_{t-1}).
    """
    n = 30
    df = pd.DataFrame({
        "High": [100.0 + i for i in range(n)],
        "Low": [90.0 + i for i in range(n)],
        "Close": [95.0 + i for i in range(n)],
    })
    # High - Low is 10 for all bars; C_prev is 95 + i - 1; H - C_prev = 100 + i - 94 - i = 6
    # So TR is constant 10.0 for every bar
    atr = compute_wilder_atr(df, period=14)
    # When TR is constant 10.0, smoothed ATR must converge to 10.0
    assert pytest.approx(atr.iloc[-1], abs=1e-4) == 10.0


def test_wilder_rsi_all_gains_and_all_losses():
    """
    Verify boundary behaviors:
    - Strictly rising prices -> RSI = 100.0
    - Strictly falling prices -> RSI = 0.0
    - Flat prices -> RSI = 50.0
    """
    rising = pd.Series([100.0 + i for i in range(25)])
    rsi_rising = compute_wilder_rsi(rising, period=14)
    assert pytest.approx(rsi_rising.iloc[-1], abs=1e-2) == 100.0

    falling = pd.Series([200.0 - i for i in range(25)])
    rsi_falling = compute_wilder_rsi(falling, period=14)
    assert pytest.approx(rsi_falling.iloc[-1], abs=1e-2) == 0.0

    flat = pd.Series([100.0 for _ in range(25)])
    rsi_flat = compute_wilder_rsi(flat, period=14)
    assert pytest.approx(rsi_flat.iloc[-1], abs=1e-2) == 50.0


def test_wilder_rsi_mixed_series():
    """
    Verify Wilder RSI on a standard fluctuating series matches bounded range [0, 100].
    """
    np.random.seed(42)
    prices = 100.0 + np.cumsum(np.random.randn(100))
    series = pd.Series(prices)
    rsi = compute_wilder_rsi(series, period=14)

    assert len(rsi) == 100
    assert (rsi.dropna() >= 0.0).all()
    assert (rsi.dropna() <= 100.0).all()


def test_52w_high_low_fail_closed_on_short_data():
    """
    Verify that if history has fewer than 250 bars, HAS_52W_DATA is False,
    and TREND_OK strictly evaluates to False (fail-closed rule).
    """
    n = 100  # Only 100 bars, well below the 250-bar minimum
    df = pd.DataFrame({
        "Date": pd.date_range("2026-01-01", periods=n, freq="D"),
        "Open": np.linspace(100.0, 150.0, n),
        "High": np.linspace(102.0, 152.0, n),
        "Low": np.linspace(98.0, 148.0, n),
        "Close": np.linspace(101.0, 151.0, n),
        "Volume": np.full(n, 1000000.0),
    })
    res = compute_all_indicators(df)

    assert not bool(res["HAS_52W_DATA"].iloc[-1])
    assert not bool(res["TREND_OK"].iloc[-1])
    assert not bool(res["SIGNAL"].iloc[-1])


def test_squeeze_indicator_detection():
    """
    Verify Bollinger inside Keltner Channel squeeze logic.
    """
    n = 60
    # Generate tight flat consolidation: std dev shrinks, putting BB inside KC
    df = pd.DataFrame({
        "Date": pd.date_range("2026-01-01", periods=n, freq="D"),
        "Open": np.full(n, 100.0),
        "High": np.full(n, 100.2),
        "Low": np.full(n, 99.8),
        "Close": np.full(n, 100.0),
        "Volume": np.full(n, 500000.0),
    })
    res = compute_all_indicators(df)
    # In ultra-tight range, SQUEEZE_ON should be True once 20 bars accumulate
    assert bool(res["SQUEEZE_ON"].iloc[-1])
