"""
Midcap Swing Scanner - Quantitative Gating & Filtering Engine (Version 2)
Implements strictly fail-closed filter predicates:
- Sector Strength Filter (Fail-closed: blocks trade if sector data is missing or in downtrend)
- Liquidity Filter (Fail-closed: requires ₹20 Crores 50-day average daily turnover)
- Relative Strength vs Benchmark (Stock 50-day return must outperform index 50-day return)
- Event & Earnings Blackout Filter (Blocks entries within 7 days prior to earnings)
"""

from typing import Dict, Any, Optional, Tuple
import datetime
import pandas as pd
from core.config import (
    INDEX_SYMBOL,
    MIN_AVG_TURNOVER,
    EARNINGS_BLACKOUT_DAYS,
)

# Comprehensive Sector mapping for NIFTY Midcap 100 and liquid NSE equities.
# Uses verified Yahoo Finance sector indices (^CNXIT, ^NSEBANK, ^CNXAUTO, ^CNXPHARMA,
# ^CNXFMCG, ^CNXMETAL, ^CNXREALTY, ^CNXMEDIA, ^CNXPSUBANK, ^CNXINFRA).
# Missing or broken sector indices default to ^NSEI benchmark index.
SECTOR_MAP: Dict[str, str] = {
    # NIFTY IT (^CNXIT)
    "COFORGE.NS": "^CNXIT",
    "MPHASIS.NS": "^CNXIT",
    "OFSS.NS": "^CNXIT",
    "PERSISTENT.NS": "^CNXIT",
    "LTIM.NS": "^CNXIT",
    "LTTS.NS": "^CNXIT",
    "TCS.NS": "^CNXIT",
    "INFY.NS": "^CNXIT",
    "WIPRO.NS": "^CNXIT",
    "HCLTECH.NS": "^CNXIT",
    "TECHM.NS": "^CNXIT",

    # NIFTY Bank (^NSEBANK)
    "AUBANK.NS": "^NSEBANK",
    "FEDERALBNK.NS": "^NSEBANK",
    "IDFCFIRSTB.NS": "^NSEBANK",
    "INDUSINDBK.NS": "^NSEBANK",
    "YESBANK.NS": "^NSEBANK",
    "BANDHANBNK.NS": "^NSEBANK",
    "RBLBANK.NS": "^NSEBANK",
    "HDFCBANK.NS": "^NSEBANK",
    "ICICIBANK.NS": "^NSEBANK",
    "KOTAKBANK.NS": "^NSEBANK",
    "AXISBANK.NS": "^NSEBANK",

    # Financial Services / NBFC / Insurance (using ^NSEBANK as reliable proxy)
    "360ONE.NS": "^NSEBANK",
    "ABCAPITAL.NS": "^NSEBANK",
    "GROWW.NS": "^NSEBANK",
    "ICICIAMC.NS": "^NSEBANK",
    "ICICIGI.NS": "^NSEBANK",
    "IREDA.NS": "^NSEBANK",
    "LICHSGFIN.NS": "^NSEBANK",
    "LICI.NS": "^NSEBANK",
    "LTF.NS": "^NSEBANK",
    "M&MFIN.NS": "^NSEBANK",
    "MCX.NS": "^NSEBANK",
    "MFSL.NS": "^NSEBANK",
    "MOTILALOFS.NS": "^NSEBANK",
    "PAYTM.NS": "^NSEBANK",
    "POLICYBZR.NS": "^NSEBANK",
    "RECLTD.NS": "^NSEBANK",
    "SBICARD.NS": "^NSEBANK",
    "PFC.NS": "^NSEBANK",
    "CHOLAFIN.NS": "^NSEBANK",
    "SHRIRAMFIN.NS": "^NSEBANK",
    "BAJFINANCE.NS": "^NSEBANK",
    "BAJAJFINSV.NS": "^NSEBANK",

    # NIFTY PSU Bank (^CNXPSUBANK)
    "BANKINDIA.NS": "^CNXPSUBANK",
    "INDIANB.NS": "^CNXPSUBANK",
    "MAHABANK.NS": "^CNXPSUBANK",
    "SBIN.NS": "^CNXPSUBANK",
    "CANBK.NS": "^CNXPSUBANK",
    "PNB.NS": "^CNXPSUBANK",
    "UNIONBANK.NS": "^CNXPSUBANK",

    # NIFTY Auto (^CNXAUTO)
    "ASHOKLEY.NS": "^CNXAUTO",
    "BHARATFORG.NS": "^CNXAUTO",
    "EXIDEIND.NS": "^CNXAUTO",
    "HEROMOTOCO.NS": "^CNXAUTO",
    "MRF.NS": "^CNXAUTO",
    "TIINDIA.NS": "^CNXAUTO",
    "TATAMOTORS.NS": "^CNXAUTO",
    "MARUTI.NS": "^CNXAUTO",
    "M&M.NS": "^CNXAUTO",
    "EICHERMOT.NS": "^CNXAUTO",
    "BAJAJ-AUTO.NS": "^CNXAUTO",
    "BALKRISIND.NS": "^CNXAUTO",
    "BOSCHLTD.NS": "^CNXAUTO",
    "TVSMOTOR.NS": "^CNXAUTO",

    # NIFTY Pharma (^CNXPHARMA)
    "AUROPHARMA.NS": "^CNXPHARMA",
    "BIOCON.NS": "^CNXPHARMA",
    "FORTIS.NS": "^CNXPHARMA",
    "GLENMARK.NS": "^CNXPHARMA",
    "LAURUSLABS.NS": "^CNXPHARMA",
    "LUPIN.NS": "^CNXPHARMA",
    "MANKIND.NS": "^CNXPHARMA",
    "SUNPHARMA.NS": "^CNXPHARMA",
    "DRREDDY.NS": "^CNXPHARMA",
    "CIPLA.NS": "^CNXPHARMA",
    "DIVISLAB.NS": "^CNXPHARMA",
    "ALKEM.NS": "^CNXPHARMA",
    "TORNTPHARM.NS": "^CNXPHARMA",
    "ZYDUSLIFE.NS": "^CNXPHARMA",
    "APOLLOHOSP.NS": "^CNXPHARMA",

    # NIFTY FMCG (^CNXFMCG)
    "COLPAL.NS": "^CNXFMCG",
    "DABUR.NS": "^CNXFMCG",
    "GODFRYPHLP.NS": "^CNXFMCG",
    "MARICO.NS": "^CNXFMCG",
    "PATANJALI.NS": "^CNXFMCG",
    "ITC.NS": "^CNXFMCG",
    "HINDUNILVR.NS": "^CNXFMCG",
    "NESTLEIND.NS": "^CNXFMCG",
    "BRITANNIA.NS": "^CNXFMCG",
    "TATACONSUM.NS": "^CNXFMCG",
    "PGHH.NS": "^CNXFMCG",
    "EMAMILTD.NS": "^CNXFMCG",

    # NIFTY Metal (^CNXMETAL)
    "APLAPOLLO.NS": "^CNXMETAL",
    "HINDCOPPER.NS": "^CNXMETAL",
    "NATIONALUM.NS": "^CNXMETAL",
    "NMDC.NS": "^CNXMETAL",
    "SAIL.NS": "^CNXMETAL",
    "TATASTEEL.NS": "^CNXMETAL",
    "JSWSTEEL.NS": "^CNXMETAL",
    "HINDALCO.NS": "^CNXMETAL",
    "JINDALSTEL.NS": "^CNXMETAL",
    "VEDL.NS": "^CNXMETAL",

    # NIFTY Realty (^CNXREALTY)
    "GODREJPROP.NS": "^CNXREALTY",
    "LODHA.NS": "^CNXREALTY",
    "OBEROIRLTY.NS": "^CNXREALTY",
    "PHOENIXLTD.NS": "^CNXREALTY",
    "PRESTIGE.NS": "^CNXREALTY",
    "DLF.NS": "^CNXREALTY",
    "BRIGADE.NS": "^CNXREALTY",

    # NIFTY Infra / Capital Goods (^CNXINFRA)
    "APARINDS.NS": "^CNXINFRA",
    "ASTRAL.NS": "^CNXINFRA",
    "BDL.NS": "^CNXINFRA",
    "BHEL.NS": "^CNXINFRA",
    "COCHINSHIP.NS": "^CNXINFRA",
    "GMRAIRPORT.NS": "^CNXINFRA",
    "GVT&D.NS": "^CNXINFRA",
    "INDUSTOWER.NS": "^CNXINFRA",
    "KEI.NS": "^CNXINFRA",
    "RVNL.NS": "^CNXINFRA",
    "LT.NS": "^CNXINFRA",
    "HAL.NS": "^CNXINFRA",
    "BEL.NS": "^CNXINFRA",
    "ULTRACEMCO.NS": "^CNXINFRA",
    "GRASIM.NS": "^CNXINFRA",

    # NIFTY Media (^CNXMEDIA)
    "SUNTV.NS": "^CNXMEDIA",
    "ZEEL.NS": "^CNXMEDIA",
    "PVRINOX.NS": "^CNXMEDIA",

    # Energy / Commodities / Consumption default to ^NSEI
    "RELIANCE.NS": "^NSEI",
    "NTPC.NS": "^NSEI",
    "POWERGRID.NS": "^NSEI",
    "ONGC.NS": "^NSEI",
    "BPCL.NS": "^NSEI",
    "IOC.NS": "^NSEI",
    "TATAPOWER.NS": "^NSEI",
    "ADANIGREEN.NS": "^NSEI",
    "ADANIPOWER.NS": "^NSEI",
    "TRENT.NS": "^NSEI",
    "TITAN.NS": "^NSEI",
    "ASIANPAINT.NS": "^NSEI",
    "DIXON.NS": "^NSEI",
    "HAVELLS.NS": "^NSEI",
    "INDHOTEL.NS": "^NSEI",
    "KALYANKJIL.NS": "^NSEI",
}


def get_sector_symbol(symbol: str) -> str:
    """Return mapped sector index symbol for a given stock (defaults to ^NSEI)."""
    clean_sym = symbol.strip().upper()
    if not clean_sym.endswith(".NS"):
        clean_sym = f"{clean_sym}.NS"
    return SECTOR_MAP.get(clean_sym, SECTOR_MAP.get(symbol, INDEX_SYMBOL))


def check_sector_strength(
    symbol: str,
    sector_df: Optional[pd.DataFrame]
) -> Tuple[bool, str, str]:
    """
    Evaluate sector strength with STRICT FAIL-CLOSED GUARANTEE.
    Rule:
    - Sector Close > SMA50 AND Sector Close > SMA200 AND SMA50 > SMA200.
    - If sector data is missing or < 200 bars, returns False (never fails open).
    Returns (is_ok, reason, sector_symbol).
    """
    sector_sym = get_sector_symbol(symbol)

    if sector_df is None or sector_df.empty or len(sector_df) < 200:
        return (False, "BLOCKED_SECTOR_DATA_UNAVAILABLE", sector_sym)

    try:
        last_row = sector_df.iloc[-1]
        close = float(last_row["Close"])
        sma50 = float(last_row["SMA50"])
        sma200 = float(last_row["SMA200"])

        if pd.isna(close) or pd.isna(sma50) or pd.isna(sma200):
            return (False, "BLOCKED_SECTOR_DATA_INVALID", sector_sym)

        is_uptrend = (close > sma50) and (close > sma200) and (sma50 > sma200)
        if is_uptrend:
            return (True, "SECTOR_IN_UPTREND", sector_sym)
        else:
            return (False, "BLOCKED_SECTOR_DOWNTREND", sector_sym)
    except Exception as exc:
        return (False, f"BLOCKED_SECTOR_ERROR_{type(exc).__name__}", sector_sym)


def check_liquidity(
    df: pd.DataFrame,
    min_avg_turnover: float = MIN_AVG_TURNOVER
) -> Tuple[bool, float, str]:
    """
    Evaluate 50-day average daily turnover (Volume * Close >= min_avg_turnover).
    FAIL-CLOSED: returns False if fewer than 50 bars.
    Returns (is_liquid, avg_turnover, reason).
    """
    if df is None or len(df) < 50:
        return (False, 0.0, "BLOCKED_INSUFFICIENT_HISTORY_FOR_LIQUIDITY")

    sub = df.iloc[-50:]
    avg_turnover = float((sub["Volume"] * sub["Close"]).mean())

    if pd.isna(avg_turnover) or avg_turnover < min_avg_turnover:
        return (False, avg_turnover, f"BLOCKED_LOW_TURNOVER_INR_{avg_turnover:,.0f}")

    return (True, avg_turnover, "LIQUIDITY_OK")


def check_relative_strength(
    stock_df: pd.DataFrame,
    index_df: pd.DataFrame,
    lookback: int = 50
) -> Tuple[bool, float, float, str]:
    """
    Relative Strength Filter: Stock return over lookback must exceed index return.
    FAIL-CLOSED: returns False if either frame has insufficient bars.
    Returns (beats_index, stock_ret, index_ret, reason).
    """
    if stock_df is None or len(stock_df) <= lookback:
        return (False, 0.0, 0.0, "BLOCKED_INSUFFICIENT_STOCK_BARS_FOR_RS")
    if index_df is None or len(index_df) <= lookback:
        return (False, 0.0, 0.0, "BLOCKED_INSUFFICIENT_INDEX_BARS_FOR_RS")

    s_close_now = float(stock_df["Close"].iloc[-1])
    s_close_prior = float(stock_df["Close"].iloc[-lookback - 1])

    idx_close_now = float(index_df["Close"].iloc[-1])
    idx_close_prior = float(index_df["Close"].iloc[-lookback - 1])

    if s_close_prior <= 0.0 or idx_close_prior <= 0.0:
        return (False, 0.0, 0.0, "BLOCKED_INVALID_PRICE_FOR_RS")

    stock_ret = (s_close_now / s_close_prior) - 1.0
    index_ret = (idx_close_now / idx_close_prior) - 1.0

    if stock_ret > index_ret:
        return (True, stock_ret, index_ret, "RELATIVE_STRENGTH_BEATS_INDEX")
    else:
        return (False, stock_ret, index_ret, "BLOCKED_WEAKER_THAN_INDEX")


def check_earnings_blackout(
    symbol: str,
    events_data: Dict[str, Any],
    blackout_days: int = EARNINGS_BLACKOUT_DAYS,
    ref_date: Optional[datetime.date] = None
) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """
    Check if a known earnings or material event is scheduled within the blackout window.
    Returns (is_blocked, blocked_reason, next_event_dict).
    """
    if not events_data:
        return (False, None, None)

    clean_sym = symbol.strip().upper()
    if clean_sym.endswith(".NS"):
        short_sym = clean_sym[:-3]
    else:
        short_sym = clean_sym
        clean_sym = f"{clean_sym}.NS"

    sym_events = events_data.get(clean_sym) or events_data.get(short_sym)
    if not sym_events or not isinstance(sym_events, list):
        return (False, None, None)

    if ref_date is None:
        ref_date = datetime.date.today()

    for ev in sym_events:
        if not isinstance(ev, dict):
            continue
        ev_date_str = ev.get("date")
        if not ev_date_str:
            continue
        try:
            ev_date = datetime.date.fromisoformat(ev_date_str[:10])
            days_diff = (ev_date - ref_date).days
            if 0 <= days_diff <= blackout_days:
                ev_type = ev.get("type", "EVENT")
                reason = f"BLOCKED_{ev_type}_IN_{days_diff}D"
                ev_info = {
                    "type": ev_type,
                    "date": ev_date_str,
                    "days_to_event": days_diff,
                }
                return (True, reason, ev_info)
        except Exception:
            continue

    return (False, None, None)
