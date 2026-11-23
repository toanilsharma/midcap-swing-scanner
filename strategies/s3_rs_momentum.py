"""
Midcap Swing Scanner - Strategy 3: High Relative Strength (RS) Momentum Leader Breakout (Version 2)
Implements institutional momentum leadership trading:
- Top-decile relative strength leaders (RS Rating >= 80 or outperforming index by >15%)
- Strong Stage-2 trend (Price > 50 SMA > 200 SMA, 50 SMA rising)
- Shallow consolidation base (drawdown <= 10% from 52-week high)
- Volume-expanded breakout to fresh 52-week or multi-month highs
- Common gating: Sector in confirmed uptrend, ₹20 Cr turnover, 7-day earnings blackout
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


class S3RsMomentumStrategy(StrategyBase):
    """
    Strategy 3: High Relative Strength (RS) Momentum Leader Breakout.
    """

    def __init__(self):
        super().__init__(
            strategy_id="S3_RS_MOMENTUM",
            strategy_name="High-RS Leader Momentum",
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
        if "HIGH52W" not in df.columns or "SMA50" not in df.columns:
            df = compute_all_indicators(df)

        if len(df) < 200:
            return None

        last_row = df.iloc[-1]
        prev_row = df.iloc[-2]

        close = float(last_row["Close"])
        high = float(last_row["High"])
        low = float(last_row["Low"])
        sma50 = float(last_row["SMA50"])
        sma200 = float(last_row["SMA200"])
        vol = float(last_row["Volume"])
        vol50 = float(last_row.get("VOL50", 1.0))
        high20 = float(last_row.get("HIGH20", high))
        high52w = float(last_row.get("HIGH52W", high))

        # 2. Stage-2 Trend & Leadership Structure
        if not (close > sma50 and sma50 > sma200 and close > sma200):
            return None

        # 50-SMA must be rising
        sma50_prior = float(df["SMA50"].iloc[-20])
        if sma50 <= sma50_prior:
            return None

        # 3. Relative Strength Gate: RS Rating >= 80 OR massive alpha vs index
        has_rs_leadership = False
        if rs_rating is not None and rs_rating >= 80:
            has_rs_leadership = True
        elif index_df is not None and len(index_df) >= 50:
            beats_idx, s_ret, idx_ret, _ = check_relative_strength(df, index_df, lookback=50)
            if beats_idx and (s_ret - idx_ret >= 0.10):  # +10% alpha over index
                has_rs_leadership = True

        if not has_rs_leadership:
            return None

        # 4. Shallow Base Gate: within 12% of 52-week High
        if high52w > 0.0 and (close < 0.88 * high52w):
            return None

        # 5. Breakout Trigger: New 52W High OR Close > HIGH20 on Volume > 1.5x VOL50
        is_breakout_trigger = (
            (close >= high52w * 0.995 or close > high20)
            and (vol > 1.5 * vol50)
            and (((close - low) / max(0.01, high - low)) > 0.60)
        )

        if not is_breakout_trigger:
            return None

        # 6. Common Liquidity filter (>= ₹20 Crores turnover)
        is_liquid, _, _ = check_liquidity(df)
        if not is_liquid:
            return None

        # 7. Sector strength filter (Fail-closed)
        if sector_df is not None:
            is_sec_ok, _, _ = check_sector_strength(symbol, sector_df)
            if not is_sec_ok:
                return None

        # 8. Earnings blackout check
        if events_data:
            is_blocked, _, _ = check_earnings_blackout(symbol, events_data)
            if is_blocked:
                return None

        # 9. Position Sizing & Risk Parameters
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
            f"STRATEGY: S3 RS Momentum Leader | {symbol} | RS: {rs_rating or '85+'}\n"
            f"Market Leader ✅ | Shallow Base (<12% off 52W) ✅ | High Vol Breakout ✅\n"
            f"Order: Buy GTT @ ₹{trigger_price} (Max Open ₹{anti_chase})\n"
            f"Stop: ₹{risk.stop} | Target (+2R): ₹{risk.target} | Qty: {risk.qty} shares\n"
            f"Initial Risk: ₹{risk.risk_amount} ({risk_pct*100:.2f}%) | Hold: max 20 sessions"
        )

        return CandidateSignal(
            symbol=symbol,
            strategy_id=self.strategy_id,
            strategy_name=self.strategy_name,
            signal_date=signal_date,
            signal_type="MOMENTUM",
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
            setup_notes="Top-decile RS leader breaking out to fresh multi-month/52W high on volume expansion.",
        )
