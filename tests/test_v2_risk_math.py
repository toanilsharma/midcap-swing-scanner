"""
Unit tests for Version 2 Risk Management & Position Sizing Engine:
- ₹1,00,000 Starting Capital
- 0.75% Equity Risk per Trade (₹750 Risk Budget)
- 1.5x ATR Stop Multiplier
- 7% Hard Stop Loss Floor Cap
- 25% Maximum Single-Position Capital Allocation Cap
- +2R Target Multiple & 20-Session Max Holding Period
"""

import pytest
from core.risk_engine import calculate_position_size, RiskParameters


def test_standard_sizing_at_075_pct_risk():
    """
    Scenario:
    Capital = ₹1,00,000, Risk = 0.75% -> Risk budget = ₹750.
    Entry = ₹1,000.0, ATR = ₹20.0
    Stop = 1000 - (1.5 * 20) = ₹970.0 (3% risk, within 7% floor)
    Risk per unit = ₹30.0
    Qty = floor(750 / 30) = 25 shares
    Total position cost = 25 * 1000 = ₹25,000 (exactly at 25% allocation cap)
    Total risk amount = 25 * 30 = ₹750.0
    Target (+2R) = 1000 + (2 * 30) = ₹1,060.0
    """
    risk = calculate_position_size(entry=1000.0, atr=20.0, equity=100000.0, risk_pct=0.0075)

    assert risk is not None
    assert risk.entry == 1000.0
    assert risk.stop == 970.0
    assert risk.risk_per_unit == 30.0
    assert risk.qty == 25
    assert risk.risk_amount == 750.0
    assert risk.target == 1060.0
    assert risk.allocation_amount == 25000.0
    assert risk.allocation_pct == 25.0
    assert risk.max_holding_sessions == 20
    assert risk.r_multiple == 2.0


def test_7pct_stop_loss_floor_cap_binds():
    """
    Scenario:
    Entry = ₹1,000.0, ATR = ₹60.0 (High Volatility)
    Raw ATR Stop = 1000 - (1.5 * 60) = 910.0 (9% loss)
    Hard Floor Cap = 1000 * 0.93 = ₹930.0 (7% loss)
    Effective Stop must bind at ₹930.0.
    Risk per unit = 1000 - 930 = ₹70.0
    Qty = floor(750 / 70) = 10 shares
    Risk amount = 10 * 70 = ₹700.0
    Target (+2R) = 1000 + (2 * 70) = ₹1,140.0
    """
    risk = calculate_position_size(entry=1000.0, atr=60.0, equity=100000.0, risk_pct=0.0075)

    assert risk is not None
    assert risk.stop == 930.0
    assert risk.risk_per_unit == 70.0
    assert risk.qty == 10
    assert risk.risk_amount == 700.0
    assert risk.target == 1140.0


def test_25pct_single_position_allocation_cap_binds():
    """
    Scenario:
    Entry = ₹1,000.0, ATR = ₹5.0 (Ultra-tight volatility)
    Raw Stop = 1000 - (1.5 * 5) = ₹992.5
    Risk per unit = ₹7.50
    Raw Qty = floor(750 / 7.50) = 100 shares -> Cost = ₹100,000 (100% of portfolio!)
    Allocation Cap = floor(100,000 * 0.25 / 1000) = 25 shares.
    Final Qty MUST cap at 25 shares (₹25,000 allocation), never 100 shares.
    """
    risk = calculate_position_size(entry=1000.0, atr=5.0, equity=100000.0, risk_pct=0.0075)

    assert risk is not None
    assert risk.qty == 25
    assert risk.allocation_amount == 25000.0
    assert risk.allocation_pct == 25.0
    # Risk taken is now less than ₹750 because position was capped at 25% capital
    assert risk.risk_amount == 25 * 7.50


def test_invalid_and_zero_inputs_fail_closed():
    """
    Verify that non-positive inputs return None.
    """
    # Negative entry
    assert calculate_position_size(entry=-100.0, atr=10.0) is None
    # Zero entry
    assert calculate_position_size(entry=0.0, atr=10.0) is None
    # Zero ATR
    assert calculate_position_size(entry=500.0, atr=0.0) is None
    # Zero Capital
    assert calculate_position_size(entry=500.0, atr=10.0, equity=0.0) is None
    # Zero Risk Pct
    assert calculate_position_size(entry=500.0, atr=10.0, risk_pct=0.0) is None
    # Stock too expensive for risk budget (e.g. MRF at ₹1,50,000 when capital is ₹1,00,000)
    assert calculate_position_size(entry=150000.0, atr=1000.0, equity=100000.0) is None
