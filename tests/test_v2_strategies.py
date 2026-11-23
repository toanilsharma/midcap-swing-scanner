"""
Unit tests for Version 2 Decoupled Strategy Engines:
- Strategy 1 (S1): Stage-2 VCP Breakout
- Strategy 2 (S2): 20-EMA Institutional Dip / Pullback
- Strategy 3 (S3): High Relative Strength Momentum Leader Breakout
- Dashboard Schema Parity & Backward Compatibility
"""

import datetime
import numpy as np
import pandas as pd
import pytest

from strategies import (
    ALL_STRATEGIES,
    STRATEGY_REGISTRY,
    S1VcpBreakoutStrategy,
    S2EmaPullbackStrategy,
    S3RsMomentumStrategy,
)
from core.indicators import compute_all_indicators


def build_synthetic_vcp_dataframe() -> pd.DataFrame:
    """
    Generate deterministic 260-bar Stage-2 VCP consolidation breakout DataFrame.
    """
    n = 260
    dates = [datetime.date(2025, 1, 1) + datetime.timedelta(days=i) for i in range(n)]

    # Steady uptrend from 100 to 200 over 230 days
    base = np.linspace(100.0, 200.0, 230)
    plateau = np.full(20, 200.0)
    coiling = np.full(9, 201.0)
    # Day 259: breakout bar to 207.0
    close = np.concatenate([base, plateau, coiling, [207.0]])

    high = close + 1.0
    low = close - 1.0
    open_ = close.copy()
    vol = np.full(n, 1500000.0)

    # Prior 20-day high ceiling at 205.0 on day 242
    high[242] = 205.0

    # Coiling period (days 250-258): tight range and volume dryup (450,000)
    for j in range(250, 259):
        high[j] = close[j] + 0.15
        low[j] = close[j] - 0.15
        vol[j] = 450000.0

    # Breakout bar (index -1): close > 205, volume 2x, strong upper close
    close[-1] = 207.0
    high[-1] = 207.2
    low[-1] = 204.0
    open_[-1] = 205.0
    vol[-1] = 3500000.0

    df = pd.DataFrame({
        "Date": dates,
        "Open": open_,
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": vol,
    })
    return compute_all_indicators(df)


def test_strategy_suite_registry():
    """Verify strategy registry contains all three distinct strategy engines."""
    assert len(ALL_STRATEGIES) == 3
    assert "S1_VCP_BREAKOUT" in STRATEGY_REGISTRY
    assert "S2_EMA_PULLBACK" in STRATEGY_REGISTRY
    assert "S3_RS_MOMENTUM" in STRATEGY_REGISTRY


def test_s1_vcp_breakout_qualification_and_schema_parity():
    """
    Verify Strategy 1 (VCP Breakout) qualifies textbook pattern
    and produces 100% schema-compatible CandidateSignal dictionary.
    """
    df = build_synthetic_vcp_dataframe()
    s1 = S1VcpBreakoutStrategy()

    # Create dummy sector uptrend df
    sec_df = pd.DataFrame({
        "Close": [120.0] * 260,
        "SMA50": [110.0] * 260,
        "SMA200": [100.0] * 260,
    })

    sig = s1.evaluate(
        df=df,
        symbol="MANKIND.NS",
        sector_df=sec_df,
        rs_rating=85,
        capital=100000.0,
        risk_pct=0.0075,
    )

    assert sig is not None
    assert sig.strategy_id == "S1_VCP_BREAKOUT"
    assert sig.symbol == "MANKIND.NS"
    assert sig.qty > 0
    assert sig.target > sig.entry
    assert sig.stop < sig.entry
    assert sig.max_holding_sessions == 20

    # Test dictionary schema parity with Netlify dashboard
    d = sig.to_dict()
    required_legacy_keys = [
        "Signal Date", "Symbol", "Sector", "Type", "Close", "Entry", "Stop",
        "Target", "Qty", "Risk Per Unit", "Risk Amount", "ATR14", "RSI14",
        "rs_rating", "thesis_card",
    ]
    for key in required_legacy_keys:
        assert key in d, f"Missing dashboard legacy key: {key}"

    # Verify Version 2 extension keys
    assert d["strategy_id"] == "S1_VCP_BREAKOUT"
    assert d["order_type"] == "BUY_GTT_STOP_LIMIT"
    assert d["max_holding_sessions"] == 20
    assert d["trigger_price"] == sig.trigger_price


def test_s1_vcp_breakout_rejection_on_downtrend():
    """Verify Strategy 1 strictly rejects downtrending stock."""
    n = 260
    dates = [datetime.date(2025, 1, 1) + datetime.timedelta(days=i) for i in range(n)]
    close = np.linspace(200.0, 100.0, n)
    df = pd.DataFrame({
        "Date": dates,
        "Open": close + 0.2,
        "High": close + 1.0,
        "Low": close - 1.0,
        "Close": close,
        "Volume": np.full(n, 1000000.0),
    })
    df = compute_all_indicators(df)

    s1 = S1VcpBreakoutStrategy()
    sig = s1.evaluate(df=df, symbol="FALLING.NS")
    assert sig is None


def test_s2_ema_pullback_qualification():
    """
    Verify Strategy 2 (20-EMA Pullback Dip) qualifies bounce setup.
    """
    n = 260
    dates = [datetime.date(2025, 1, 1) + datetime.timedelta(days=i) for i in range(n)]
    # Stage 2 steady uptrend from 100 to 220
    close = np.linspace(100.0, 220.0, n)
    high = close + 1.0
    low = close - 1.0
    vol = np.full(n, 1000000.0)

    # Bar -2: Pullback touches 20-EMA, RSI drops
    # Bar -1: Bullish reversal candle above 20-EMA
    close[-2] = close[-3] - 2.0
    low[-2] = close[-2] - 1.0
    close[-1] = close[-2] + 3.0
    high[-1] = close[-1] + 0.5
    low[-1] = close[-2]

    df = pd.DataFrame({
        "Date": dates,
        "Open": close.copy(),
        "High": high,
        "Low": low,
        "Close": close,
        "Volume": vol,
    })
    df = compute_all_indicators(df)

    # Force short-term RSI2 dip to simulate exhaustion
    df.loc[df.index[-2], "RSI2"] = 12.0

    sec_df = pd.DataFrame({
        "Close": [120.0] * 260,
        "SMA50": [110.0] * 260,
        "SMA200": [100.0] * 260,
    })

    s2 = S2EmaPullbackStrategy()
    sig = s2.evaluate(
        df=df,
        symbol="DIPBUY.NS",
        sector_df=sec_df,
        rs_rating=75,
        capital=100000.0,
        risk_pct=0.0075,
    )

    assert sig is not None
    assert sig.strategy_id == "S2_EMA_PULLBACK"
    assert sig.signal_type == "PULLBACK"
    assert sig.qty > 0


def test_s3_rs_momentum_qualification():
    """
    Verify Strategy 3 (High-RS Momentum Leader) qualifies top leader breaking out.
    """
    df = build_synthetic_vcp_dataframe()
    s3 = S3RsMomentumStrategy()

    sec_df = pd.DataFrame({
        "Close": [120.0] * 260,
        "SMA50": [110.0] * 260,
        "SMA200": [100.0] * 260,
    })

    # RS Rating 92 (top decile leader)
    sig = s3.evaluate(
        df=df,
        symbol="LEADER.NS",
        sector_df=sec_df,
        rs_rating=92,
        capital=100000.0,
        risk_pct=0.0075,
    )

    assert sig is not None
    assert sig.strategy_id == "S3_RS_MOMENTUM"
    assert sig.signal_type == "MOMENTUM"
    assert sig.qty > 0
    assert "RS: 92" in sig.thesis_card


def test_s3_rs_momentum_rejection_on_low_rs():
    """
    Verify Strategy 3 strictly rejects stocks with low RS rating (<80).
    """
    df = build_synthetic_vcp_dataframe()
    s3 = S3RsMomentumStrategy()

    # RS Rating 60 (not a leader)
    sig = s3.evaluate(
        df=df,
        symbol="LAGGARD.NS",
        rs_rating=60,
        capital=100000.0,
        risk_pct=0.0075,
    )
    assert sig is None
