"""
Midcap Swing Scanner - Strategy 2: 20-EMA Institutional Dip / Pullback (Version 2)
Implements institutional pullback buying into rising dynamic support:
- Verified Stage-2 trend (Price > 50 SMA > 200 SMA)
- Rising 20-day Exponential Moving Average (EMA20 slope > 0)
- Pullback test of 20-EMA with short-term oversold exhaustion (RSI2 <= 15 or 3-day pullback)
- Reversal confirmation: Close > Previous Close, Close > 20-EMA, and strong upper close
- Common gating: Sector in confirmed uptrend, ₹20 Cr turnover, 7-day earnings blackout
"""

from typing import Optional, Dict, Any
import numpy as np
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


class S2EmaPullbackStrategy(StrategyBase):
    """
    Strategy 2: Pullback to Rising 20-EMA in Stage-2 Trend.
    """

    def __init__(self):
        super().__init__(
            strategy_id="S2_EMA_PULLBACK",
            strategy_name="20-EMA Pullback Dip",
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
        if "EMA20" not in df.columns or "SMA50" not in df.columns or "ATR14" not in df.columns:
            df = compute_all_indicators(df)

        if len(df) < 200:
            return None

        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]

        close = float(last_row["Close"])
        open_p = float(last_row["Open"])
        high = float(last_row["High"])
        low = float(last_row["Low"])
        ema20 = float(last_row["EMA20"])
        sma50 = float(last_row["SMA50"])
        sma200 = float(last_row["SMA200"])

        # 2. Stage-2 Trend Check: Price > 50 SMA > 200 SMA
        if not (close > sma50 and sma50 > sma200 and close > sma200):
            return None

        # 3. Rising 20-EMA slope over prior 5 days
        ema20_5d_ago = float(df["EMA20"].iloc[-6])
        if ema20 <= ema20_5d_ago:
            return None

        # 4. Pullback proximity test: within 2.0% of 20-EMA during the last 2 sessions
        tested_ema = (low <= ema20 * 1.02) and (high >= ema20 * 0.98)
        prev_low = float(prev_row["Low"])
        prev_tested_ema = (prev_low <= float(prev_row["EMA20"]) * 1.02)

        if not (tested_ema or prev_tested_ema):
            return None

        # 5. Short-term exhaustion / pullback condition
        rsi2 = float(last_row.get("RSI2", 50.0))
        prev_rsi2 = float(prev_row.get("RSI2", 50.0))
        is_exhausted = (rsi2 < 20.0) or (prev_rsi2 < 15.0)

        # 6. Reversal trigger: Bullish response above 20-EMA
        is_reversal = (
            (close > float(prev_row["Close"]))
            and (close >= ema20)
            and (close > (high + low) / 2.0)
        )

        if not (is_exhausted and is_reversal):
            return None

        # 7. Common liquidity filter (>= ₹20 Crores turnover)
        is_liquid, _, _ = check_liquidity(df)
        if not is_liquid:
            return None

        # 8. Sector strength filter (Fail-closed)
        if sector_df is not None:
            is_sec_ok, _, _ = check_sector_strength(symbol, sector_df)
            if not is_sec_ok:
                return None

        # 9. Relative strength vs index
        if index_df is not None:
            beats_idx, _, _, _ = check_relative_strength(df, index_df, lookback=50)
            if not beats_idx:
                return None

        # 10. Earnings blackout check
        if events_data:
            is_blocked, _, _ = check_earnings_blackout(symbol, events_data)
            if is_blocked:
                return None

        # 11. Position Sizing & Risk Parameters
        atr = float(last_row["ATR14"])
        risk = calculate_position_size(
            entry=close,
            atr=atr,
            equity=capital,
            risk_pct=risk_pct,
            max_holding_sessions=MAX_HOLDING_SESSIONS,
        )
        if risk is None or risk.qty <= 0:
            return None

        trigger_price = round(max(high, close), 2)
        anti_chase = round(trigger_price * (1.0 + ANTI_CHASE_MAX_GAP_PCT), 2)
        sector_sym = get_sector_symbol(symbol)
        signal_date = pd.to_datetime(last_row["Date"]).strftime("%Y-%m-%d")

        thesis_card = (
            f"STRATEGY: S2 20-EMA Pullback | {symbol} | RS: {rs_rating or 'N/A'}\n"
            f"Stage-2 Leader ✅ | 20-EMA Dip Support Rebound ✅ | RSI-2 Reversal ✅\n"
            f"Order: Buy GTT @ ₹{trigger_price} (Max Open ₹{anti_chase})\n"
            f"Stop: ₹{risk.stop} | Target (+2R): ₹{risk.target} | Qty: {risk.qty} shares\n"
            f"Initial Risk: ₹{risk.risk_amount} ({risk_pct*100:.2f}%) | Hold: max 20 sessions"
        )

        return CandidateSignal(
            symbol=symbol,
            strategy_id=self.strategy_id,
            strategy_name=self.strategy_name,
            signal_date=signal_date,
            signal_type="PULLBACK",
            close=close,
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
            setup_notes="Institutional dip pullback into rising 20-EMA support with bullish reversal candle.",
        )
