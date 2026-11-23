"""
Midcap Swing Scanner - Version 2 Configuration & Parameters
Central single source of truth for quantitative trading rules, portfolio guardrails,
and operational constants.
"""

import datetime
import os
from typing import Dict, Any

# =====================================================================
# 1) CAPITAL & RISK MANAGEMENT PARAMETERS (V2 User Contract)
# =====================================================================
CAPITAL: float = 100000.0                       # Base starting equity (₹1,00,000)
RISK_PCT: float = 0.0075                        # 0.75% equity risk per trade
INITIAL_RISK_BUDGET: float = CAPITAL * RISK_PCT # ₹750 per trade on initial capital
MAX_POSITION_ALLOCATION_PCT: float = 0.25       # Max 25% of equity in single stock (₹25,000 cap)
MAX_PORTFOLIO_HEAT_PCT: float = 0.0375          # Max 3.75% total open risk (max 5 open positions)
MAX_OPEN_POSITIONS: int = 5                     # Maximum concurrent open positions

# =====================================================================
# 2) SWING TRADING EXECUTION & TIMEFRAME RULES
# =====================================================================
MAX_HOLDING_SESSIONS: int = 20                  # Maximum holding period: 20 trading sessions
ATR_STOP_MULTIPLIER: float = 1.5                # Initial stop loss distance = 1.5 * ATR14
TARGET_R_MULTIPLE: float = 2.0                  # Partial profit target at +2R (50% position)
MAX_STOP_LOSS_PCT: float = 0.07                 # Hard risk ceiling: Stop loss cannot exceed 7% from entry
BREAKEVEN_TRIGGER_GAIN_PCT: float = 0.08        # Ratchet stop to entry when price achieves +8%
ANTI_CHASE_MAX_GAP_PCT: float = 0.015           # Void next-day entry if Open > Trigger + 1.5%

# =====================================================================
# 3) SETUP & INDICATOR THRESHOLDS
# =====================================================================
VOLUME_SPIKE_MULTIPLIER: float = 1.5            # Breakout requires Volume > 1.5 * 50-day average volume
SETUP_WINDOW_DAYS: int = 10                     # Volatility coiling/squeeze lookback window
MIN_AVG_TURNOVER: float = 200000000.0           # ₹20 Crores minimum 50-day average daily turnover
EARNINGS_BLACKOUT_DAYS: int = 7                 # Blackout new entries within 7 days prior to earnings
MIN_HISTORY_BARS: int = 252                     # Minimum completed daily bars required for full analysis

# Setup enablement flags
ENABLE_PULLBACK: bool = True
ENABLE_SQUEEZE: bool = True
ENABLE_RS_LEADER: bool = True

# Benchmark and reference indices
INDEX_SYMBOL: str = "^NSEI"                     # NIFTY 50 benchmark
MIDCAP_INDEX_SYMBOL: str = "^NSEMDCP50"         # NIFTY Midcap proxy

# =====================================================================
# 4) TIMEZONE & CALENDAR
# =====================================================================
IST_TZ = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

def get_now_ist() -> datetime.datetime:
    """Return current timestamp in Indian Standard Time (IST)."""
    return datetime.datetime.now(IST_TZ)

# =====================================================================
# 5) FILE PATHS & PERSISTENCE
# =====================================================================
SYMBOLS_FILE: str = "symbols.txt"
TRADES_FILE: str = "trades.json"
OPEN_POSITIONS_FILE: str = "open_positions.json"
SCAN_RESULTS_FILE: str = "scan_results.json"
DEALS_FILE: str = "deals.json"
EVENTS_FILE: str = "events.json"
ALERT_SETTINGS_FILE: str = "alert_settings.json"
TG_OFFSET_FILE: str = "tg_offset.txt"
LAST_ALERT_FILE: str = "last_alert.txt"
BACKTEST_RESULTS_FILE: str = "backtest_results.json"
ARCHIVE_DIR: str = "archive"

# Default alert settings
DEFAULT_ALERT_SETTINGS: Dict[str, Any] = {
    "mute_until": None,
    "quiet_start": "21:00",
    "quiet_end": "08:00",
    "enable": {
        "scan": True,
        "watchlist": True,
        "market": True,
    },
    "digest": False,
}
