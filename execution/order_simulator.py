"""
Midcap Swing Scanner - Realistic Next-Day Order Execution Simulator (Version 2)
Implements execution realism:
- Evaluates signals confirmed on Day t Close strictly on Day t+1
- Simulated Buy GTT Stop-Limits (Trigger = Pivot, Anti-Chase Limit = Trigger * 1.015)
- Fills at max(Open, Trigger) + slippage if Day t+1 High >= Trigger
- Anti-chase protection: voids entry if Day t+1 Open > Anti-Chase Limit
- Indian equity broker friction modeling (STT, exchange fees, SEBI, GST, stamp duty, slippage)
"""

from dataclasses import dataclass
from typing import Optional
import pandas as pd
from strategies.base import CandidateSignal


@dataclass(frozen=True)
class FillResult:
    filled: bool
    fill_price: float
    fill_date: str
    qty: int
    friction_cost: float
    reason: str


def compute_broker_friction(
    buy_turnover: float,
    sell_turnover: float,
    flat_brokerage_per_order: float = 20.0,
) -> float:
    """
    Calculate realistic Indian delivery equity trading friction:
    - STT (Securities Transaction Tax): 0.1% on both Buy and Sell delivery
    - Exchange Transaction Charges (NSE): 0.00345% of turnover
    - SEBI Turnover Charges: 0.0001% of turnover
    - Stamp Duty (Buy only): 0.015% of buy turnover
    - GST: 18% on (Brokerage + Exchange Charges + SEBI Charges)
    - Flat Brokerage: ₹20 per executed order leg (Discount broker rate)
    """
    total_turnover = buy_turnover + sell_turnover
    stt = 0.001 * total_turnover
    exchange_charges = 0.0000345 * total_turnover
    sebi_charges = 0.000001 * total_turnover
    stamp_duty = 0.00015 * buy_turnover

    total_brokerage = flat_brokerage_per_order * 2.0  # Buy + Sell
    gst = 0.18 * (total_brokerage + exchange_charges + sebi_charges)

    total_friction = stt + exchange_charges + sebi_charges + stamp_duty + total_brokerage + gst
    return round(total_friction, 2)


def simulate_order_fill(
    candidate: CandidateSignal,
    next_day_bar: pd.Series,
    slippage_pct: float = 0.0005,  # 5 bps standard institutional slippage
) -> FillResult:
    """
    Simulate execution on Day t+1 given candidate signal generated on Day t.

    Rules:
    1. If Day t+1 Open > Anti-Chase Limit -> CANCELLED_GAP_EXCEEDED (avoids buying peak gaps)
    2. If Day t+1 High >= Trigger Price -> FILLED at max(Open, Trigger) * (1 + slippage)
    3. If Day t+1 High < Trigger Price -> UNTRIGGERED (price never reached breakout pivot)
    """
    open_p = float(next_day_bar["Open"])
    high_p = float(next_day_bar["High"])
    low_p = float(next_day_bar["Low"])
    close_p = float(next_day_bar["Close"])
    bar_date = pd.to_datetime(next_day_bar["Date"]).strftime("%Y-%m-%d")

    # Anti-chase gap rule
    if open_p > candidate.anti_chase_limit:
        return FillResult(
            filled=False,
            fill_price=0.0,
            fill_date=bar_date,
            qty=0,
            friction_cost=0.0,
            reason="CANCELLED_GAP_EXCEEDED",
        )

    # Trigger check
    if candidate.order_type == "BUY_GTT_STOP_LIMIT":
        if high_p >= candidate.trigger_price:
            # Filled at Open if opened between Trigger and Anti-Chase, else filled at Trigger
            raw_fill = max(open_p, candidate.trigger_price)
            fill_price = round(raw_fill * (1.0 + slippage_pct), 2)
            buy_turnover = fill_price * candidate.qty
            entry_friction = compute_broker_friction(buy_turnover, 0.0, flat_brokerage_per_order=20.0)

            return FillResult(
                filled=True,
                fill_price=fill_price,
                fill_date=bar_date,
                qty=candidate.qty,
                friction_cost=entry_friction,
                reason="FILLED_AT_TRIGGER",
            )
        else:
            return FillResult(
                filled=False,
                fill_price=0.0,
                fill_date=bar_date,
                qty=0,
                friction_cost=0.0,
                reason="UNTRIGGERED_HIGH_BELOW_PIVOT",
            )

    elif candidate.order_type == "BUY_MARKET_OPEN":
        if open_p > candidate.close * 1.02:  # 2% gap ceiling for market orders
            return FillResult(
                filled=False,
                fill_price=0.0,
                fill_date=bar_date,
                qty=0,
                friction_cost=0.0,
                reason="CANCELLED_GAP_EXCEEDED",
            )
        fill_price = round(open_p * (1.0 + slippage_pct), 2)
        buy_turnover = fill_price * candidate.qty
        entry_friction = compute_broker_friction(buy_turnover, 0.0, flat_brokerage_per_order=20.0)

        return FillResult(
            filled=True,
            fill_price=fill_price,
            fill_date=bar_date,
            qty=candidate.qty,
            friction_cost=entry_friction,
            reason="FILLED_AT_OPEN",
        )

    return FillResult(
        filled=False,
        fill_price=0.0,
        fill_date=bar_date,
        qty=0,
        friction_cost=0.0,
        reason="UNRECOGNIZED_ORDER_TYPE",
    )
