"""
Midcap Swing Scanner - Risk Management & Position Sizing Engine (Version 2)
Implements institutional swing-trading capital allocation:
- 0.75% equity risk per trade (initial risk budget: ₹750 on ₹1,00,000 capital)
- Position sizing: Qty = floor(Risk_Budget / Risk_Per_Unit)
- Structural stop loss at 1.5 * ATR14, capped at hard 7% floor
- Maximum single-position capital allocation cap (25% of account equity)
- Strict validation: rejects non-positive entry, atr, capital, or risk
"""

import math
from typing import Optional, Dict, Any
from dataclasses import dataclass, asdict
import pandas as pd

from core.config import (
    CAPITAL,
    RISK_PCT,
    INITIAL_RISK_BUDGET,
    MAX_POSITION_ALLOCATION_PCT,
    ATR_STOP_MULTIPLIER,
    TARGET_R_MULTIPLE,
    MAX_STOP_LOSS_PCT,
    MAX_HOLDING_SESSIONS,
)


@dataclass(frozen=True)
class RiskParameters:
    entry: float
    stop: float
    target: float
    qty: int
    risk_per_unit: float
    risk_amount: float
    allocation_amount: float
    allocation_pct: float
    risk_pct: float
    max_holding_sessions: int
    r_multiple: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def calculate_position_size(
    entry: float,
    atr: float,
    equity: float = CAPITAL,
    risk_pct: float = RISK_PCT,
    atr_multiplier: float = ATR_STOP_MULTIPLIER,
    target_multiple: float = TARGET_R_MULTIPLE,
    max_stop_pct: float = MAX_STOP_LOSS_PCT,
    max_position_allocation_pct: float = MAX_POSITION_ALLOCATION_PCT,
    max_holding_sessions: int = MAX_HOLDING_SESSIONS,
) -> Optional[RiskParameters]:
    """
    Calculate position quantity, stop loss, and target based on fixed-fractional equity risk.

    Formulas:
    1. Risk Budget = equity * risk_pct (e.g. ₹1,00,000 * 0.0075 = ₹750)
    2. Proposed Stop = entry - (atr_multiplier * atr)
    3. Floor Stop = entry * (1.0 - max_stop_pct) [7% maximum loss]
    4. Effective Stop = max(Proposed Stop, Floor Stop)
    5. Risk Per Unit = entry - Effective Stop
    6. Raw Quantity = floor(Risk Budget / Risk Per Unit)
    7. Allocation Cap = floor((equity * max_position_allocation_pct) / entry)
    8. Final Qty = min(Raw Quantity, Allocation Cap)

    Returns None if inputs are non-positive, resulting stop >= entry, or final qty <= 0.
    """
    # 1. Input sanitization
    if (
        pd.isna(entry)
        or pd.isna(atr)
        or entry <= 0.0
        or atr <= 0.0
        or equity <= 0.0
        or risk_pct <= 0.0
    ):
        return None

    # 2. Stop loss calculation with 7% ceiling cap
    raw_stop = entry - (atr_multiplier * atr)
    floor_stop = entry * (1.0 - max_stop_pct)
    stop = max(raw_stop, floor_stop)

    if stop >= entry:
        return None

    risk_per_unit = entry - stop
    if risk_per_unit <= 0.0:
        return None

    # 3. Position quantity sizing
    risk_budget = equity * risk_pct
    raw_qty = math.floor(risk_budget / risk_per_unit)
    if raw_qty <= 0:
        return None

    # 4. Maximum position allocation guardrail (e.g. 25% max in one stock)
    max_capital_allowed = equity * max_position_allocation_pct
    max_shares_allowed = math.floor(max_capital_allowed / entry)

    qty = min(raw_qty, max_shares_allowed)
    if qty <= 0:
        return None

    # 5. Financial metrics
    risk_amount = round(qty * risk_per_unit, 2)
    allocation_amount = round(qty * entry, 2)
    allocation_pct = round((allocation_amount / equity) * 100.0, 2)
    target = round(entry + (target_multiple * risk_per_unit), 2)

    return RiskParameters(
        entry=round(entry, 2),
        stop=round(stop, 2),
        target=target,
        qty=int(qty),
        risk_per_unit=round(risk_per_unit, 2),
        risk_amount=risk_amount,
        allocation_amount=allocation_amount,
        allocation_pct=allocation_pct,
        risk_pct=round(risk_pct * 100.0, 4),
        max_holding_sessions=max_holding_sessions,
        r_multiple=round(target_multiple, 1),
    )
