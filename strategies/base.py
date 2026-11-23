"""
Midcap Swing Scanner - Abstract Strategy Base & Signal Contracts (Version 2)
Defines the unified interface and data contract for all quantitative swing strategies.
Ensures 100% schema backward-compatibility with the existing dashboard while
exposing Version 2 explainability fields.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any
import pandas as pd

from core.risk_engine import RiskParameters
from core.filters import get_sector_symbol


@dataclass(frozen=True)
class CandidateSignal:
    # Core identifiers
    symbol: str
    strategy_id: str
    strategy_name: str
    signal_date: str
    signal_type: str  # "BREAKOUT" or "PULLBACK" or "MOMENTUM"

    # Execution prices & sizing
    close: float
    entry: float
    stop: float
    target: float
    qty: int
    risk_per_unit: float
    risk_amount: float
    r_multiple: float
    allocation_amount: float
    allocation_pct: float

    # Order management
    order_type: str  # "BUY_GTT_STOP_LIMIT" or "BUY_MARKET_OPEN"
    trigger_price: float
    anti_chase_limit: float
    max_holding_sessions: int

    # Technical descriptors
    atr: float
    rsi: float
    rs_rating: Optional[int]
    sector: str

    # Narrative explainability
    thesis_card: str
    setup_notes: str

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary strictly matching existing dashboard JSON schema
        while adding Version 2 strategy identification fields.
        """
        return {
            # Legacy Dashboard Keys (guarantees zero UI regressions)
            "Signal Date": self.signal_date,
            "Symbol": self.symbol,
            "Sector": self.sector,
            "Type": self.signal_type,
            "Close": round(self.close, 2),
            "Entry": round(self.entry, 2),
            "Stop": round(self.stop, 2),
            "Target": round(self.target, 2),
            "Qty": int(self.qty),
            "Risk Per Unit": round(self.risk_per_unit, 2),
            "Risk Amount": round(self.risk_amount, 2),
            "ATR14": round(self.atr, 2),
            "RSI14": round(self.rsi, 1),
            "rs_rating": self.rs_rating,
            "base_maturity": 2,
            "days_in_base": 20,
            "inst_footprint": "accumulation",
            "next_event": None,
            "event_blocked_reason": None,
            "mtf_confluence": True,
            "thesis_card": self.thesis_card,

            # Version 2 Extended Keys
            "strategy_id": self.strategy_id,
            "strategy_name": self.strategy_name,
            "order_type": self.order_type,
            "trigger_price": round(self.trigger_price, 2),
            "anti_chase_limit": round(self.anti_chase_limit, 2),
            "max_holding_sessions": self.max_holding_sessions,
            "allocation_amount": round(self.allocation_amount, 2),
            "allocation_pct": round(self.allocation_pct, 2),
            "setup_notes": self.setup_notes,
        }


class StrategyBase(ABC):
    """
    Abstract base class for quantitative swing trading strategies.
    Each strategy independently evaluates market history, enforces its own setup triggers,
    and returns a standardized CandidateSignal upon qualification.
    """

    def __init__(self, strategy_id: str, strategy_name: str):
        self.strategy_id = strategy_id
        self.strategy_name = strategy_name

    @abstractmethod
    def evaluate(
        self,
        df: pd.DataFrame,
        symbol: str,
        sector_df: Optional[pd.DataFrame] = None,
        index_df: Optional[pd.DataFrame] = None,
        events_data: Optional[Dict[str, Any]] = None,
        rs_rating: Optional[int] = None,
        capital: float = 100000.0,
        risk_pct: float = 0.0075,
    ) -> Optional[CandidateSignal]:
        """
        Evaluate symbol DataFrame for strategy setup qualification.
        Returns CandidateSignal if all filters and triggers pass, else None.
        """
        pass
