"""
Midcap Swing Scanner - Strategy Suite (Version 2)
Provides three decoupled quantitative strategy engines:
- Strategy 1 (S1): Stage-2 VCP / Consolidation Breakout
- Strategy 2 (S2): 20-EMA Institutional Dip / Pullback
- Strategy 3 (S3): High Relative Strength (RS) Momentum Leader Breakout
"""

from typing import List, Dict, Type
from strategies.base import StrategyBase, CandidateSignal
from strategies.s1_vcp_breakout import S1VcpBreakoutStrategy
from strategies.s2_ema_pullback import S2EmaPullbackStrategy
from strategies.s3_rs_momentum import S3RsMomentumStrategy

ALL_STRATEGIES: List[StrategyBase] = [
    S1VcpBreakoutStrategy(),
    S2EmaPullbackStrategy(),
    S3RsMomentumStrategy(),
]

STRATEGY_REGISTRY: Dict[str, StrategyBase] = {
    s.strategy_id: s for s in ALL_STRATEGIES
}

__all__ = [
    "StrategyBase",
    "CandidateSignal",
    "S1VcpBreakoutStrategy",
    "S2EmaPullbackStrategy",
    "S3RsMomentumStrategy",
    "ALL_STRATEGIES",
    "STRATEGY_REGISTRY",
]
