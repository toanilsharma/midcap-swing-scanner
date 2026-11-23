"""
Midcap Swing Scanner - Core Package (Version 2)
Provides modular configuration, mathematical indicators, risk management, and filtering.
"""

from core.config import (
    CAPITAL,
    RISK_PCT,
    INITIAL_RISK_BUDGET,
    MAX_POSITION_ALLOCATION_PCT,
    MAX_PORTFOLIO_HEAT_PCT,
    MAX_HOLDING_SESSIONS,
    ATR_STOP_MULTIPLIER,
    TARGET_R_MULTIPLE,
    MAX_STOP_LOSS_PCT,
    VOLUME_SPIKE_MULTIPLIER,
    SETUP_WINDOW_DAYS,
    INDEX_SYMBOL,
    MIN_AVG_TURNOVER,
    EARNINGS_BLACKOUT_DAYS,
    IST_TZ,
)
from core.indicators import (
    compute_wilder_atr,
    compute_wilder_rsi,
    compute_all_indicators,
)
from core.risk_engine import (
    calculate_position_size,
    RiskParameters,
)

__all__ = [
    "CAPITAL",
    "RISK_PCT",
    "INITIAL_RISK_BUDGET",
    "MAX_POSITION_ALLOCATION_PCT",
    "MAX_PORTFOLIO_HEAT_PCT",
    "MAX_HOLDING_SESSIONS",
    "ATR_STOP_MULTIPLIER",
    "TARGET_R_MULTIPLE",
    "MAX_STOP_LOSS_PCT",
    "VOLUME_SPIKE_MULTIPLIER",
    "SETUP_WINDOW_DAYS",
    "INDEX_SYMBOL",
    "MIN_AVG_TURNOVER",
    "EARNINGS_BLACKOUT_DAYS",
    "IST_TZ",
    "compute_wilder_atr",
    "compute_wilder_rsi",
    "compute_all_indicators",
    "calculate_position_size",
    "RiskParameters",
]
