"""
Midcap Swing Scanner - Trade Exit & Holding Period Evaluator (Version 2)
Implements quantitative swing exit rules:
1. Stop Loss breach (with gap-down open fill protection)
2. +2R Profit Target hit (50% partial exit, ratcheting stop to breakeven)
3. Breakeven ratchet when high reaches +8% gain
4. 20-EMA trailing stop on runner after +2R target
5. Strict 20-Trading-Session Maximum Holding Period time stop
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any
import pandas as pd
from core.config import (
    MAX_HOLDING_SESSIONS,
    BREAKEVEN_TRIGGER_GAIN_PCT,
)


@dataclass(frozen=True)
class ExitEvent:
    action: str  # "STOP_LOSS", "PARTIAL_TARGET", "TARGET_FULL", "TRAIL_EXIT", "TIME_STOP"
    exit_price: float
    qty: int
    reason: str
    holding_sessions: int

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action,
            "exit_price": round(self.exit_price, 2),
            "qty": int(self.qty),
            "reason": self.reason,
            "holding_sessions": self.holding_sessions,
        }


def evaluate_position_exit(
    position: Dict[str, Any],
    current_bar: pd.Series,
    holding_sessions: int,
    max_holding_sessions: int = MAX_HOLDING_SESSIONS,
) -> Optional[ExitEvent]:
    """
    Evaluate open position against current completed daily candle.

    Order of evaluation:
    1. Check Stop Loss breach
    2. Check +2R Profit Target (50% partial exit)
    3. Ratchet Stop to breakeven if price achieved +8% gain
    4. Check 20-EMA trailing stop on runner (if partial was taken)
    5. Check 20-trading-session maximum holding period time stop
    """
    open_p = float(current_bar["Open"])
    high_p = float(current_bar["High"])
    low_p = float(current_bar["Low"])
    close_p = float(current_bar["Close"])

    ema20_val = current_bar.get("EMA20")
    ema20 = float(ema20_val) if ema20_val is not None and not pd.isna(ema20_val) else None

    entry_price = float(position["entry_price"])
    current_stop = float(position["current_stop"])
    target = float(position["target"])
    remaining_qty = int(position.get("remaining_qty", position.get("qty", 1)))
    partial_taken = bool(position.get("partial_taken", False))

    # Track highest price achieved during hold
    highest_price = max(float(position.get("highest_price", entry_price)), high_p)
    position["highest_price"] = highest_price

    # 1. Stop Loss breach check
    if low_p <= current_stop:
        # Gap-down fill protection: if opened below stop, exit at open
        exit_price = min(open_p, current_stop) if open_p < current_stop else current_stop
        return ExitEvent(
            action="STOP_LOSS",
            exit_price=round(exit_price, 2),
            qty=remaining_qty,
            reason="Stop Loss Hit",
            holding_sessions=holding_sessions,
        )

    # 2. +2R Profit Target check
    if not partial_taken and high_p >= target:
        exit_price = target
        initial_qty = int(position["qty"])
        partial_qty = initial_qty // 2

        if partial_qty <= 0 or remaining_qty <= 1 or initial_qty <= 1:
            return ExitEvent(
                action="TARGET_FULL",
                exit_price=round(exit_price, 2),
                qty=remaining_qty,
                reason="2R Target Reached (Full Exit)",
                holding_sessions=holding_sessions,
            )
        else:
            # Update position state for runner
            position["partial_taken"] = True
            position["partial_qty"] = partial_qty
            position["remaining_qty"] = remaining_qty - partial_qty
            position["current_stop"] = max(current_stop, entry_price)  # Ratchet stop to breakeven
            return ExitEvent(
                action="PARTIAL_TARGET",
                exit_price=round(exit_price, 2),
                qty=partial_qty,
                reason="2R Target Reached (50% Partial Taken)",
                holding_sessions=holding_sessions,
            )

    # 3. Breakeven ratchet: move stop to entry if price reached +8% gain
    if highest_price >= entry_price * (1.0 + BREAKEVEN_TRIGGER_GAIN_PCT):
        current_stop = max(current_stop, entry_price)
        position["current_stop"] = current_stop

    # 4. Trailing stop on runner with 20-EMA (when partial has been booked)
    if partial_taken and ema20 is not None:
        if close_p < ema20:
            return ExitEvent(
                action="TRAIL_EXIT",
                exit_price=round(close_p, 2),
                qty=remaining_qty,
                reason="20-EMA Trail Exit",
                holding_sessions=holding_sessions,
            )

    # 5. Strict 20-Trading-Session Maximum Holding Period Time Stop
    if holding_sessions >= max_holding_sessions:
        return ExitEvent(
            action="TIME_STOP",
            exit_price=round(close_p, 2),
            qty=remaining_qty,
            reason=f"Time Stop ({max_holding_sessions} Sessions Max Hold Reached)",
            holding_sessions=holding_sessions,
        )

    return None
