"""
Daily NIFTY Midcap 100 Swing-Trading Scanner with Telegram Alerts.
Implements momentum trend-following and pullback setups with discipline rules.
"""

import datetime
import io
import json
import logging
import math
import os
import re
import sys
import time
from typing import Optional, Dict, Any, List, Tuple

# Suppress yfinance warning logs (e.g. 'No data found / may be delisted')
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

# Ensure utf-8 encoding on Windows console for emoji/unicode support
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import numpy as np
import pandas as pd
import requests
import yfinance as yf
from dotenv import load_dotenv

# =====================================================================
# 1) SECRETS AND CONFIGURATION
# =====================================================================
load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

CAPITAL = 100000
RISK_PCT = 0.01
SEND_NO_SIGNAL_MESSAGE = True
SEND_WATCHLIST = True
ATR_STOP_MULTIPLIER = 1.5
TARGET_R_MULTIPLE = 2.0
MAX_STOP_LOSS_PCT = 0.07
VOLUME_SPIKE_MULTIPLIER = 1.5
SETUP_WINDOW_DAYS = 10
INDEX_SYMBOL = "^NSEI"
MIN_AVG_TURNOVER = 200000000  # 20 Crores daily average turnover
ENABLE_PULLBACK = True
ENABLE_SQUEEZE = True
SYMBOLS_FILE = "symbols.txt"
TRADES_FILE = "trades.json"
OPEN_POSITIONS_FILE = "open_positions.json"
TG_OFFSET_FILE = "tg_offset.txt"
SCAN_RESULTS_FILE = "scan_results.json"

# Sector mapping for NIFTY Midcap 100 and key liquid Indian equities
# Uses only verified, live Yahoo Finance sector index symbols to avoid 404 warnings:
# ^CNXIT, ^NSEBANK, ^CNXAUTO, ^CNXPHARMA, ^CNXFMCG, ^CNXMETAL, ^CNXREALTY, ^CNXMEDIA, ^CNXPSUBANK, ^CNXINFRA
# Financials / NBFCs are mapped to ^NSEBANK.
# Unreliable / missing Yahoo indices (Energy, Commodities, Consumption, Services) are mapped directly to ^NSEI.
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

    # Energy (mapped to ^NSEI due to unreliable Yahoo sector index)
    "ATGL.NS": "^NSEI",
    "HINDPETRO.NS": "^NSEI",
    "JSWENERGY.NS": "^NSEI",
    "NHPC.NS": "^NSEI",
    "NLCINDIA.NS": "^NSEI",
    "OIL.NS": "^NSEI",
    "PREMIERENE.NS": "^NSEI",
    "SUZLON.NS": "^NSEI",
    "WAAREEENER.NS": "^NSEI",
    "RELIANCE.NS": "^NSEI",
    "NTPC.NS": "^NSEI",
    "POWERGRID.NS": "^NSEI",
    "ONGC.NS": "^NSEI",
    "BPCL.NS": "^NSEI",
    "IOC.NS": "^NSEI",
    "TATAPOWER.NS": "^NSEI",
    "ADANIGREEN.NS": "^NSEI",
    "ADANIPOWER.NS": "^NSEI",

    # Commodities (mapped to ^NSEI due to unreliable Yahoo sector index)
    "PIIND.NS": "^NSEI",
    "SRF.NS": "^NSEI",
    "UPL.NS": "^NSEI",
    "DEEPAKNTR.NS": "^NSEI",
    "TATACHEM.NS": "^NSEI",

    # Consumption (mapped to ^NSEI due to unreliable Yahoo sector index)
    "BLUESTARCO.NS": "^NSEI",
    "DIXON.NS": "^NSEI",
    "HAVELLS.NS": "^NSEI",
    "INDHOTEL.NS": "^NSEI",
    "JUBLFOOD.NS": "^NSEI",
    "KALYANKJIL.NS": "^NSEI",
    "LENSKART.NS": "^NSEI",
    "LGEINDIA.NS": "^NSEI",
    "MEESHO.NS": "^NSEI",
    "NYKAA.NS": "^NSEI",
    "PAGEIND.NS": "^NSEI",
    "RADICO.NS": "^NSEI",
    "SUPREMEIND.NS": "^NSEI",
    "SWIGGY.NS": "^NSEI",
    "UNITDSPR.NS": "^NSEI",
    "VMM.NS": "^NSEI",
    "VOLTAS.NS": "^NSEI",
    "TITAN.NS": "^NSEI",
    "TRENT.NS": "^NSEI",
    "ASIANPAINT.NS": "^NSEI",

    # Service Sector (mapped to ^NSEI due to unreliable Yahoo sector index)
    "CONCOR.NS": "^NSEI",
    "IRCTC.NS": "^NSEI",
    "NAUKRI.NS": "^NSEI",
    "TATACOMM.NS": "^NSEI",
    "BHARTIARTL.NS": "^NSEI",
    "INTERGLOBE.NS": "^NSEI",
}

# Cache for the index historical dataframe
_INDEX_CACHE: Optional[pd.DataFrame] = None
# Cache for sector historical dataframes
_SECTOR_CACHE: Dict[str, pd.DataFrame] = {}


# =====================================================================
# 2) TELEGRAM ALERTS
# =====================================================================
def send_telegram(message: str) -> bool:
    """
    Send a message to Telegram using bot API.
    Splits long messages into chunks of maximum 3500 characters.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("Telegram Error: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID is missing from .env")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    chunk_size = 3500
    all_success = True

    # Split message into chunks if length exceeds chunk_size
    chunks = [message[i : i + chunk_size] for i in range(0, len(message), chunk_size)] if message else [""]

    for idx, chunk in enumerate(chunks, start=1):
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
        }
        try:
            response = requests.post(url, json=payload, timeout=15)
            if response.status_code == 200:
                print(f"Telegram chunk {idx}/{len(chunks)} sent successfully.")
            else:
                print(f"Telegram Error ({response.status_code}): {response.text}")
                all_success = False
        except Exception as exc:
            print(f"Telegram Exception sending chunk {idx}/{len(chunks)}: {exc}")
            all_success = False

    return all_success


# =====================================================================
# 3) SYMBOL LIST RETRIEVAL
# =====================================================================
def get_symbols() -> List[str]:
    """
    Load symbols from symbols.txt if available.
    If empty or missing, download NIFTY Midcap 100 constituents from niftyindices.com.
    """
    symbols: List[str] = []

    # Check local symbols.txt
    if os.path.exists(SYMBOLS_FILE):
        try:
            with open(SYMBOLS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    # Split on commas and spaces
                    parts = re.split(r"[\s,]+", line)
                    for part in parts:
                        if part.startswith("#"):
                            break
                        cleaned = part.strip().upper()
                        if not cleaned:
                            continue
                        if cleaned.endswith(".NS"):
                            cleaned = cleaned[:-3]
                        sym = f"{cleaned}.NS"
                        if sym not in symbols:
                            symbols.append(sym)
        except Exception as exc:
            print(f"Warning reading {SYMBOLS_FILE}: {exc}")

    # Return local symbols if any were configured
    if symbols:
        return symbols

    # Fallback: Download NIFTY Midcap 100 list
    print("symbols.txt is empty or missing. Auto-downloading NIFTY Midcap 100 list...")
    url = "https://www.niftyindices.com/IndexConstituent/ind_niftymidcap100list.csv"
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/csv,application/csv,*/*",
        "Referer": "https://www.niftyindices.com/",
    }

    try:
        resp = requests.get(url, headers=headers, timeout=20)
        if resp.status_code == 200 and resp.text:
            lines = resp.text.splitlines()
            start_line_idx = None
            for idx, line in enumerate(lines):
                if "symbol" in line.lower():
                    start_line_idx = idx
                    break

            if start_line_idx is not None:
                csv_payload = "\n".join(lines[start_line_idx:])
                df_csv = pd.read_csv(io.StringIO(csv_payload))

                # Identify symbol column
                target_col = None
                for col in df_csv.columns:
                    if "symbol" in str(col).lower():
                        target_col = col
                        break

                if target_col is not None:
                    raw_symbols = df_csv[target_col].dropna().astype(str).str.upper().str.strip()
                    for raw_sym in raw_symbols:
                        if raw_sym.endswith(".NS"):
                            raw_sym = raw_sym[:-3]
                        if re.match(r"^[A-Z0-9&.-]+$", raw_sym):
                            sym = f"{raw_sym}.NS"
                            if sym not in symbols:
                                symbols.append(sym)
    except Exception as exc:
        print(f"Error downloading constituents from niftyindices: {exc}")

    if not symbols:
        print(f"ERROR: Failed to retrieve symbols from {SYMBOLS_FILE} and web source.")
        print(f"Please populate '{SYMBOLS_FILE}' with symbols and re-run.")
        sys.exit(1)

    return symbols


# =====================================================================
# 4) HISTORICAL DATA RETRIEVAL
# =====================================================================
def get_history(symbol: str) -> Optional[pd.DataFrame]:
    """
    Download 2 years of daily historical data for the symbol from Yahoo Finance.
    Returns clean DataFrame with Date, Open, High, Low, Close, Volume.
    """
    try:
        df = yf.download(symbol, period="2y", interval="1d", auto_adjust=False, progress=False)
        if df is None or df.empty:
            return None

        # Reset index to extract Date
        df = df.reset_index()

        # Flatten MultiIndex columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        # Rename first column to Date
        df.rename(columns={df.columns[0]: "Date"}, inplace=True)

        # Keep only required columns
        required_cols = ["Date", "Open", "High", "Low", "Close", "Volume"]
        for col in required_cols:
            if col not in df.columns:
                return None
        df = df[required_cols].copy()

        # Standardize date and numbers
        df["Date"] = pd.to_datetime(df["Date"])
        if df["Date"].dt.tz is not None:
            df["Date"] = df["Date"].dt.tz_localize(None)
        df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce").fillna(0)
        for num_col in ["Open", "High", "Low", "Close"]:
            df[num_col] = pd.to_numeric(df[num_col], errors="coerce")

        df = df.dropna(subset=["Close"]).reset_index(drop=True)
        if df.empty:
            return None

        return df
    except Exception:
        return None


# =====================================================================
# 5) TECHNICAL INDICATORS COMPUTATION
# =====================================================================
def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute moving averages, volatility measures, trend filters,
    squeeze detection, and setup/trigger signals.
    """
    df = df.copy()

    # Moving averages of Close
    df["SMA50"] = df["Close"].rolling(50).mean()
    df["SMA150"] = df["Close"].rolling(150).mean()
    df["SMA200"] = df["Close"].rolling(200).mean()

    # Moving averages of Volume
    df["VOL5"] = df["Volume"].rolling(5).mean()
    df["VOL50"] = df["Volume"].rolling(50).mean()

    # Range calculations (High - Low)
    hl_range = df["High"] - df["Low"]
    df["RANGE5"] = hl_range.rolling(5).mean()
    df["RANGE50"] = hl_range.rolling(50).mean()

    # True Range & ATR14
    prev_close = df["Close"].shift(1)
    tr1 = df["High"] - df["Low"]
    tr2 = (df["High"] - prev_close).abs()
    tr3 = (df["Low"] - prev_close).abs()
    df["true_range"] = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["ATR14"] = df["true_range"].rolling(14).mean()

    # RSI (14 and 2 periods)
    price_diff = df["Close"].diff()
    gains = price_diff.clip(lower=0)
    losses = (-price_diff).clip(lower=0)

    # RSI14
    avg_gain14 = gains.rolling(14).mean()
    avg_loss14 = losses.rolling(14).mean().replace(0, np.nan)
    rs14 = avg_gain14 / avg_loss14
    df["RSI14"] = 100 - (100 / (1 + rs14))

    # RSI2
    avg_gain2 = gains.rolling(2).mean()
    avg_loss2 = losses.rolling(2).mean().replace(0, np.nan)
    rs2 = avg_gain2 / avg_loss2
    df["RSI2"] = 100 - (100 / (1 + rs2))

    # 52-week High and Low
    df["HIGH52W"] = df["High"].rolling(252, min_periods=50).max()
    df["LOW52W"] = df["Low"].rolling(252, min_periods=50).min()

    # 20-day High excluding today
    df["HIGH20"] = df["High"].rolling(20).max().shift(1)

    # Trend Filter (Minervini / O'Neil style)
    df["TREND_OK"] = (
        (df["Close"] > df["SMA150"])
        & (df["Close"] > df["SMA200"])
        & (df["SMA150"] > df["SMA200"])
        & (df["SMA200"] > df["SMA200"].shift(50))
        & (df["SMA50"] > df["SMA150"])
        & (df["SMA50"] > df["SMA200"])
        & (df["Close"] > df["SMA50"])
        & (df["Close"] > 1.30 * df["LOW52W"])
        & (df["Close"] > 0.75 * df["HIGH52W"])
    )

    # Setup conditions: volume contraction & price tightening
    df["VOL_DRYUP"] = df["VOL5"] < (0.80 * df["VOL50"])
    df["PRICE_TIGHT"] = df["RANGE5"] < (0.80 * df["RANGE50"])
    df["SETUP_OK"] = df["VOL_DRYUP"] & df["PRICE_TIGHT"]

    # Squeeze condition: Bollinger Bands inside Keltner Channels
    sma20 = df["Close"].rolling(20).mean()
    std20 = df["Close"].rolling(20).std()
    bb_upper = sma20 + 2 * std20
    bb_lower = sma20 - 2 * std20

    atr20 = df["true_range"].rolling(20).mean()
    kc_upper = sma20 + 1.5 * atr20
    kc_lower = sma20 - 1.5 * atr20
    df["SQUEEZE_ON"] = (bb_upper < kc_upper) & (bb_lower > kc_lower)

    # Setup window: active if setup or squeeze occurred within SETUP_WINDOW_DAYS, shifted by 1 day
    coiling = df["SETUP_OK"] | (df["SQUEEZE_ON"] if ENABLE_SQUEEZE else False)
    df["SETUP_WINDOW"] = coiling.astype(float).rolling(SETUP_WINDOW_DAYS).max().shift(1) > 0

    # Breakout triggers
    df["BREAKOUT"] = (df["Close"] > df["HIGH20"]) & (df["Close"].shift(1) <= df["HIGH20"])
    df["VOL_SPIKE"] = df["Volume"] > (VOLUME_SPIKE_MULTIPLIER * df["VOL50"])

    # Strong close (>60% of candle's range)
    safe_hl = (df["High"] - df["Low"]).replace(0, np.nan)
    df["STRONG_CLOSE"] = ((df["Close"] - df["Low"]) / safe_hl) > 0.60

    # Pullback trigger
    df["PULLBACK"] = (df["RSI2"] < 10) & (df["RSI2"].shift(1) >= 10) & (df["Close"] > df["Close"].shift(1))

    # Master signals
    df["SIGNAL"] = (
        df["TREND_OK"]
        & df["SETUP_WINDOW"]
        & df["BREAKOUT"]
        & df["VOL_SPIKE"]
        & df["STRONG_CLOSE"]
    )
    df["SIGNAL_PULLBACK"] = df["TREND_OK"] & df["PULLBACK"]

    # Clean boolean columns (replace NaN with False)
    boolean_columns = [
        "TREND_OK",
        "VOL_DRYUP",
        "PRICE_TIGHT",
        "SETUP_OK",
        "SQUEEZE_ON",
        "SETUP_WINDOW",
        "BREAKOUT",
        "VOL_SPIKE",
        "STRONG_CLOSE",
        "PULLBACK",
        "SIGNAL",
        "SIGNAL_PULLBACK",
    ]
    for col in boolean_columns:
        df[col] = df[col].fillna(False).astype(bool)

    return df


# =====================================================================
# 6) MARKET REGIME FILTER
# =====================================================================
def get_cached_index_df() -> Optional[pd.DataFrame]:
    """Retrieve and cache the benchmark index history."""
    global _INDEX_CACHE
    if _INDEX_CACHE is None:
        idx_df = get_history(INDEX_SYMBOL)
        if idx_df is not None and not idx_df.empty:
            _INDEX_CACHE = add_indicators(idx_df)
    return _INDEX_CACHE


def market_ok() -> bool:
    """
    O'Neil M-rule: Benchmark index must be in a healthy uptrend.
    Last Close > SMA50 and Last Close > SMA200 and SMA50 > SMA200.
    """
    idx_df = get_cached_index_df()
    if idx_df is None or len(idx_df) < 200:
        return False

    last_row = idx_df.iloc[-1]
    is_ok = (
        (last_row["Close"] > last_row["SMA50"])
        and (last_row["Close"] > last_row["SMA200"])
        and (last_row["SMA50"] > last_row["SMA200"])
    )
    return bool(is_ok)


def index_return_50() -> Optional[float]:
    """
    50-day return of the benchmark index: (Last Close / Close 50 rows ago) - 1.
    """
    idx_df = get_cached_index_df()
    if idx_df is None or len(idx_df) < 51:
        return None

    last_close = idx_df["Close"].iloc[-1]
    close_50 = idx_df["Close"].iloc[-51]
    if close_50 <= 0:
        return None

    return float((last_close / close_50) - 1.0)


def get_sector_df(sector_symbol: str) -> Optional[pd.DataFrame]:
    """
    Retrieve and cache historical dataframe for a given sector index.
    Ensures each sector is downloaded only once per run.
    """
    global _SECTOR_CACHE
    if sector_symbol == INDEX_SYMBOL:
        return get_cached_index_df()

    if sector_symbol not in _SECTOR_CACHE:
        df = get_history(sector_symbol)
        if df is not None and not df.empty:
            _SECTOR_CACHE[sector_symbol] = add_indicators(df)
        else:
            _SECTOR_CACHE[sector_symbol] = None
    return _SECTOR_CACHE.get(sector_symbol)


def sector_ok(symbol: str) -> bool:
    """
    Sector strength filter:
    Looks up stock's sector symbol from SECTOR_MAP (defaults to ^NSEI).
    Returns True if sector's last Close > SMA50 AND > SMA200 AND SMA50 > SMA200.
    Returns True if sector data is unavailable or fails (fail-open).
    """
    try:
        clean_sym = symbol.strip().upper()
        if not clean_sym.endswith(".NS"):
            clean_sym = f"{clean_sym}.NS"

        sector_sym = SECTOR_MAP.get(clean_sym, SECTOR_MAP.get(symbol, INDEX_SYMBOL))
        sec_df = get_sector_df(sector_sym)
        if sec_df is None or len(sec_df) < 200:
            return True  # Fail-open so a download glitch never blocks trades

        last_row = sec_df.iloc[-1]
        is_ok = (
            (last_row["Close"] > last_row["SMA50"])
            and (last_row["Close"] > last_row["SMA200"])
            and (last_row["SMA50"] > last_row["SMA200"])
        )
        return bool(is_ok)
    except Exception:
        return True  # Strictly fail-open on any unexpected error


# =====================================================================
# 7) SINGLE SYMBOL SCANNER & POSITION SIZER
# =====================================================================
def scan_symbol(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Scan an individual symbol for Breakout or Pullback swing setups.
    Calculates entry, stop loss, profit target, and position quantity.
    """
    df = get_history(symbol)
    if df is None or len(df) < 220:
        return None

    df = add_indicators(df)

    # 1) Liquidity filter: 50-day average daily turnover >= MIN_AVG_TURNOVER
    avg_turnover = (df["Volume"] * df["Close"]).iloc[-50:].mean()
    if avg_turnover < MIN_AVG_TURNOVER:
        return None

    # 2) Relative strength filter: 50-day stock return must beat index 50-day return
    idx_ret = index_return_50()
    if idx_ret is not None and len(df) >= 60:
        stock_close_now = df["Close"].iloc[-1]
        stock_close_50 = df["Close"].iloc[-51]
        if stock_close_50 <= 0:
            return None
        stock_ret_50 = (stock_close_now / stock_close_50) - 1.0
        if stock_ret_50 <= idx_ret:
            return None

    # 3) Sector strength filter: stock's sector index must be in an uptrend
    if not sector_ok(symbol):
        return None

    # 4) Setup trigger check
    last_row = df.iloc[-1]
    if last_row["SIGNAL"]:
        signal_type = "BREAKOUT"
    elif ENABLE_PULLBACK and last_row["SIGNAL_PULLBACK"]:
        signal_type = "PULLBACK"
    else:
        return None

    # 5) Entry and Stop Loss
    entry = float(last_row["Close"])
    atr = float(last_row["ATR14"])
    if pd.isna(entry) or pd.isna(atr) or atr <= 0 or entry <= 0:
        return None

    stop = entry - (ATR_STOP_MULTIPLIER * atr)
    # Floor stop loss at 7% (max 7% risk from entry)
    stop = max(stop, entry * 0.93)
    if stop >= entry:
        return None

    # 6) Sizing and target
    risk_per_unit = entry - stop
    target = entry + (TARGET_R_MULTIPLE * risk_per_unit)
    qty = math.floor((CAPITAL * RISK_PCT) / risk_per_unit)
    if qty <= 0:
        return None

    risk_amount = qty * risk_per_unit
    sector_sym = SECTOR_MAP.get(symbol, INDEX_SYMBOL)

    return {
        "Signal Date": pd.to_datetime(last_row["Date"]).strftime("%Y-%m-%d"),
        "Symbol": symbol,
        "Sector": sector_sym,
        "Type": signal_type,
        "Close": round(entry, 2),
        "Entry": round(entry, 2),
        "Stop": round(stop, 2),
        "Target": round(target, 2),
        "Qty": int(qty),
        "Risk Per Unit": round(risk_per_unit, 2),
        "Risk Amount": round(risk_amount, 2),
        "ATR14": round(atr, 2),
        "RSI14": round(float(last_row["RSI14"]), 1),
    }


# =====================================================================
# 8) MESSAGES AND SCANNER RUNNER
# =====================================================================
DISCIPLINE_CARD = (
    "Execution & Risk Rules:\n"
    "• Max 2 trades per day and 2 percent daily loss limit\n"
    "• Move stop to entry when price reaches +8 percent\n"
    "• Exit if no +3 percent within 5 days (time stop)\n"
    "• Trail stop with 10 EMA while in profit\n"
    "• Never average down and never revenge trade\n"
    "• Check earnings date before entering"
)


def format_signal(sig: Dict[str, Any]) -> str:
    """Format signal dictionary into a Telegram alert message."""
    lines = [
        f"🟢 MIDCAP SWING SIGNAL ({sig['Type']})",
        f"Symbol: {sig['Symbol']}",
        f"Sector: {sig.get('Sector', 'N/A')}",
        f"Signal Date: {sig['Signal Date']}",
        f"Close: ₹{sig['Close']:.2f}",
        f"Entry: ₹{sig['Entry']:.2f}",
        f"Stop: ₹{sig['Stop']:.2f}",
        f"Target: ₹{sig['Target']:.2f}",
        f"Quantity: {sig['Qty']}",
        f"Risk/Unit: ₹{sig['Risk Per Unit']:.2f}",
        f"Risk Amount: ₹{sig['Risk Amount']:.2f}",
        f"ATR14: {sig['ATR14']:.2f}",
        f"RSI14: {sig['RSI14']:.1f}",
    ]
    return "\n".join(lines)


def run_scanner() -> Tuple[List[Dict[str, Any]], int, bool]:
    """
    Execute the scan across all candidate symbols.
    Returns (signals, scanned_count, is_market_ok).
    """
    print("Checking market regime filter...")
    is_mkt_ok = market_ok()
    if not is_mkt_ok:
        msg = "🔴 MARKET FILTER: Index not in uptrend. No new entries today (O'Neil M-rule)."
        print(msg)
        send_telegram(msg)
        return [], 0, False

    symbols = get_symbols()
    total = len(symbols)
    print(f"Scanning {total} symbols for swing setups...")

    signals: List[Dict[str, Any]] = []
    messages: List[str] = []

    for i, sym in enumerate(symbols, start=1):
        print(f"{i}/{total}: {sym}")
        sig = scan_symbol(sym)
        if sig:
            signals.append(sig)
            formatted = f"{format_signal(sig)}\n\n{DISCIPLINE_CARD}"
            messages.append(formatted)
        time.sleep(0.25)

    if messages:
        joined_message = "\n\n----\n\n".join(messages)
        send_telegram(joined_message)
    elif SEND_NO_SIGNAL_MESSAGE:
        send_telegram("No new midcap swing signals today.")

    return signals, total, True


# =====================================================================
# 9) WATCHLIST GENERATOR
# =====================================================================
def diagnose(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Diagnose a symbol's trend, coiling status, and breakout proximity.
    """
    df = get_history(symbol)
    if df is None or len(df) < 50:
        return None

    df = add_indicators(df)
    last_row = df.iloc[-1]

    close_val = float(last_row["Close"])
    high20_val = float(last_row["HIGH20"])
    if pd.isna(close_val) or close_val <= 0 or pd.isna(high20_val):
        return None

    sym_name = symbol[:-3] if symbol.endswith(".NS") else symbol
    sec_sym = SECTOR_MAP.get(symbol, INDEX_SYMBOL)
    sec_bullish = "YES" if sector_ok(symbol) else "no"
    trend_str = "YES" if bool(last_row["TREND_OK"]) else "no"
    coiling_str = "YES" if bool(last_row["SETUP_OK"]) else "no"
    dist_pct = round(((high20_val - close_val) / close_val) * 100, 2)

    return {
        "Symbol": sym_name,
        "Sector": sec_sym,
        "SectorBullish": sec_bullish,
        "Trend": trend_str,
        "Coiling": coiling_str,
        "DistToBreakout%": dist_pct,
        "Close": round(close_val, 2),
    }


def get_watchlist_candidates() -> List[Dict[str, Any]]:
    """
    Scan symbols to build a watchlist of stocks in an uptrend near breakout.
    Returns list of diagnose() dicts with Trend YES and DistToBreakout% <= 5.0,
    sorted by DistToBreakout% ascending.
    """
    symbols = get_symbols()
    watchlist_candidates: List[Dict[str, Any]] = []

    print("Building watchlist...")
    for sym in symbols:
        diag = diagnose(sym)
        if diag and diag["Trend"] == "YES" and diag["DistToBreakout%"] <= 5.0:
            watchlist_candidates.append(diag)
        time.sleep(0.2)

    # Sort ascending by distance to breakout
    watchlist_candidates.sort(key=lambda x: x["DistToBreakout%"])
    return watchlist_candidates


def build_watchlist_text(candidates: Optional[List[Dict[str, Any]]] = None) -> str:
    """
    Format watchlist candidates into a readable Telegram message.
    """
    if candidates is None:
        candidates = get_watchlist_candidates()

    if not candidates:
        return "📋 Watchlist empty: no midcap in uptrend near breakout."

    lines = ["📋 MIDCAP WATCHLIST (near breakout)"]
    for item in candidates:
        sec_info = f"{item['Sector']} (Bullish: {item['SectorBullish']})"
        line = (
            f"{item['Symbol']} | {sec_info} | {item['DistToBreakout%']}% away | "
            f"Close {item['Close']} | Coiling: {item['Coiling']}"
        )
        lines.append(line)

    return "\n".join(lines)


# =====================================================================
# 10) TRADING JOURNAL & TELEGRAM BOT COMMANDS
# =====================================================================
def load_json_file(file_path: str) -> List[Dict[str, Any]]:
    """
    Safely load a list of dictionaries from a JSON file.
    Creates an empty JSON file with [] if missing.
    """
    if not os.path.exists(file_path):
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write("[]\n")
        except Exception as exc:
            print(f"Error creating default {file_path}: {exc}")
        return []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if not content:
                return []
            data = json.loads(content)
            if isinstance(data, list):
                return data
            return []
    except Exception as exc:
        print(f"Error loading {file_path}: {exc}")
        return []


def save_json_file(file_path: str, data: List[Dict[str, Any]]) -> None:
    """Safely save a list of dictionaries to a JSON file."""
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        print(f"Error saving {file_path}: {exc}")


def load_trades() -> List[Dict[str, Any]]:
    """Load all closed trades from trades.json."""
    return load_json_file(TRADES_FILE)


def save_trades(data: List[Dict[str, Any]]) -> None:
    """Save closed trades to trades.json."""
    save_json_file(TRADES_FILE, data)


def load_open_positions() -> List[Dict[str, Any]]:
    """Load all open positions from open_positions.json."""
    return load_json_file(OPEN_POSITIONS_FILE)


def save_open_positions(data: List[Dict[str, Any]]) -> None:
    """Save open positions to open_positions.json."""
    save_json_file(OPEN_POSITIONS_FILE, data)


def get_updates(offset: Optional[int] = None) -> List[Dict[str, Any]]:
    """
    Call Telegram getUpdates API with the bot token and an optional offset.
    Returns the list of update objects.
    """
    if not TELEGRAM_BOT_TOKEN:
        return []
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    params: Dict[str, Any] = {"timeout": 10}
    if offset is not None:
        params["offset"] = offset

    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("ok"):
                return data.get("result", [])
    except Exception as exc:
        print(f"Error calling Telegram getUpdates: {exc}")
    return []


def handle_command(text: str, chat_id: Any) -> Optional[str]:
    """
    Parse and process journal commands received from Telegram.
    Security: Only responds to messages originating from the configured TELEGRAM_CHAT_ID.
    Case-insensitive, supports bot username mentions (e.g. /buy@my_bot).
    """
    if not TELEGRAM_CHAT_ID or str(chat_id).strip() != str(TELEGRAM_CHAT_ID).strip():
        print(f"Ignored unauthorized message from chat_id: {chat_id}")
        return None

    cleaned_text = text.strip()
    if not cleaned_text.startswith("/"):
        return None

    parts = cleaned_text.split()
    if not parts:
        return None

    # Strip bot username suffix if present e.g. /buy@bot -> /buy
    cmd = parts[0].lower().split("@")[0]
    args = parts[1:]

    try:
        if cmd == "/help":
            return (
                "🤖 SWING TRADING JOURNAL COMMANDS:\n\n"
                "• /buy SYMBOL ENTRY QTY [STOP] [TARGET]\n"
                "  Example: /buy DIXON 12500 8 11800 13900\n\n"
                "• /sell SYMBOL EXIT [NOTE]\n"
                "  Example: /sell DIXON 13800 hit target 2R\n\n"
                "• /open\n"
                "  List current open positions\n\n"
                "• /trades\n"
                "  List last 10 closed trades\n\n"
                "• /stats\n"
                "  Calculate win rate, profit factor, max drawdown & PnL\n\n"
                "• /help\n"
                "  Show this command menu"
            )

        elif cmd == "/buy":
            # Usage: /buy SYMBOL ENTRY_PRICE QTY [STOP] [TARGET]
            if len(args) < 3:
                return "⚠️ Usage: /buy SYMBOL ENTRY_PRICE QTY [STOP] [TARGET]\nExample: /buy PERSISTENT 5200 10 4950 5700"

            raw_sym = args[0].strip().upper()
            sym = raw_sym if raw_sym.endswith(".NS") else f"{raw_sym}.NS"

            try:
                entry_price = float(args[1])
                qty = int(float(args[2]))
            except ValueError:
                return "⚠️ Invalid format: Entry price and quantity must be valid numbers."

            if entry_price <= 0 or qty <= 0:
                return "⚠️ Entry price and quantity must be positive numbers."

            stop = None
            target = None
            if len(args) >= 4:
                try:
                    stop = float(args[3])
                except ValueError:
                    return "⚠️ Invalid format: Stop loss must be a number."
            if len(args) >= 5:
                try:
                    target = float(args[4])
                except ValueError:
                    return "⚠️ Invalid format: Target price must be a number."

            open_positions = load_open_positions()
            today_str = datetime.date.today().isoformat()

            new_pos = {
                "symbol": sym,
                "entry_date": today_str,
                "entry_price": round(entry_price, 2),
                "qty": qty,
                "stop": round(stop, 2) if stop is not None else None,
                "target": round(target, 2) if target is not None else None,
            }
            open_positions.append(new_pos)
            save_open_positions(open_positions)

            stop_str = f"₹{stop:,.2f}" if stop is not None else "None"
            target_str = f"₹{target:,.2f}" if target is not None else "None"

            return (
                f"✅ POSITION OPENED:\n"
                f"Symbol: {sym}\n"
                f"Entry: ₹{entry_price:,.2f} | Qty: {qty}\n"
                f"Stop: {stop_str} | Target: {target_str}\n"
                f"Date: {today_str}"
            )

        elif cmd == "/sell":
            # Usage: /sell SYMBOL EXIT_PRICE [NOTE]
            if len(args) < 2:
                return "⚠️ Usage: /sell SYMBOL EXIT_PRICE [NOTE]\nExample: /sell PERSISTENT 5600 Exited at 2R target"

            raw_sym = args[0].strip().upper()
            search_sym = raw_sym[:-3] if raw_sym.endswith(".NS") else raw_sym

            try:
                exit_price = float(args[1])
            except ValueError:
                return "⚠️ Invalid format: Exit price must be a valid number."

            note = " ".join(args[2:]).strip() if len(args) > 2 else ""

            open_positions = load_open_positions()
            matched_idx = -1
            matched_pos = None

            for i, pos in enumerate(open_positions):
                pos_sym = pos["symbol"].upper()
                pos_clean = pos_sym[:-3] if pos_sym.endswith(".NS") else pos_sym
                if pos_clean == search_sym:
                    matched_idx = i
                    matched_pos = pos
                    break

            if matched_pos is None:
                return f"❌ No open position found for {raw_sym}. Use /open to view active positions."

            # Remove from open positions
            open_positions.pop(matched_idx)
            save_open_positions(open_positions)

            entry_price = float(matched_pos["entry_price"])
            qty = int(matched_pos["qty"])
            entry_date = matched_pos.get("entry_date", datetime.date.today().isoformat())
            stop_val = matched_pos.get("stop")
            target_val = matched_pos.get("target")

            pnl = (exit_price - entry_price) * qty
            pnl_pct = ((exit_price - entry_price) / entry_price) * 100.0 if entry_price > 0 else 0.0

            r_mult = None
            if stop_val is not None:
                risk_per_unit = entry_price - float(stop_val)
                if abs(risk_per_unit) > 1e-4:
                    r_mult = (exit_price - entry_price) / risk_per_unit

            today_str = datetime.date.today().isoformat()
            closed_trade = {
                "symbol": matched_pos["symbol"],
                "entry_date": entry_date,
                "entry_price": round(entry_price, 2),
                "qty": qty,
                "stop": round(float(stop_val), 2) if stop_val is not None else None,
                "target": round(float(target_val), 2) if target_val is not None else None,
                "exit_date": today_str,
                "exit_price": round(exit_price, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
                "r_multiple": round(r_mult, 2) if r_mult is not None else None,
                "note": note,
            }

            trades = load_trades()
            trades.append(closed_trade)
            save_trades(trades)

            sign = "+" if pnl >= 0 else ""
            r_str = f"{r_mult:+.2f}R" if r_mult is not None else "N/A"
            note_str = f"\nNote: {note}" if note else ""

            return (
                f"🎯 POSITION CLOSED:\n"
                f"Symbol: {closed_trade['symbol']}\n"
                f"Entry: ₹{entry_price:,.2f} ({entry_date}) -> Exit: ₹{exit_price:,.2f} ({today_str})\n"
                f"Qty: {qty}\n"
                f"PnL: {sign}₹{pnl:,.2f} ({sign}{pnl_pct:.2f}%)\n"
                f"R-Multiple: {r_str}"
                f"{note_str}"
            )

        elif cmd == "/open":
            positions = load_open_positions()
            if not positions:
                return "📋 No open positions currently."

            lines = [f"📋 OPEN POSITIONS ({len(positions)}):"]
            for i, p in enumerate(positions, start=1):
                sym_clean = p["symbol"]
                e_price = p["entry_price"]
                q = p["qty"]
                e_date = p.get("entry_date", "N/A")
                s_str = f"₹{p['stop']:,.2f}" if p.get("stop") is not None else "None"
                t_str = f"₹{p['target']:,.2f}" if p.get("target") is not None else "None"
                lines.append(f"{i}) {sym_clean} (Qty: {q})")
                lines.append(f"   Entry: ₹{e_price:,.2f} on {e_date}")
                lines.append(f"   Stop: {s_str} | Target: {t_str}")

            return "\n".join(lines)

        elif cmd == "/trades":
            trades = load_trades()
            if not trades:
                return "📜 No closed trades recorded yet."

            recent = trades[-10:]
            recent.reverse()  # most recent first

            lines = [f"📜 RECENT CLOSED TRADES (Last {len(recent)}):"]
            for t in recent:
                pnl = t["pnl"]
                sign = "+" if pnl >= 0 else ""
                r_str = f"{t['r_multiple']:+.2f}R" if t.get("r_multiple") is not None else "N/A"
                lines.append(
                    f"• {t['symbol']}: {sign}₹{pnl:,.2f} ({sign}{t['pnl_pct']:.1f}%) | R: {r_str}\n"
                    f"  Entry: ₹{t['entry_price']:,.2f} ({t['entry_date']}) -> Exit: ₹{t['exit_price']:,.2f} ({t['exit_date']})"
                )
                if t.get("note"):
                    lines.append(f"  Note: {t['note']}")

            return "\n".join(lines)

        elif cmd == "/stats":
            trades = load_trades()
            if not trades:
                return "📊 No closed trades available to calculate statistics."

            total_trades = len(trades)
            wins = [t for t in trades if t["pnl"] > 0]
            losses = [t for t in trades if t["pnl"] <= 0]

            win_rate = (len(wins) / total_trades) * 100.0
            avg_win = (sum(t["pnl"] for t in wins) / len(wins)) if wins else 0.0
            avg_loss = (sum(t["pnl"] for t in losses) / len(losses)) if losses else 0.0
            sum_wins = sum(t["pnl"] for t in wins)
            sum_losses = sum(t["pnl"] for t in losses)

            if sum_losses != 0:
                profit_factor = sum_wins / abs(sum_losses)
                pf_str = f"{profit_factor:.2f}"
            elif sum_wins > 0:
                pf_str = "∞ (All Wins)"
            else:
                pf_str = "0.00"

            win_prob = len(wins) / total_trades
            loss_prob = 1.0 - win_prob
            expectancy = (win_prob * avg_win) - (loss_prob * abs(avg_loss))
            total_pnl = sum(t["pnl"] for t in trades)

            best_trade = max((t["pnl"] for t in trades), default=0.0)
            worst_trade = min((t["pnl"] for t in trades), default=0.0)

            # Max drawdown on cumulative PnL
            cum = 0.0
            peak = 0.0
            max_dd = 0.0
            for t in trades:
                cum += t["pnl"]
                if cum > peak:
                    peak = cum
                dd = peak - cum
                if dd > max_dd:
                    max_dd = dd

            pnl_sign = "+" if total_pnl >= 0 else ""
            exp_sign = "+" if expectancy >= 0 else ""
            best_sign = "+" if best_trade >= 0 else ""
            worst_sign = "+" if worst_trade >= 0 else ""

            return (
                "📊 SWING JOURNAL PERFORMANCE:\n\n"
                f"• Total Trades: {total_trades} (Wins: {len(wins)}, Losses: {len(losses)})\n"
                f"• Win Rate: {win_rate:.1f}%\n"
                f"• Total PnL: {pnl_sign}₹{total_pnl:,.2f}\n"
                f"• Profit Factor: {pf_str}\n"
                f"• Expectancy / Trade: {exp_sign}₹{expectancy:,.2f}\n"
                f"• Average Win: +₹{avg_win:,.2f}\n"
                f"• Average Loss: -₹{abs(avg_loss):,.2f}\n"
                f"• Max Drawdown: ₹{max_dd:,.2f}\n"
                f"• Best Trade: {best_sign}₹{best_trade:,.2f}\n"
                f"• Worst Trade: {worst_sign}₹{worst_trade:,.2f}"
            )

        else:
            return f"❓ Unknown command: {cmd}\nType /help to see all available commands."

    except Exception as exc:
        print(f"Error handling command '{text}': {exc}")
        return f"⚠️ Error processing command: {exc}"


def poll_once() -> None:
    """
    Check for new Telegram updates, execute any commands, and update offset.
    """
    last_offset = None
    if os.path.exists(TG_OFFSET_FILE):
        try:
            with open(TG_OFFSET_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    last_offset = int(content)
        except Exception:
            last_offset = None

    updates = get_updates(offset=last_offset)
    if not updates:
        return

    for update in updates:
        update_id = update.get("update_id")
        if update_id is not None:
            last_offset = update_id + 1

        message = update.get("message") or update.get("channel_post")
        if not message:
            continue

        text = message.get("text")
        chat = message.get("chat") or {}
        chat_id = chat.get("id")

        if text and chat_id:
            reply = handle_command(text, chat_id)
            if reply:
                send_telegram(reply)

    if last_offset is not None:
        try:
            with open(TG_OFFSET_FILE, "w", encoding="utf-8") as f:
                f.write(str(last_offset))
        except Exception as exc:
            print(f"Error saving {TG_OFFSET_FILE}: {exc}")


def poll_loop() -> None:
    """
    Poll Telegram for journal commands.
    If ONESHOT=1 is set, runs poll_once() once and exits immediately (suitable for 5-min cron workflows).
    Otherwise, polls continuously every 5 seconds.
    """
    if os.getenv("ONESHOT", "0").strip() == "1":
        print("Running Telegram listener in ONESHOT mode (processing pending updates once)...")
        poll_once()
        print("ONESHOT update processing completed.")
        return

    print("Telegram journal bot listener started. Polling every 5 seconds... (Press Ctrl+C to stop)")
    while True:
        try:
            poll_once()
        except KeyboardInterrupt:
            print("Telegram listener stopped by user.")
            break
        except Exception as exc:
            print(f"Polling loop exception: {exc}")
        time.sleep(5)


def git_commit_scan_results() -> None:
    """
    Commit and push scan_results.json to origin main.
    Skips if SKIP_GIT_PUSH environment variable is set to '1'.
    Fails safely so git errors never break the scanner.
    """
    if os.getenv("SKIP_GIT_PUSH", "0").strip() == "1":
        print("SKIP_GIT_PUSH=1: Skipping git commit & push.")
        return

    try:
        import subprocess
        # Check and stage scan_results.json
        subprocess.run(["git", "add", SCAN_RESULTS_FILE], check=True, capture_output=True, text=True)
        diff_proc = subprocess.run(["git", "diff", "--staged", "--quiet"], capture_output=True)
        if diff_proc.returncode != 0:
            commit_proc = subprocess.run(
                ["git", "commit", "-m", "update scan results [skip ci]"],
                capture_output=True,
                text=True,
                check=True,
            )
            print(f"Git committed scan results: {commit_proc.stdout.strip()}")
            subprocess.run(
                ["git", "push", "origin", "main"],
                capture_output=True,
                text=True,
                check=True,
            )
            print("Git pushed scan results to origin main.")
        else:
            print("No changes in scan_results.json to commit.")
    except Exception as exc:
        print(f"Git auto-commit failed (non-blocking): {exc}")


# =====================================================================
# 11) SCRIPT ENTRY POINT
# =====================================================================
if __name__ == "__main__":
    if "--poll" in sys.argv:
        poll_loop()  # long-running, for the listener workflow
    else:
        # 1. Run daily setup scanner
        signals, scanned_count, is_mkt_ok = run_scanner()

        # 2. Build watchlist candidates & send Telegram alert
        watchlist_candidates = get_watchlist_candidates()
        if SEND_WATCHLIST:
            wl_text = build_watchlist_text(watchlist_candidates)
            send_telegram(wl_text)

        # 3. Publish scan_results.json for web dashboard
        ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        now_ist = datetime.datetime.now(ist_tz).isoformat()

        total_scanned = scanned_count if scanned_count > 0 else len(get_symbols())
        scan_results = {
            "updated_at": now_ist,
            "market_ok": is_mkt_ok,
            "signals": signals,
            "watchlist": watchlist_candidates,
            "scanned_count": total_scanned,
        }

        with open(SCAN_RESULTS_FILE, "w", encoding="utf-8") as f:
            json.dump(scan_results, f, indent=2, ensure_ascii=False)
        print(f"Published scan results to {SCAN_RESULTS_FILE}")

        # 4. Attempt git auto-commit of scan_results.json
        git_commit_scan_results()
