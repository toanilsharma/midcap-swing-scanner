"""
Unit tests for Version 2 Backtest Engine & Execution Realism:
- Next-Day Order Execution Simulation
- 20-Trading-Session Maximum Holding Period Time Stop
- Multi-Strategy Performance Separation (S1, S2, S3)
- Broker Friction & Slippage Accounting
"""

import datetime
import numpy as np
import pandas as pd
import pytest

from backtest import backtest
from execution.order_simulator import simulate_order_fill, compute_broker_friction, FillResult
from execution.exit_evaluator import evaluate_position_exit, ExitEvent
from strategies.base import CandidateSignal


def test_order_simulator_anti_chase_gap_void():
    """
    Verify that an opening gap exceeding anti_chase_limit (+1.5%) voids the trade.
    """
    candidate = CandidateSignal(
        symbol="GAPPER.NS",
        strategy_id="S1_VCP_BREAKOUT",
        strategy_name="Stage-2 VCP Breakout",
        signal_date="2026-11-20",
        signal_type="BREAKOUT",
        close=100.0,
        entry=100.0,
        stop=93.0,
        target=114.0,
        qty=10,
        risk_per_unit=7.0,
        risk_amount=70.0,
        r_multiple=2.0,
        allocation_amount=1000.0,
        allocation_pct=1.0,
        order_type="BUY_GTT_STOP_LIMIT",
        trigger_price=100.0,
        anti_chase_limit=101.50,  # +1.5% max gap
        max_holding_sessions=20,
        atr=5.0,
        rsi=65.0,
        rs_rating=85,
        sector="^CNXIT",
        thesis_card="",
        setup_notes="",
    )

    # Day t+1 opens at 102.50 (2.5% gap > 1.5% limit) -> MUST VOID
    gap_bar = pd.Series({
        "Date": "2026-11-21",
        "Open": 102.50,
        "High": 105.0,
        "Low": 102.0,
        "Close": 104.0,
    })

    fill = simulate_order_fill(candidate, gap_bar)
    assert not fill.filled
    assert fill.reason == "CANCELLED_GAP_EXCEEDED"


def test_order_simulator_valid_trigger_fill():
    """
    Verify that Day t+1 High >= Trigger fills at Trigger (or Open if between Trigger and Limit).
    """
    candidate = CandidateSignal(
        symbol="VALID.NS",
        strategy_id="S1_VCP_BREAKOUT",
        strategy_name="Stage-2 VCP Breakout",
        signal_date="2026-11-20",
        signal_type="BREAKOUT",
        close=100.0,
        entry=100.0,
        stop=93.0,
        target=114.0,
        qty=10,
        risk_per_unit=7.0,
        risk_amount=70.0,
        r_multiple=2.0,
        allocation_amount=1000.0,
        allocation_pct=1.0,
        order_type="BUY_GTT_STOP_LIMIT",
        trigger_price=100.0,
        anti_chase_limit=101.50,
        max_holding_sessions=20,
        atr=5.0,
        rsi=65.0,
        rs_rating=85,
        sector="^CNXIT",
        thesis_card="",
        setup_notes="",
    )

    # Day t+1 opens at 99.50 and reaches 102.0 -> Fills at trigger 100.0 + slippage
    normal_bar = pd.Series({
        "Date": "2026-11-21",
        "Open": 99.50,
        "High": 102.0,
        "Low": 99.0,
        "Close": 101.0,
    })

    fill = simulate_order_fill(candidate, normal_bar, slippage_pct=0.0005)
    assert fill.filled
    assert fill.fill_price == 100.05  # 100.0 + 5 bps slippage
    assert fill.qty == 10
    assert fill.reason == "FILLED_AT_TRIGGER"
    assert fill.friction_cost > 0.0


def test_exit_evaluator_20_session_time_stop():
    """
    Verify that an open trade holding for 20 sessions without hitting stop or target
    exits cleanly with TIME_STOP.
    """
    position = {
        "symbol": "STAGNANT.NS",
        "entry_price": 100.0,
        "current_stop": 93.0,
        "target": 114.0,
        "qty": 10,
        "remaining_qty": 10,
        "partial_taken": False,
        "highest_price": 102.0,
    }

    current_bar = pd.Series({
        "Date": "2026-12-18",
        "Open": 101.0,
        "High": 102.0,
        "Low": 100.0,
        "Close": 101.5,
        "EMA20": 99.0,
    })

    # At holding_sessions = 19: No exit
    exit_19 = evaluate_position_exit(position, current_bar, holding_sessions=19, max_holding_sessions=20)
    assert exit_19 is None

    # At holding_sessions = 20: Time stop triggers
    exit_20 = evaluate_position_exit(position, current_bar, holding_sessions=20, max_holding_sessions=20)
    assert exit_20 is not None
    assert exit_20.action == "TIME_STOP"
    assert exit_20.exit_price == 101.5
    assert exit_20.qty == 10
    assert "20 Sessions Max Hold" in exit_20.reason


def test_exit_evaluator_2r_partial_and_runner_trail():
    """
    Verify 50% partial exit at +2R followed by 20-EMA trail exit on runner.
    """
    position = {
        "symbol": "RUNNER.NS",
        "entry_price": 100.0,
        "current_stop": 93.0,
        "target": 114.0,
        "qty": 10,
        "remaining_qty": 10,
        "partial_taken": False,
        "highest_price": 100.0,
    }

    # Day 1: Bar touches target 114.0 -> Takes 50% partial (5 shares)
    bar_target = pd.Series({
        "Date": "2026-11-22",
        "Open": 110.0,
        "High": 115.0,
        "Low": 109.0,
        "Close": 113.0,
        "EMA20": 105.0,
    })
    ev1 = evaluate_position_exit(position, bar_target, holding_sessions=3)
    assert ev1 is not None
    assert ev1.action == "PARTIAL_TARGET"
    assert ev1.qty == 5
    assert position["partial_taken"] is True
    assert position["remaining_qty"] == 5
    assert position["current_stop"] == 100.0  # Stop ratcheted to breakeven!

    # Day 2: Runner closes below 20-EMA (e.g. Close = 104.0 < EMA20 = 105.0) -> Trailing exit
    bar_trail = pd.Series({
        "Date": "2026-11-23",
        "Open": 106.0,
        "High": 107.0,
        "Low": 103.0,
        "Close": 104.0,
        "EMA20": 105.0,
    })
    ev2 = evaluate_position_exit(position, bar_trail, holding_sessions=4)
    assert ev2 is not None
    assert ev2.action == "TRAIL_EXIT"
    assert ev2.qty == 5
    assert ev2.exit_price == 104.0


def test_broker_friction_accounting():
    """
    Verify calculation of Indian equity delivery trading friction.
    """
    buy_turnover = 25000.0  # ₹25,000 buy
    sell_turnover = 28000.0  # ₹28,000 sell
    friction = compute_broker_friction(buy_turnover, sell_turnover)

    # STT = 0.1% of (25k + 28k) = ₹53
    # Brokerage = ₹40 + GST
    # Total friction should be ~₹100 - ₹120
    assert 90.0 <= friction <= 130.0
