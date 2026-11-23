"""
Midcap Swing Scanner - Strategy 1: Stage-2 VCP / Consolidation Breakout (Version 2)
Implements Mark Minervini's Volatility Contraction Pattern (VCP) breakout:
- Confirmed Stage-2 trend (Price > 50 SMA > 150 SMA > 200 SMA, 200-SMA rising)
- Volatility contraction and volume dry-up inside consolidation base
- Breakout above 20-day high on 1.5x volume expansion with strong candle close
- Common gating: Sector in confirmed uptrend, 20 Cr liquidity, 7-day earnings blackout
"""

from typing import Optional, Dict, Any
import pandas as pd

from core.config import (
    CAPITAL,
    RISK_PCT,
    ANTI_CHASE_MAX_GAP_PCT,
    MAX_HOLDING_SESSIONS,
)
from core.indicators import compute_all_indicators
from core.filters import (
    check_sector_strength,
    check_liquidity,
    check_relative_strength,
    check_earnings_blackout,
    get_sector_symbol,
)
from core.risk_engine import calculate_position_size
from strategies.base import StrategyBase, CandidateSignal


class S1VcpBreakoutStrategy(StrategyBase):
    """
    Strategy 1: Stage-2 Volatility Contraction Pattern (VCP) Breakout.
    """

    def __init__(self):
        super().__init__(
            strategy_id="S1_VCP_BREAKOUT",
            strategy_name="Stage-2 VCP Breakout",
        )

    def evaluate(
        self,
        df: pd.DataFrame,
        symbol: str,
        sector_df: Optional[pd.DataFrame] = None,
        index_df: Optional[pd.DataFrame] = None,
        events_data: Optional[Dict[str, Any]] = None,
        rs_rating: Optional[int] = None,
        capital: float = CAPITAL,
        risk_pct: float = RISK_PCT,
    ) -> Optional[CandidateSignal]:
        if df is None or len(df) < 50:
            return None

        # 1. Ensure indicators are computed
        if "SIGNAL" not in df.columns or "ATR14" not in df.columns:
            df = compute_all_indicators(df)

        last_row = df.iloc[-1]

        # 2. Setup trigger check: Must have completed breakout signal
        is_breakout = bool(last_row.get("SIGNAL", False))
        if not is_breakout:
            return None

        # 3. Liquidity filter (Fail-closed >= ₹20 Crores turnover)
        is_liquid, avg_to, _ = check_liquidity(df)
        if not is_liquid:
            return None

        # 4. Sector Strength filter (Fail-closed)
        if sector_df is not None:
            is_sec_ok, _, _ = check_sector_strength(symbol, sector_df)
            if not is_sec_ok:
                return None

        # 5. Relative Strength vs Index (Stock return must beat Index return over 50 days)
        if index_df is not None:
            beats_idx, _, _, _ = check_relative_strength(df, index_df, lookback=50)
            if not beats_idx:
                return None

        # 6. Earnings Blackout filter (7-day buffer)
        if events_data:
            is_blocked, _, _ = check_earnings_blackout(symbol, events_data)
            if is_blocked:
                return None

        # 7. Position Sizing & Risk Math
        entry_price = float(last_row["Close"])
        atr = float(last_row["ATR14"])

        risk = calculate_position_size(
            entry=entry_price,
            atr=atr,
            equity=capital,
            risk_pct=risk_pct,
            max_holding_sessions=MAX_HOLDING_SESSIONS,
        )
        if risk is None or risk.qty <= 0:
            return None

        # 8. Execution order parameters
        trigger_price = round(max(float(last_row["High"]), entry_price), 2)
        anti_chase = round(trigger_price * (1.0 + ANTI_CHASE_MAX_GAP_PCT), 2)
        sector_sym = get_sector_symbol(symbol)
        signal_date = pd.to_datetime(last_row["Date"]).strftime("%Y-%m-%d")

        thesis_card = (
            f"STRATEGY: S1 VCP Breakout | {symbol} | RS: {rs_rating or 'N/A'}\n"
            f"Stage-2 Trend ✅ | Coiling/Squeeze ✅ | Volume Spike: >1.5x ✅\n"
            f"Order: Buy GTT @ ₹{trigger_price} (Max Open ₹{anti_chase})\n"
            f"Stop: ₹{risk.stop} | Target (+2R): ₹{risk.target} | Qty: {risk.qty} shares\n"
            f"Initial Risk: ₹{risk.risk_amount} ({risk_pct*100:.2f}%) | Hold: max 20 sessions"
        )

        return CandidateSignal(
            symbol=symbol,
            strategy_id=self.strategy_id,
            strategy_name=self.strategy_name,
            signal_date=signal_date,
            signal_type="BREAKOUT",
            close=entry_price,
            entry=trigger_price,
            stop=risk.stop,
            target=risk.target,
            qty=risk.qty,
            risk_per_unit=risk.risk_per_unit,
            risk_amount=risk.risk_amount,
            r_multiple=risk.r_multiple,
            allocation_amount=risk.allocation_amount,
            allocation_pct=risk.allocation_pct,
            order_type="BUY_GTT_STOP_LIMIT",
            trigger_price=trigger_price,
            anti_chase_limit=anti_chase,
            max_holding_sessions=risk.max_holding_sessions,
            atr=atr,
            rsi=float(last_row.get("RSI14", 50.0)),
            rs_rating=rs_rating,
            sector=sector_sym,
            thesis_card=thesis_card,
            setup_notes="Minervini Stage-2 VCP consolidation breakout on volume expansion.",
        )
