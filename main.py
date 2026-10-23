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
ALERT_SETTINGS_FILE = "alert_settings.json"
SCAN_RESULTS_FILE = "scan_results.json"
LAST_ALERT_FILE = "last_alert.txt"
DEALS_FILE = "deals.json"
EVENTS_FILE = "events.json"
EARNINGS_BLACKOUT_DAYS = 7

_DEALS: Dict[str, Any] = {}
_DEALS_STALE: bool = False
_INST_SUMMARY: Dict[str, int] = {"accumulation": 0, "churn": 0, "unknown": 0}
_LANDMINES: List[Dict[str, Any]] = []
_EARNINGS_CACHE: Dict[str, Optional[str]] = {}

IST_TZ = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

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

_DIGEST_MESSAGES: List[Tuple[str, str]] = []


def get_now_ist() -> datetime.datetime:
    return datetime.datetime.now(IST_TZ)


def load_alert_settings() -> Dict[str, Any]:
    """
    Load alert settings from alert_settings.json.
    If missing or corrupt, initialize with defaults.
    """
    settings = dict(DEFAULT_ALERT_SETTINGS)
    if os.path.exists(ALERT_SETTINGS_FILE):
        try:
            with open(ALERT_SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    settings.update(data)
                    if "enable" in data and isinstance(data["enable"], dict):
                        en = dict(DEFAULT_ALERT_SETTINGS["enable"])
                        en.update(data["enable"])
                        settings["enable"] = en
                    return settings
        except Exception as exc:
            print(f"Warning reading {ALERT_SETTINGS_FILE}: {exc}")

    save_alert_settings(settings)
    return settings


def save_alert_settings(settings: Dict[str, Any]) -> None:
    try:
        with open(ALERT_SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2, ensure_ascii=False)
    except Exception as exc:
        print(f"Error saving {ALERT_SETTINGS_FILE}: {exc}")


def load_tg_offset() -> Optional[int]:
    """
    Read integer offset from tg_offset.txt if it exists and is non-empty.
    Else returns None (treated as unknown).
    """
    if os.path.exists(TG_OFFSET_FILE):
        try:
            with open(TG_OFFSET_FILE, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    return int(content)
        except Exception as exc:
            print(f"Warning reading {TG_OFFSET_FILE}: {exc}")
    return None


def save_tg_offset(offset: int) -> None:
    try:
        with open(TG_OFFSET_FILE, "w", encoding="utf-8") as f:
            f.write(str(offset))
    except Exception as exc:
        print(f"Error saving {TG_OFFSET_FILE}: {exc}")

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
def _dispatch_telegram_http(message: str) -> bool:
    """
    Perform actual HTTP POST requests to Telegram sendMessage with chunking.
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


def send_telegram(
    message: str,
    kind: str = "proactive",
    msg_type: Optional[str] = None
) -> bool:
    """
    Send a message to Telegram using bot API with gating rules.
    kind is 'proactive' for scan/watchlist/market/no-signals alerts and 'reply' for user commands.
    A proactive send is blocked silently (print "[BLOCKED:<reason>] <first 40 chars>" and return True) if:
      (a) QUIET environment variable is '1'
      (b) mute_until is active (now < mute_until)
      (c) current IST time is inside quiet_start..quiet_end window
      (d) matching enable flag is false (scan / watchlist / market)
    A 'reply' send is blocked ONLY by (b) mute.
    """
    if not message:
        return True

    # Normalize kind if caller passed msg_type as kind e.g. send_telegram(msg, kind="scan")
    if kind in ("scan", "watchlist", "market"):
        msg_type = kind
        kind = "proactive"

    settings = load_alert_settings()
    now_ist = get_now_ist()

    # Rule (b): Mute check applies to BOTH proactive and reply
    mute_until_val = settings.get("mute_until")
    if mute_until_val:
        try:
            mute_dt = datetime.datetime.fromisoformat(mute_until_val)
            if mute_dt.tzinfo is None:
                mute_dt = mute_dt.replace(tzinfo=IST_TZ)
            if now_ist < mute_dt:
                # Allow the confirmation reply of /mute itself so the user knows they are muted
                if kind == "reply" and message.startswith("Muted until"):
                    pass
                else:
                    first_chars = message[:40].replace("\n", " ")
                    print(f"[BLOCKED:mute] {first_chars}")
                    return True
        except Exception as exc:
            print(f"Warning parsing mute_until: {exc}")

    # Reply is blocked ONLY by (b) mute
    if kind == "reply":
        return _dispatch_telegram_http(message)

    # Gating for proactive alerts:
    # Rule (a): Environment variable QUIET == "1"
    if os.getenv("QUIET", "0").strip() == "1":
        first_chars = message[:40].replace("\n", " ")
        print(f"[BLOCKED:quiet_env] {first_chars}")
        return True

    # Rule (c): Inside quiet window quiet_start..quiet_end (handles past-midnight wrap)
    # Bypassed if FORCE_ALERT == "1" so delayed GitHub Actions runners can still deliver daily summary
    force_alert = os.getenv("FORCE_ALERT", "0").strip() == "1"
    if not force_alert:
        q_start = settings.get("quiet_start")
        q_end = settings.get("quiet_end")
        if q_start and q_end and q_start != "off" and q_end != "off":
            try:
                qs_h, qs_m = map(int, q_start.split(":"))
                qe_h, qe_m = map(int, q_end.split(":"))
                now_m = now_ist.hour * 60 + now_ist.minute
                start_m = qs_h * 60 + qs_m
                end_m = qe_h * 60 + qe_m

                in_quiet = False
                if start_m < end_m:
                    in_quiet = (start_m <= now_m < end_m)
                elif start_m > end_m:
                    in_quiet = (now_m >= start_m or now_m < end_m)

                if in_quiet:
                    first_chars = message[:40].replace("\n", " ")
                    print(f"[BLOCKED:quiet_window] {first_chars}")
                    return True
            except Exception as exc:
                print(f"Warning checking quiet window ({q_start}-{q_end}): {exc}")

    # Rule (d): Matching enable flag is false (scan / watchlist / market)
    eff_type = msg_type
    if not eff_type:
        if "MARKET FILTER" in message:
            eff_type = "market"
        elif "WATCHLIST" in message:
            eff_type = "watchlist"
        else:
            eff_type = "scan"

    enable_flags = settings.get("enable", {})
    if not enable_flags.get(eff_type, True):
        first_chars = message[:40].replace("\n", " ")
        print(f"[BLOCKED:disabled_{eff_type}] {first_chars}")
        return True

    return _dispatch_telegram_http(message)



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
_HISTORY_CACHE: Dict[str, pd.DataFrame] = {}


def get_history(symbol: str) -> Optional[pd.DataFrame]:
    """
    Download 2 years of daily historical data for the symbol from Yahoo Finance.
    Returns clean DataFrame with Date, Open, High, Low, Close, Volume.
    Caches downloaded frames in memory to avoid redundant network calls.
    """
    if symbol in _HISTORY_CACHE:
        return _HISTORY_CACHE[symbol].copy()

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

        _HISTORY_CACHE[symbol] = df
        return df.copy()
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
    df["SMA50"] = df["Close"].rolling(50, min_periods=1).mean()
    df["SMA150"] = df["Close"].rolling(150, min_periods=1).mean()
    df["SMA200"] = df["Close"].rolling(200, min_periods=1).mean()

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
    sma_cross = (df["SMA150"] > df["SMA200"]) if len(df) >= 150 else True
    sma200_slope = (df["SMA200"] > df["SMA200"].shift(50)) if len(df) >= 200 else True
    df["TREND_OK"] = (
        (df["Close"] > df["SMA150"])
        & (df["Close"] > df["SMA200"])
        & sma_cross
        & sma200_slope
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
    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
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
# 5b) PREMIUM INFORMATIONAL METRICS (DIAGNOSTIC ONLY)
# =====================================================================
def compute_window_return(df: pd.DataFrame, window_bars: int) -> float:
    """
    Compute raw % return over window_bars: ((close_now - prior_close) / prior_close) * 100.
    If window has fewer bars, uses the longest available.
    """
    if df is None or len(df) < 2:
        return 0.0
    try:
        close_now = float(df["Close"].iloc[-1])
        prior_idx = max(0, len(df) - 1 - window_bars)
        prior_close = float(df["Close"].iloc[prior_idx])
        if prior_close <= 0 or pd.isna(prior_close) or pd.isna(close_now):
            return 0.0
        return float(((close_now - prior_close) / prior_close) * 100.0)
    except Exception:
        return 0.0


def compute_blended_return(df: pd.DataFrame) -> float:
    """
    blended_return = 0.4*ret_63d + 0.2*ret_126d + 0.2*ret_189d + 0.2*ret_252d
    (annualized-free, raw % over each window; if window has < its bars, uses longest available).
    """
    ret_63d = compute_window_return(df, 63)
    ret_126d = compute_window_return(df, 126)
    ret_189d = compute_window_return(df, 189)
    ret_252d = compute_window_return(df, 252)
    return float(0.4 * ret_63d + 0.2 * ret_126d + 0.2 * ret_189d + 0.2 * ret_252d)


def compute_universe_rs_ratings(symbols_blended: Dict[str, float]) -> Dict[str, Optional[int]]:
    """
    Percentile ranking (1-99) of blended returns across evaluated universe.
    rs_rating = round(100 * (#symbols with blended_return <= this symbol's) / N).
    Ties broken deterministically by symbol name ascending (stable).
    Graceful degradation: if evaluated universe N < 30, rs_rating = None.
    """
    N = len(symbols_blended)
    if N < 30:
        return {sym: None for sym in symbols_blended}

    # Deterministic sort: ascending by (blended_return, symbol)
    sorted_items = sorted(symbols_blended.items(), key=lambda item: (item[1], item[0]))
    ratings: Dict[str, Optional[int]] = {}
    for idx, (sym, _) in enumerate(sorted_items, start=1):
        raw_rs = round(100.0 * idx / N)
        clamped_rs = max(1, min(99, int(raw_rs)))
        ratings[sym] = clamped_rs
    return ratings


def compute_base_maturity(df: pd.DataFrame) -> Tuple[int, int]:
    """
    base_start_idx = index of min(Low) over last 60 bars;
    days_in_base = len(df) - 1 - base_start_idx.
    Counts successive step-downs of 10-day rolling std of (High-Low)/Close; clamp 1..4.
    Returns (base_maturity, days_in_base) as integers.
    """
    if df is None or len(df) < 2:
        return 1, 0

    try:
        window = min(60, len(df))
        sub_lows = df["Low"].iloc[-window:].values
        min_pos = int(np.argmin(sub_lows))
        base_start_idx = int((len(df) - window) + min_pos)
        days_in_base = int((len(df) - 1) - base_start_idx)

        safe_close = df["Close"].replace(0, np.nan)
        hl_c = ((df["High"] - df["Low"]) / safe_close).fillna(0)
        rolling_std = hl_c.rolling(10, min_periods=2).std().fillna(0)

        cons_slice = rolling_std.iloc[base_start_idx:].values
        if len(cons_slice) < 2:
            return 1, max(0, days_in_base)

        checkpoints = [float(cons_slice[i]) for i in range(0, len(cons_slice), 10)]
        if (len(cons_slice) - 1) not in range(0, len(cons_slice), 10):
            checkpoints.append(float(cons_slice[-1]))

        step_downs = sum(1 for i in range(1, len(checkpoints)) if checkpoints[i] < checkpoints[i - 1])
        base_maturity = max(1, min(4, 1 + step_downs))
        return int(base_maturity), max(0, int(days_in_base))
    except Exception:
        return 1, 0


def build_leaders_board(symbols: List[str], rs_ratings: Dict[str, Optional[int]]) -> List[Dict[str, Any]]:
    """
    Build leaders_board = up to 10 symbols with highest rs_rating that ALSO satisfy TREND_OK (Stage-2).
    Format: {symbol, rs_rating, close, dist_to_breakout, grade}.
    Empty list allowed if no symbols qualify or universe N < 30.
    """
    leaders: List[Dict[str, Any]] = []
    for sym in symbols:
        rs_val = rs_ratings.get(sym)
        if rs_val is None:
            if not sym.endswith(".NS"):
                rs_val = rs_ratings.get(sym + ".NS")
            else:
                rs_val = rs_ratings.get(sym[:-3])
        if rs_val is None:
            continue

        df = get_history(sym)
        if df is None or len(df) < 50:
            continue
        df = add_indicators(df)
        last_row = df.iloc[-1]
        if not bool(last_row.get("TREND_OK", False)):
            continue

        c_val = float(last_row["Close"])
        h20 = float(last_row["HIGH20"])
        if c_val <= 0 or pd.isna(h20):
            continue
        dist_bo = round(((h20 - c_val) / c_val) * 100, 2)
        diag = diagnose(sym)
        grade_val = diag.get("grade", "C") if diag else "C"
        clean_sym = sym[:-3] if sym.endswith(".NS") else sym
        leaders.append({
            "symbol": clean_sym,
            "rs_rating": int(rs_val),
            "close": round(c_val, 2),
            "dist_to_breakout": dist_bo,
            "grade": grade_val,
        })

    # Sort descending by rs_rating, secondary ascending by symbol
    leaders.sort(key=lambda x: (-x["rs_rating"], x["symbol"]))
    return leaders[:10]


# =====================================================================
# 5b) P5 GARNISH: MULTI-TF CONFLUENCE, THESIS CARD & CORRELATION
# =====================================================================
def compute_mtf_confluence(df: pd.DataFrame) -> bool:
    """
    Compute multi-timeframe confluence:
    Resample the daily history to weekly (W-FRI).
    weekly Stage-2 = w_Close > w_SMA30 and w_SMA30 rising.
    confluence = (daily TREND_OK AND weekly Stage-2) => True/False.
    Informational only; returns boolean True/False.
    """
    try:
        if df is None or len(df) < 5:
            return False

        daily_trend_ok = bool(df["TREND_OK"].iloc[-1]) if "TREND_OK" in df.columns else False
        if not daily_trend_ok:
            return False

        temp = df.copy()
        if "Date" in temp.columns:
            temp["Date"] = pd.to_datetime(temp["Date"])
            temp = temp.set_index("Date")
        elif not isinstance(temp.index, pd.DatetimeIndex):
            return bool(daily_trend_ok)

        # Resample to weekly (Friday close)
        df_w = temp.resample("W-FRI").agg({
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum"
        }).dropna(subset=["Close"])

        if len(df_w) < 2:
            return bool(daily_trend_ok)

        w_sma30 = df_w["Close"].rolling(30, min_periods=1).mean()
        w_close = float(df_w["Close"].iloc[-1])
        w_sma_now = float(w_sma30.iloc[-1])
        w_sma_prev = float(w_sma30.iloc[-2])

        weekly_stage_2 = (w_close > w_sma_now) and (w_sma_now >= w_sma_prev)
        return bool(daily_trend_ok and weekly_stage_2)
    except Exception:
        return False


def format_thesis_card(item: Dict[str, Any]) -> str:
    """
    Assemble a 4-line plain-English thesis card string ONLY from existing fields:
    Line 1: GRADE <g> | RS <rs> | Base <maturity>/4 (<days>d)
    Line 2: Trend <trend> / Setup <coiling> / Sector <bullish>
    Line 3: Inst: <footprint> | Next event: <type in Nd or none>
    Line 4: Plan: <exit_plan string> | Risk 1% (gap-capped)
    Pure formatting; if a field is None prints 'n/a'. Never compute new thresholds.
    """
    # Line 1: Grade, RS, Base
    g = item.get("grade") or item.get("Grade") or "n/a"
    rs = item.get("rs_rating")
    rs_str = str(rs) if rs is not None else "n/a"
    base_mat = item.get("base_maturity")
    base_mat_str = f"{base_mat}" if base_mat is not None else "n/a"
    days_base = item.get("days_in_base")
    days_base_str = f"{days_base}d" if days_base is not None else "n/a"
    line1 = f"GRADE {g} | RS {rs_str} | Base {base_mat_str}/4 ({days_base_str})"

    # Line 2: Trend, Setup, Sector
    trend_val = str(item.get("Trend") or ("YES" if item.get("TREND_OK") else "no")).upper()
    trend_icon = "Trend ✅" if trend_val in ["YES", "TRUE", "1"] else "Trend ❌"
    coiling_val = item.get("Coiling") or ("YES" if item.get("SETUP_OK") else "no") or "n/a"
    sec_val = item.get("SectorBullish") or ("bullish" if item.get("Sector") else "n/a")
    line2 = f"{trend_icon} / Setup Coiling: {coiling_val} / Sector {sec_val}"

    # Line 3: Inst, Next event
    inst = item.get("inst_footprint") or "unknown"
    next_ev = item.get("next_event")
    if isinstance(next_ev, dict) and next_ev.get("type"):
        ev_type = next_ev.get("type")
        d_val = next_ev.get("days_to_event")
        ev_str = f"{ev_type} in {d_val}d" if d_val is not None else f"{ev_type}"
    elif isinstance(next_ev, str) and next_ev:
        ev_str = next_ev
    else:
        ev_str = "none"
    line3 = f"Inst: {inst} | Next event: {ev_str}"

    # Line 4: Plan, Risk
    stop = item.get("Stop") or item.get("stop")
    target = item.get("Target") or item.get("target")
    if stop is not None and target is not None:
        try:
            plan_str = f"Stop ₹{float(stop):.2f} / Target ₹{float(target):.2f} (2R trail)"
        except (ValueError, TypeError):
            plan_str = "Stop / Target 2R trail"
    else:
        plan_str = "2R target partial + 20-EMA trail / 5d time-stop"
    line4 = f"Plan: {plan_str} | Risk 1% (gap-capped)"

    return f"{line1}\n{line2}\n{line3}\n{line4}"


def compute_open_positions_correlation(positions: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Pairwise 60d daily-return Pearson correlation among open positions
    + each position's beta to universe basket.
    Output correlation = {
        pairs: [{a, b, corr}],
        betas: {sym: beta},
        concentration_warning: (any pair corr > 0.7) OR (>2 positions same sector)
    }
    Graceful: < 2 open positions => pairs [] and warning False.
    """
    if not positions or len(positions) < 2:
        betas = {}
        if positions and len(positions) == 1:
            sym = positions[0].get("symbol", "")
            if sym:
                betas[sym] = 1.0
        return {
            "pairs": [],
            "betas": betas,
            "concentration_warning": False,
        }

    try:
        # 1. Fetch 60d daily returns for each open position
        returns_by_sym: Dict[str, pd.Series] = {}
        for pos in positions:
            sym = pos.get("symbol", "")
            if not sym:
                continue
            df = get_history(sym)
            if df is not None and len(df) >= 2:
                if "Date" in df.columns:
                    s_ret = df.set_index("Date")["Close"].pct_change().dropna().tail(60)
                else:
                    s_ret = df["Close"].pct_change().dropna().tail(60)
                if len(s_ret) >= 2:
                    returns_by_sym[sym] = s_ret

        sym_list = [pos.get("symbol", "") for pos in positions if pos.get("symbol", "") in returns_by_sym]

        # 2. Pairwise Pearson correlations
        pairs: List[Dict[str, Any]] = []
        for i in range(len(sym_list)):
            for j in range(i + 1, len(sym_list)):
                s_a = sym_list[i]
                s_b = sym_list[j]
                r_a = returns_by_sym[s_a]
                r_b = returns_by_sym[s_b]
                df_pair = pd.concat([r_a, r_b], axis=1, join="inner").dropna()
                if len(df_pair) >= 5 and df_pair.iloc[:, 0].std() > 1e-8 and df_pair.iloc[:, 1].std() > 1e-8:
                    c_val = float(df_pair.iloc[:, 0].corr(df_pair.iloc[:, 1]))
                    c_val = 0.0 if pd.isna(c_val) else c_val
                else:
                    c_val = 0.0
                pairs.append({"a": s_a, "b": s_b, "corr": round(c_val, 2)})

        # 3. Universe basket for beta calculation
        basket_series: List[pd.Series] = []
        symbols_pool = get_symbols()
        for sym in symbols_pool[:30]:
            df_sym = get_history(sym)
            if df_sym is not None and len(df_sym) >= 10:
                if "Date" in df_sym.columns:
                    ret_s = df_sym.set_index("Date")["Close"].pct_change().dropna().tail(60)
                else:
                    ret_s = df_sym["Close"].pct_change().dropna().tail(60)
                if len(ret_s) >= 5 and ret_s.std() > 1e-8:
                    basket_series.append(ret_s)

        if basket_series:
            basket_df = pd.concat(basket_series, axis=1, join="outer")
            basket_ret = basket_df.mean(axis=1).dropna()
        else:
            basket_ret = None

        betas: Dict[str, float] = {}
        for sym in sym_list:
            r_s = returns_by_sym[sym]
            if basket_ret is not None and len(basket_ret) >= 5:
                aligned = pd.concat([r_s, basket_ret], axis=1, join="inner").dropna()
                var_m = aligned.iloc[:, 1].var() if len(aligned) >= 5 else 0.0
                if var_m > 1e-8:
                    cov_sm = aligned.iloc[:, 0].cov(aligned.iloc[:, 1])
                    beta_val = float(cov_sm / var_m)
                    beta_val = 1.0 if pd.isna(beta_val) else beta_val
                else:
                    beta_val = 1.0
            else:
                beta_val = 1.0
            betas[sym] = round(beta_val, 2)

        # 4. Concentration Warning: (any pair corr > 0.7) OR (>2 positions same sector)
        sector_counts: Dict[str, int] = {}
        for pos in positions:
            sym = pos.get("symbol", "")
            sec = pos.get("sector") or SECTOR_MAP.get(sym, INDEX_SYMBOL)
            sector_counts[sec] = sector_counts.get(sec, 0) + 1

        high_corr = any((p.get("corr", 0.0) > 0.7) for p in pairs)
        sector_crowded = any(cnt > 2 for cnt in sector_counts.values())
        concentration_warning = bool(high_corr or sector_crowded)

        return {
            "pairs": pairs,
            "betas": betas,
            "concentration_warning": concentration_warning,
        }
    except Exception as exc:
        print(f"Warning in compute_open_positions_correlation: {exc}")
        return {
            "pairs": [],
            "betas": {},
            "concentration_warning": False,
        }


# =====================================================================
# 5c) INSTITUTIONAL FOOTPRINT (BULK/BLOCK + DELIVERY LENS)
# =====================================================================
def load_deals() -> Tuple[Dict[str, Any], bool]:
    """
    Load deals archive from deals.json.
    FAIL-OPEN HARD: Missing, corrupt, or unreadable file returns ({}, True).
    """
    if not os.path.exists(DEALS_FILE):
        return {}, True
    try:
        with open(DEALS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data, False
    except Exception as exc:
        print(f"Warning: Failed to load {DEALS_FILE} ({exc}). Marking deals stale.")
    return {}, True


def get_deal_record(deals: Dict[str, Any], date_str: str, sym: str) -> Optional[Dict[str, Any]]:
    """Retrieve deal record for symbol on a given date, supporting .NS normalization."""
    day = deals.get(date_str)
    if not isinstance(day, dict):
        return None
    if sym in day:
        return day[sym]
    clean_sym = sym[:-3] if sym.endswith(".NS") else sym
    if clean_sym in day:
        return day[clean_sym]
    ns_sym = f"{sym}.NS" if not sym.endswith(".NS") else sym
    if ns_sym in day:
        return day[ns_sym]
    return None


def classify_inst_footprint(
    symbol: str,
    df: Optional[pd.DataFrame] = None,
    deals: Optional[Dict[str, Any]] = None,
    is_stale: bool = False,
) -> str:
    """
    Classify institutional footprint into {"accumulation", "churn", "unknown"}.
    - accumulation: (delivery_pct rising vs 5d-avg AND price flat/up) OR block_print/bulk_print True in last 3 sessions.
    - churn: volume >= 1.5x avg AND delivery_pct < 25% AND no inst print.
    - unknown: no data / stale.
    INFORMATIONAL ONLY: Must NOT alter score, grade, SIGNAL, or risk math.
    """
    if is_stale or not deals:
        return "unknown"

    sorted_dates = sorted(deals.keys())
    if not sorted_dates:
        return "unknown"

    last_3_dates = sorted_dates[-3:]
    last_5_dates = sorted_dates[-5:]
    latest_date = sorted_dates[-1]

    # Check for block_print/bulk_print in last 3 sessions
    has_inst_print_last3 = False
    for d in last_3_dates:
        rec = get_deal_record(deals, d, symbol)
        if rec and (rec.get("block_print") is True or rec.get("bulk_print") is True):
            has_inst_print_last3 = True
            break

    # Delivery % history over last 5 sessions
    deliv_history = []
    for d in last_5_dates:
        rec = get_deal_record(deals, d, symbol)
        if rec and rec.get("delivery_pct") is not None:
            try:
                deliv_history.append(float(rec["delivery_pct"]))
            except (ValueError, TypeError):
                pass

    latest_rec = get_deal_record(deals, latest_date, symbol)
    latest_deliv = None
    if latest_rec and latest_rec.get("delivery_pct") is not None:
        try:
            latest_deliv = float(latest_rec["delivery_pct"])
        except (ValueError, TypeError):
            pass

    # Delivery rising vs 5d-avg
    deliv_rising = False
    if latest_deliv is not None and len(deliv_history) >= 2:
        avg_5d = sum(deliv_history) / len(deliv_history)
        deliv_rising = latest_deliv > avg_5d

    # Price flat / up: close_today >= close_prev * 0.998 (-0.2% tolerance)
    price_flat_up = False
    vol_spike = False
    if df is not None and len(df) >= 2:
        c_today = float(df["Close"].iloc[-1])
        c_prev = float(df["Close"].iloc[-2])
        if c_prev > 0:
            price_flat_up = c_today >= (c_prev * 0.998)

        if len(df) >= 50:
            vol_today = float(df["Volume"].iloc[-1])
            if "VOL50" in df.columns and not pd.isna(df["VOL50"].iloc[-1]):
                vol_avg = float(df["VOL50"].iloc[-1])
            else:
                vol_avg = float(df["Volume"].iloc[-50:].mean())
            if vol_avg > 0 and vol_today >= 1.5 * vol_avg:
                vol_spike = True

    # 1. Accumulation
    if has_inst_print_last3 or (deliv_rising and price_flat_up):
        return "accumulation"

    # 2. Churn
    if vol_spike and (latest_deliv is not None and latest_deliv < 25.0) and not has_inst_print_last3:
        return "churn"

    # 3. Unknown
    return "unknown"


# =====================================================================
# 5c) EVENT RADAR & GAP RISK
# =====================================================================
def load_events() -> Dict[str, List[Dict[str, Any]]]:
    """
    Load manual corporate events from events.json.
    FAIL-OPEN HARD: Missing, corrupt, or unreadable file returns {}.
    """
    if not os.path.exists(EVENTS_FILE):
        return {}
    try:
        with open(EVENTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception as exc:
        print(f"Warning: Failed to load {EVENTS_FILE} ({exc})")
    return {}


def fetch_next_earnings_date(symbol: str) -> Optional[str]:
    """
    Attempt auto-fetch of next earnings date from Yahoo Finance calendar.
    FAIL-OPEN: returns None on any network, rate-limit, or parsing error.
    """
    global _EARNINGS_CACHE
    if symbol in _EARNINGS_CACHE:
        return _EARNINGS_CACHE[symbol]

    try:
        ticker = yf.Ticker(symbol)
        cal = ticker.calendar
        if cal is not None:
            if isinstance(cal, dict):
                ed = cal.get("Earnings Date")
                if ed:
                    if isinstance(ed, list) and len(ed) > 0:
                        first_ed = ed[0]
                        val = first_ed.strftime("%Y-%m-%d") if hasattr(first_ed, "strftime") else str(first_ed)[:10]
                        _EARNINGS_CACHE[symbol] = val
                        return val
                    val = ed.strftime("%Y-%m-%d") if hasattr(ed, "strftime") else str(ed)[:10]
                    _EARNINGS_CACHE[symbol] = val
                    return val
            elif isinstance(cal, pd.DataFrame) and not cal.empty:
                if "Earnings Date" in cal.index:
                    vals = cal.loc["Earnings Date"].dropna().tolist()
                    if vals:
                        first_ed = vals[0]
                        val = first_ed.strftime("%Y-%m-%d") if hasattr(first_ed, "strftime") else str(first_ed)[:10]
                        _EARNINGS_CACHE[symbol] = val
                        return val
    except Exception:
        pass

    _EARNINGS_CACHE[symbol] = None
    return None


def get_symbol_events(symbol: str) -> List[Dict[str, Any]]:
    """
    Merge manual events from events.json and auto-fetched earnings into one list.
    Returns list of event dicts: {"type": str, "date": "YYYY-MM-DD", "note": str}.
    """
    clean_sym = symbol[:-3] if symbol.endswith(".NS") else symbol
    all_manual = load_events()
    sym_events: List[Dict[str, Any]] = []

    # Check clean_sym, symbol with .NS, and raw symbol
    raw_list = all_manual.get(clean_sym) or all_manual.get(f"{clean_sym}.NS") or all_manual.get(symbol) or []
    for ev in raw_list:
        if isinstance(ev, dict) and "date" in ev and "type" in ev:
            sym_events.append({
                "type": str(ev.get("type", "OTHER")).upper(),
                "date": str(ev["date"]),
                "note": str(ev.get("note", ""))
            })

    # Auto earnings from Yahoo
    earnings_date = fetch_next_earnings_date(symbol)
    if earnings_date:
        has_earnings = any(e.get("type") == "EARNINGS" and e.get("date") == earnings_date for e in sym_events)
        if not has_earnings:
            sym_events.append({
                "type": "EARNINGS",
                "date": earnings_date,
                "note": "Quarterly Financial Results"
            })

    return sym_events


def compute_next_event(symbol: str, ref_date: Optional[datetime.date] = None) -> Optional[Dict[str, Any]]:
    """
    Per symbol compute next_event {type, date, days_to_event}
    (nearest future event where days_to_event >= 0; None if none).
    """
    if ref_date is None:
        ref_date = datetime.datetime.now(IST_TZ).date()

    events = get_symbol_events(symbol)
    future_events = []
    for ev in events:
        try:
            ev_date = datetime.datetime.strptime(ev["date"], "%Y-%m-%d").date()
            diff = (ev_date - ref_date).days
            if diff >= 0:
                future_events.append({
                    "type": ev["type"],
                    "date": ev["date"],
                    "days_to_event": int(diff)
                })
        except Exception:
            continue

    if not future_events:
        return None

    future_events.sort(key=lambda x: (x["days_to_event"], x["date"]))
    return future_events[0]


def check_event_entry_blocked(symbol: str) -> Tuple[bool, Optional[str], Optional[Dict[str, Any]]]:
    """
    ENTRY gate: if days_to_event <= EARNINGS_BLACKOUT_DAYS for ANY gap-event type
    (earnings/lockin/AGM/record), BLOCK the entry.
    Unknown event (None) => allowed (not blocked).
    Returns (is_blocked, blocked_reason, next_event).
    """
    next_ev = compute_next_event(symbol)
    if next_ev and next_ev.get("days_to_event") is not None:
        days = next_ev["days_to_event"]
        if 0 <= days <= EARNINGS_BLACKOUT_DAYS:
            reason = f"Upcoming {next_ev['type']} in {days}d ({next_ev['date']})"
            return True, reason, next_ev
    return False, None, next_ev


def evaluate_open_positions_events() -> Tuple[List[Dict[str, Any]], List[str]]:
    """
    OPEN-position WARN: if a held symbol has days_to_event <= 3,
    set warn_event=True on the position record.
    Returns (positions, warn_lines).
    INFORMATIONAL ONLY: Never modifies exit math, stop, target, or time-stop.
    """
    positions = load_open_positions()
    if not positions:
        return [], []

    warn_lines: List[str] = []
    updated = False
    for pos in positions:
        sym = pos.get("symbol", "")
        next_ev = compute_next_event(sym)
        pos["next_event"] = next_ev
        df_p = get_history(sym)
        pos["mtf_confluence"] = compute_mtf_confluence(df_p) if df_p is not None else False
        if next_ev and next_ev.get("days_to_event") is not None and 0 <= next_ev["days_to_event"] <= 3:
            pos["warn_event"] = True
            clean_sym = sym[:-3] if sym.endswith(".NS") else sym
            warn_lines.append(f"🔔 {clean_sym} event ({next_ev['type']}) in {next_ev['days_to_event']} days — review hold")
        else:
            pos["warn_event"] = False
        updated = True

    if updated:
        save_open_positions(positions)

    return positions, warn_lines


def compute_landmines(
    watchlist: List[Dict[str, Any]],
    on_deck: List[Dict[str, Any]],
    open_positions: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Top-level landmines: list of {symbol, type, date, days_to_event}
    for any watchlist, on_deck, or open position symbol with an event within 7 days,
    sorted ascending by days_to_event.
    """
    candidate_symbols = set()
    for w in watchlist:
        s = w.get("Symbol") or w.get("symbol")
        if s:
            candidate_symbols.add(s)
    for o in on_deck:
        s = o.get("symbol") or o.get("Symbol")
        if s:
            candidate_symbols.add(s)
    for p in open_positions:
        s = p.get("symbol") or p.get("Symbol")
        if s:
            candidate_symbols.add(s)

    landmines: List[Dict[str, Any]] = []
    for sym in sorted(candidate_symbols):
        next_ev = compute_next_event(sym)
        if next_ev and next_ev.get("days_to_event") is not None and 0 <= next_ev["days_to_event"] <= 7:
            clean_sym = sym[:-3] if sym.endswith(".NS") else sym
            landmines.append({
                "symbol": clean_sym,
                "type": next_ev["type"],
                "date": next_ev["date"],
                "days_to_event": next_ev["days_to_event"],
            })

    landmines.sort(key=lambda x: (x["days_to_event"], x["symbol"]))
    return landmines


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


def compute_market_summary(symbols: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Diagnostic market pulse summary computed exclusively from already-cached data.
    Does NOT make any new network calls.
    Returns:
    {
      "source": INDEX_SYMBOL,
      "last_close": float,
      "prev_close": float,
      "chg_pct": float,
      "last_bar_date": str,
      "as_of_ist": str,
      "breadth_above_sma50": int,
      "breadth_above_sma200": int,
      "universe_size": int,
      "advancers": int,
      "decliners": int,
      "unchanged": int
    }
    """
    now_ist = datetime.datetime.now(IST_TZ).isoformat()

    source = INDEX_SYMBOL
    last_close = 0.0
    prev_close = 0.0
    chg_pct = 0.0
    last_bar_date = "n/a"

    idx_df = get_cached_index_df()
    if idx_df is not None and not idx_df.empty:
        try:
            if len(idx_df) >= 2:
                last_close = float(idx_df["Close"].iloc[-1])
                prev_close = float(idx_df["Close"].iloc[-2])
                if prev_close > 0:
                    chg_pct = round(((last_close - prev_close) / prev_close) * 100.0, 2)
            elif len(idx_df) == 1:
                last_close = float(idx_df["Close"].iloc[-1])
                prev_close = last_close
                chg_pct = 0.0

            if "Date" in idx_df.columns:
                last_bar_date = pd.to_datetime(idx_df["Date"].iloc[-1]).strftime("%Y-%m-%d")
            elif hasattr(idx_df.index, "strftime"):
                last_bar_date = idx_df.index[-1].strftime("%Y-%m-%d")
            else:
                last_bar_date = str(idx_df.index[-1])[:10]
        except Exception as e:
            print(f"Warning computing index in market_summary: {e}")

    if symbols is None:
        try:
            symbols = get_symbols()
        except Exception:
            symbols = []

    universe_size = len(symbols) if symbols else 0
    breadth_above_sma50 = 0
    breadth_above_sma200 = 0
    advancers = 0
    decliners = 0
    unchanged = 0

    for sym in symbols:
        df_sym = _HISTORY_CACHE.get(sym)
        if df_sym is None:
            alt_sym = sym[:-3] if sym.endswith(".NS") else f"{sym}.NS"
            df_sym = _HISTORY_CACHE.get(alt_sym)

        if df_sym is not None and len(df_sym) >= 1:
            try:
                c_last = float(df_sym["Close"].iloc[-1])
                if len(df_sym) >= 2:
                    c_prev = float(df_sym["Close"].iloc[-2])
                    if c_last > c_prev:
                        advancers += 1
                    elif c_last < c_prev:
                        decliners += 1
                    else:
                        unchanged += 1
                else:
                    unchanged += 1

                # SMA50 breadth
                sma50 = None
                if "SMA50" in df_sym.columns:
                    sma50 = df_sym["SMA50"].iloc[-1]
                elif len(df_sym) >= 50:
                    sma50 = df_sym["Close"].rolling(50).mean().iloc[-1]
                if sma50 is not None and not pd.isna(sma50) and c_last > sma50:
                    breadth_above_sma50 += 1

                # SMA200 breadth
                sma200 = None
                if "SMA200" in df_sym.columns:
                    sma200 = df_sym["SMA200"].iloc[-1]
                elif len(df_sym) >= 200:
                    sma200 = df_sym["Close"].rolling(200).mean().iloc[-1]
                if sma200 is not None and not pd.isna(sma200) and c_last > sma200:
                    breadth_above_sma200 += 1
            except Exception:
                continue

    return {
        "source": source,
        "last_close": round(last_close, 2),
        "prev_close": round(prev_close, 2),
        "chg_pct": chg_pct,
        "last_bar_date": last_bar_date,
        "as_of_ist": now_ist,
        "breadth_above_sma50": breadth_above_sma50,
        "breadth_above_sma200": breadth_above_sma200,
        "universe_size": universe_size,
        "advancers": advancers,
        "decliners": decliners,
        "unchanged": unchanged,
    }


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


def compute_risk_parameters(
    entry: float,
    atr: float,
    capital: float = CAPITAL,
    risk_pct: float = RISK_PCT,
    atr_multiplier: float = ATR_STOP_MULTIPLIER,
    target_multiple: float = TARGET_R_MULTIPLE,
    max_stop_pct: float = MAX_STOP_LOSS_PCT,
) -> Optional[Dict[str, Any]]:
    """
    Compute initial stop loss, 2R target, risk per unit, and position sizing
    according to live discipline rules. Returns None if inputs are invalid or resulting qty is 0.
    """
    if pd.isna(entry) or pd.isna(atr) or atr <= 0 or entry <= 0 or capital <= 0 or risk_pct <= 0:
        return None

    stop = entry - (atr_multiplier * atr)
    # Floor stop loss at max_stop_pct (e.g. 7% max risk from entry)
    stop = max(stop, entry * (1.0 - max_stop_pct))
    if stop >= entry:
        return None

    risk_per_unit = entry - stop
    if risk_per_unit <= 0:
        return None

    target = entry + (target_multiple * risk_per_unit)
    qty = math.floor((capital * risk_pct) / risk_per_unit)
    if qty <= 0:
        return None

    risk_amount = qty * risk_per_unit

    return {
        "entry": round(entry, 2),
        "stop": round(stop, 2),
        "target": round(target, 2),
        "qty": int(qty),
        "risk_per_unit": round(risk_per_unit, 2),
        "risk_amount": round(risk_amount, 2),
    }


def evaluate_trade_exit(
    position: Dict[str, Any],
    current_bar: pd.Series,
    holding_days: int,
) -> Optional[Dict[str, Any]]:
    """
    Mechanical exit rule evaluator for open positions (S2/S3 live rules).
    Applies:
    1) Stop loss breach (initial or ratcheted)
    2) 2R target hit (triggers 50% partial or full exit)
    3) Trailing stop (20-EMA close cross for runner after 2R or while in profit)
    4) Breakeven ratchet (if high reaches +8% or 2R, ratchet stop to entry)
    5) Per-type time stop (e.g. 5 days if gain < 3%)

    Returns an exit event dictionary if an exit or partial exit occurs, else None.
    """
    open_p = float(current_bar["Open"])
    high_p = float(current_bar["High"])
    low_p = float(current_bar["Low"])
    close_p = float(current_bar["Close"])
    ema20 = current_bar.get("EMA20")
    if ema20 is not None and not pd.isna(ema20):
        ema20 = float(ema20)
    else:
        ema20 = None

    entry_price = float(position["entry_price"])
    current_stop = float(position["current_stop"])
    target = float(position["target"])
    remaining_qty = int(position.get("remaining_qty", position["qty"]))
    partial_taken = bool(position.get("partial_taken", False))
    signal_type = str(position.get("signal_type", "BREAKOUT")).upper()

    # Track highest price achieved
    highest_price = max(float(position.get("highest_price", entry_price)), high_p)
    position["highest_price"] = highest_price

    # 1) Breakeven ratchet: move stop to entry when price reaches +8%
    if highest_price >= entry_price * 1.08:
        current_stop = max(current_stop, entry_price)
        position["current_stop"] = current_stop

    # 2) Stop loss hit check
    if low_p <= current_stop:
        # Gap-down protection: if opened below stop, exit at open; otherwise exit at stop
        exit_price = min(open_p, current_stop) if open_p < current_stop else current_stop
        return {
            "action": "STOP_LOSS",
            "exit_price": round(exit_price, 2),
            "qty": remaining_qty,
            "reason": "Stop Loss Hit",
        }

    # 3) 2R Target & Partial Exit check
    if not partial_taken and high_p >= target:
        exit_price = target
        partial_qty = position["qty"] // 2
        if partial_qty <= 0 or remaining_qty <= 1 or position["qty"] <= 1:
            return {
                "action": "TARGET_FULL",
                "exit_price": round(exit_price, 2),
                "qty": remaining_qty,
                "reason": "2R Target Reached",
            }
        else:
            position["partial_taken"] = True
            position["partial_qty"] = partial_qty
            position["remaining_qty"] = remaining_qty - partial_qty
            position["current_stop"] = max(current_stop, entry_price)
            return {
                "action": "PARTIAL_TARGET",
                "exit_price": round(exit_price, 2),
                "qty": partial_qty,
                "reason": "2R Target Partial",
            }

    # 4) Trailing stop on runner with 20-EMA (when partial taken or in profit)
    if partial_taken and ema20 is not None:
        if close_p < ema20:
            return {
                "action": "TRAIL_EXIT",
                "exit_price": round(close_p, 2),
                "qty": remaining_qty,
                "reason": "20-EMA Trail Exit",
            }

    # 5) Per-type time stop:
    # Pullback setups: 4 days without momentum
    # Breakout / Spring setups: 5 days without momentum (< +3% gain)
    time_limit = 4 if signal_type == "PULLBACK" else 5
    if holding_days >= time_limit and not partial_taken:
        gain_pct = (highest_price - entry_price) / entry_price if entry_price > 0 else 0.0
        if gain_pct < 0.03:
            return {
                "action": "TIME_STOP",
                "exit_price": round(close_p, 2),
                "qty": remaining_qty,
                "reason": "Time Stop (<3% gain)",
            }

    return None


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

    # 5) Entry, Stop Loss, Sizing and Target (via live rule function)
    entry = float(last_row["Close"])
    atr = float(last_row["ATR14"])
    risk_params = compute_risk_parameters(
        entry=entry,
        atr=atr,
        capital=CAPITAL,
        risk_pct=RISK_PCT,
    )
    if risk_params is None:
        return None

    entry = risk_params["entry"]
    stop = risk_params["stop"]
    target = risk_params["target"]
    qty = risk_params["qty"]
    risk_per_unit = risk_params["risk_per_unit"]
    risk_amount = risk_params["risk_amount"]
    sector_sym = SECTOR_MAP.get(symbol, INDEX_SYMBOL)
    base_mat, days_base = compute_base_maturity(df)
    rs_val = _RS_RATINGS.get(symbol)
    if rs_val is None:
        if not symbol.endswith(".NS"):
            rs_val = _RS_RATINGS.get(symbol + ".NS")
        else:
            rs_val = _RS_RATINGS.get(symbol[:-3])

    # 7) Event blackout filter: blocks new entry if known event within EARNINGS_BLACKOUT_DAYS
    is_event_blocked, event_blocked_reason, next_ev = check_event_entry_blocked(symbol)
    if is_event_blocked:
        print(f"Entry blocked for {symbol}: {event_blocked_reason}")
        return None

    global _DEALS, _DEALS_STALE
    if not _DEALS and not _DEALS_STALE:
        _DEALS, _DEALS_STALE = load_deals()
    inst_fp = classify_inst_footprint(symbol, df, _DEALS, _DEALS_STALE)

    sig = {
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
        "rs_rating": rs_val,
        "base_maturity": base_mat,
        "days_in_base": days_base,
        "inst_footprint": inst_fp,
        "next_event": next_ev,
        "event_blocked_reason": None,
        "mtf_confluence": compute_mtf_confluence(df),
    }
    sig["thesis_card"] = format_thesis_card(sig)
    return sig


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


_LAST_ON_DECK: List[Dict[str, Any]] = []


def format_on_deck_summary(on_deck_list: List[Dict[str, Any]], max_names: int = 3) -> str:
    """
    Format on_deck list into comma-separated symbol+dist_pct+brief_reason, max 3 names.
    e.g. 'COFORGE (+0.3%, needs vol), NYKAA (+0.8%, price pending)'
    """
    parts = []
    for item in on_deck_list[:max_names]:
        sym = item.get("symbol", "")
        sym_clean = sym[:-3] if sym.endswith(".NS") else sym
        dist = item.get("dist_pct", 0.0)
        dist_str = f"+{dist}%" if dist >= 0 else f"{dist}%"
        reason = "needs vol" if item.get("missing_condition") == "Volume too low" else "price pending"
        parts.append(f"{sym_clean} ({dist_str}, {reason})")
    return ", ".join(parts)


_LAST_ON_DECK: List[Dict[str, Any]] = []
_RS_RATINGS: Dict[str, Optional[int]] = {}
_LEADERS_BOARD: List[Dict[str, Any]] = []


def run_scanner() -> Tuple[List[Dict[str, Any]], int, bool]:
    """
    Execute the scan across all candidate symbols.
    Returns (signals, scanned_count, is_market_ok).
    """
    global _LAST_ON_DECK, _RS_RATINGS, _LEADERS_BOARD, _INST_SUMMARY, _DEALS, _DEALS_STALE, _LANDMINES
    _LAST_ON_DECK = []
    _RS_RATINGS = {}
    _LEADERS_BOARD = []
    _LANDMINES = []
    _DEALS, _DEALS_STALE = load_deals()
    _INST_SUMMARY = {"accumulation": 0, "churn": 0, "unknown": 0}
    on_deck: List[Dict[str, Any]] = []

    print("Checking market regime filter...")
    is_mkt_ok = market_ok()
    settings = load_alert_settings()
    is_digest = settings.get("digest", False)

    if not is_mkt_ok:
        msg = "🔴 MARKET FILTER: Index not in uptrend. No new entries today (O'Neil M-rule)."
        print(msg)
        if is_digest:
            _DIGEST_MESSAGES.append(("market", msg))
        else:
            send_telegram(msg, kind="proactive", msg_type="market")
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

        # On-deck diagnostic near-miss evaluation (does not alter signal calculation)
        try:
            df_sym = get_history(sym)
            if df_sym is not None and len(df_sym) >= 50:
                df_sym = add_indicators(df_sym)
                last_row = df_sym.iloc[-1]
                t_ok = bool(last_row.get("TREND_OK", False))
                s_ok = bool(last_row.get("SETUP_OK", False))
                sec_is_ok = bool(sector_ok(sym))
                if t_ok and s_ok and sec_is_ok:
                    brk = bool(last_row.get("BREAKOUT", False))
                    v_spk = bool(last_row.get("VOL_SPIKE", False))
                    if not brk or not v_spk:
                        l_close = float(last_row["Close"])
                        p_high = float(last_row["HIGH20"])
                        if l_close > 0 and not pd.isna(p_high):
                            d_pct = round((p_high - l_close) / l_close * 100, 2)
                            m_cond = "Volume too low" if brk else "Price not broken"
                            a_val = round(float(last_row["ATR14"]), 2) if ("ATR14" in last_row and not pd.isna(last_row["ATR14"])) else None
                            r_val = round(float(last_row["RSI14"]), 1) if ("RSI14" in last_row and not pd.isna(last_row["RSI14"])) else None
                            base_mat, days_base = compute_base_maturity(df_sym)
                            inst_fp = classify_inst_footprint(sym, df_sym, _DEALS, _DEALS_STALE)
                            is_ev_blocked, ev_blocked_reason, next_ev = check_event_entry_blocked(sym)
                            od_item = {
                                "symbol": sym,
                                "close": round(l_close, 2),
                                "breakout_level": round(p_high, 2),
                                "dist_pct": d_pct,
                                "missing_condition": m_cond,
                                "atr14": a_val,
                                "rsi14": r_val,
                                "rs_rating": None,
                                "base_maturity": base_mat,
                                "days_in_base": days_base,
                                "inst_footprint": inst_fp,
                                "next_event": next_ev,
                                "event_blocked_reason": ev_blocked_reason,
                                "mtf_confluence": compute_mtf_confluence(df_sym),
                            }
                            od_item["thesis_card"] = format_thesis_card(od_item)
                            on_deck.append(od_item)
        except Exception as exc:
            print(f"Diagnostic on_deck check error for {sym}: {exc}")
        time.sleep(0.25)

    # 1. Deterministically compute universe RS ratings (reusing in-memory cached history)
    blended_returns: Dict[str, float] = {}
    for sym in symbols:
        df_sym = get_history(sym)
        if df_sym is not None and len(df_sym) >= 50:
            blended_returns[sym] = compute_blended_return(df_sym)

    _RS_RATINGS = compute_universe_rs_ratings(blended_returns)

    # 2. Attach rs_rating to signals and on_deck and refresh thesis_card
    for sig in signals:
        s_name = sig.get("Symbol", "")
        r_val = _RS_RATINGS.get(s_name)
        if r_val is None:
            r_val = _RS_RATINGS.get(s_name + ".NS" if not s_name.endswith(".NS") else s_name[:-3])
        sig["rs_rating"] = r_val
        sig["thesis_card"] = format_thesis_card(sig)

    for od in on_deck:
        s_name = od.get("symbol", "")
        r_val = _RS_RATINGS.get(s_name)
        if r_val is None:
            r_val = _RS_RATINGS.get(s_name + ".NS" if not s_name.endswith(".NS") else s_name[:-3])
        od["rs_rating"] = r_val
        od["thesis_card"] = format_thesis_card(od)

    # 3. Build top-level leaders board
    _LEADERS_BOARD = build_leaders_board(symbols, _RS_RATINGS)

    # 4. Compute universe institutional footprint summary
    summary_counts = {"accumulation": 0, "churn": 0, "unknown": 0}
    for sym in symbols:
        df_sym = get_history(sym)
        fp = classify_inst_footprint(sym, df_sym, _DEALS, _DEALS_STALE)
        summary_counts[fp] = summary_counts.get(fp, 0) + 1
    _INST_SUMMARY = summary_counts

    on_deck.sort(key=lambda x: x["dist_pct"])
    on_deck = on_deck[:5]
    _LAST_ON_DECK = on_deck

    # Evaluate open positions and compute landmines
    open_pos, warn_lines = evaluate_open_positions_events()
    _LANDMINES = compute_landmines([], on_deck, open_pos)

    # Identify accumulation symbols among signals and on-deck
    acc_syms = []
    for sig in signals:
        if sig.get("inst_footprint") == "accumulation":
            s_name = sig.get("Symbol", "")
            clean_s = s_name[:-3] if s_name.endswith(".NS") else s_name
            if clean_s not in acc_syms:
                acc_syms.append(clean_s)
    for od in on_deck:
        if od.get("inst_footprint") == "accumulation":
            s_name = od.get("symbol", "")
            clean_s = s_name[:-3] if s_name.endswith(".NS") else s_name
            if clean_s not in acc_syms:
                acc_syms.append(clean_s)

    inst_line = ""
    if acc_syms:
        inst_line = f"🏦 Institutional: {len(acc_syms)} accumulation among signals/on-deck (e.g. {', '.join(acc_syms[:2])})."

    warn_block = f"\n\n{chr(10).join(warn_lines)}" if warn_lines else ""

    if messages:
        joined_message = "\n\n----\n\n".join(messages)
        if len(on_deck) > 0:
            od_summary = format_on_deck_summary(on_deck, 3)
            if is_digest:
                joined_message += f"\n\n🎯 Near Misses:\n{od_summary}."
            else:
                joined_message += f"\n\n----\n\n🎯 On Deck (near misses): {od_summary}."
        if inst_line:
            joined_message += f"\n\n{inst_line}"
        if warn_lines:
            joined_message += warn_block
        if is_digest:
            _DIGEST_MESSAGES.append(("scan", joined_message))
        else:
            send_telegram(joined_message, kind="proactive", msg_type="scan")
    elif len(signals) == 0:
        extra_inst = f"\n\n{inst_line}" if inst_line else ""
        if len(on_deck) > 0:
            od_summary = format_on_deck_summary(on_deck, 3)
            if is_digest:
                digest_msg = f"No new midcap swing signals today.\n\n🎯 Near Misses:\n{od_summary}.{extra_inst}{warn_block}"
                _DIGEST_MESSAGES.append(("scan", digest_msg))
            else:
                evening_msg = f"No new midcap swing signals today.\n\n🎯 On Deck (near misses): {od_summary}.{extra_inst}{warn_block}"
                send_telegram(evening_msg, kind="proactive", msg_type="scan")
        elif SEND_NO_SIGNAL_MESSAGE:
            no_sig_msg = f"No new midcap swing signals today.{extra_inst}{warn_block}"
            if is_digest:
                _DIGEST_MESSAGES.append(("scan", no_sig_msg))
            else:
                send_telegram(no_sig_msg, kind="proactive", msg_type="scan")

    return signals, total, True


# =====================================================================
# 9) WATCHLIST GENERATOR
# =====================================================================
def diagnose_from_dataframe(df: pd.DataFrame, symbol: str) -> Optional[Dict[str, Any]]:
    """
    Diagnose a symbol's trend, coiling status, and breakout proximity from an existing DataFrame.
    """
    if df is None or len(df) < 50:
        return None

    if "HIGH20" not in df.columns or "TREND_OK" not in df.columns:
        df = add_indicators(df)
    last_row = df.iloc[-1]

    close_val = float(last_row["Close"])
    high20_val = float(last_row["HIGH20"])
    if pd.isna(close_val) or close_val <= 0 or pd.isna(high20_val):
        return None

    sym_name = symbol[:-3] if symbol.endswith(".NS") else symbol
    sec_sym = SECTOR_MAP.get(symbol, INDEX_SYMBOL)
    sec_ok = sector_ok(symbol)
    sec_bullish = "YES" if sec_ok else "no"
    trend_ok = bool(last_row["TREND_OK"])
    trend_str = "YES" if trend_ok else "no"
    setup_ok = bool(last_row["SETUP_OK"])
    coiling_str = "YES" if setup_ok else "no"
    dist_pct = round(((high20_val - close_val) / close_val) * 100, 2)

    # Composite Setup Score (0-100) & Grade
    #   +25 if TREND_OK
    #   +20 if DistToBreakout% < 2 (scale: 20 * max(0, 1 - dist/5))
    #   +15 if SETUP_OK (coiling today)
    #   +15 if sector_ok(symbol) is True
    #   +10 if VOL_DRYUP
    #   +10 if 40 <= RSI14 <= 65
    #   + 5 if market_ok() else cap the total at 50
    # Clamp to 0-100.
    trend_pts = 25 if trend_ok else 0

    dist = max(0.0, float(dist_pct))
    dist_pts = min(20.0, max(0.0, 20.0 * max(0.0, 1.0 - (dist / 5.0))))

    setup_pts = 15 if setup_ok else 0
    sector_pts = 15 if sec_ok else 0

    vol_dryup = bool(last_row.get("VOL_DRYUP", False))
    vol_pts = 10 if vol_dryup else 0

    rsi_val = last_row.get("RSI14")
    rsi_in_range = False
    if rsi_val is not None and not pd.isna(rsi_val):
        rsi_in_range = (40.0 <= float(rsi_val) <= 65.0)
    rsi_pts = 10 if rsi_in_range else 0

    mkt_ok = bool(market_ok())
    raw_score = trend_pts + dist_pts + setup_pts + sector_pts + vol_pts + rsi_pts
    if mkt_ok:
        raw_score += 5
    else:
        raw_score = min(raw_score, 50.0)

    score = int(round(max(0.0, min(100.0, raw_score))))

    # Grade: A+ if score>=80 and sector bullish and market ok; A if score>=70 and sector bullish; B if score>=60; else C.
    if score >= 80 and sec_ok and mkt_ok:
        grade = "A+"
    elif score >= 70 and sec_ok:
        grade = "A"
    elif score >= 60:
        grade = "B"
    else:
        grade = "C"

    base_mat, days_base = compute_base_maturity(df)
    rs_val = _RS_RATINGS.get(symbol)
    if rs_val is None:
        if not symbol.endswith(".NS"):
            rs_val = _RS_RATINGS.get(symbol + ".NS")
        else:
            rs_val = _RS_RATINGS.get(symbol[:-3])

    global _DEALS, _DEALS_STALE
    if not _DEALS and not _DEALS_STALE:
        _DEALS, _DEALS_STALE = load_deals()
    inst_fp = classify_inst_footprint(symbol, df, _DEALS, _DEALS_STALE)
    is_ev_blocked, ev_blocked_reason, next_ev = check_event_entry_blocked(symbol)

    diag_dict = {
        "Symbol": sym_name,
        "Sector": sec_sym,
        "SectorBullish": sec_bullish,
        "Trend": trend_str,
        "Coiling": coiling_str,
        "DistToBreakout%": dist_pct,
        "Close": round(close_val, 2),
        "VolDryup": "YES" if vol_dryup else "no",
        "RsiInRange": "YES" if rsi_in_range else "no",
        "RSI14": round(float(rsi_val), 1) if (rsi_val is not None and not pd.isna(rsi_val)) else None,
        "ATR14": round(float(last_row["ATR14"]), 2) if ("ATR14" in last_row and not pd.isna(last_row["ATR14"])) else None,
        "score": score,
        "grade": grade,
        "Score": score,
        "Grade": grade,
        "rs_rating": rs_val,
        "base_maturity": base_mat,
        "days_in_base": days_base,
        "inst_footprint": inst_fp,
        "next_event": next_ev,
        "event_blocked_reason": ev_blocked_reason,
        "mtf_confluence": compute_mtf_confluence(df),
    }
    diag_dict["thesis_card"] = format_thesis_card(diag_dict)
    return diag_dict


def diagnose(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Diagnose a symbol's trend, coiling status, and breakout proximity.
    """
    df = get_history(symbol)
    if df is None or len(df) < 50:
        return None
    return diagnose_from_dataframe(df, symbol)


def get_watchlist_candidates() -> List[Dict[str, Any]]:
    """
    Scan symbols to build a watchlist of stocks in an uptrend near breakout.
    Returns list of diagnose() dicts with Trend YES and DistToBreakout% <= 5.0,
    sorted by score descending.
    """
    symbols = get_symbols()
    watchlist_candidates: List[Dict[str, Any]] = []

    print("Building watchlist...")
    for sym in symbols:
        diag = diagnose(sym)
        if diag and diag["Trend"] == "YES" and diag["DistToBreakout%"] <= 5.0:
            watchlist_candidates.append(diag)
        time.sleep(0.2)

    # Sort descending by score, secondary ascending by distance to breakout
    watchlist_candidates.sort(key=lambda x: (-x.get("score", 0), x.get("DistToBreakout%", 999.0)))
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
        score_val = item.get("score", item.get("Score", "-"))
        grade_val = item.get("grade", item.get("Grade", "-"))
        line = (
            f"{item['Symbol']} [Grade {grade_val} | Score {score_val}] | {sec_info} | "
            f"{item['DistToBreakout%']}% away | Close {item['Close']} | Coiling: {item['Coiling']}"
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
    """Save open positions to open_positions.json with correlation analysis."""
    corr = compute_open_positions_correlation(data)
    for pos in data:
        pos["correlation"] = corr
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
                "🤖 SWING TRADING BOT COMMANDS:\n\n"
                "• /buy SYMBOL ENTRY QTY [STOP] [TARGET] [#tags...]\n"
                "  Record a new open swing trade position.\n"
                "  Example: /buy PERSISTENT 5200 10 4950 5700 #breakout #plan_followed\n\n"
                "• /sell SYMBOL EXIT [NOTE] [#tags...]\n"
                "  Close an open position and log PnL & discipline audit.\n"
                "  Example: /sell PERSISTENT 5600 hit target 2R #plan_followed\n\n"
                "• /open\n"
                "  List all current open swing positions.\n"
                "  Example: /open\n\n"
                "• /trades\n"
                "  List the last 10 closed trades with tags & notes.\n"
                "  Example: /trades\n\n"
                "• /stats\n"
                "  View journal metrics: win rate, expectancy, drawdown & discipline.\n"
                "  Example: /stats\n\n"
                "• /mute [duration]\n"
                "  Temporarily silence all alerts and command replies (default 8h).\n"
                "  Example: /mute 4h (or: /mute 30m, /mute until 07:00)\n\n"
                "• /unmute\n"
                "  Cancel active mute and restore alerts immediately.\n"
                "  Example: /unmute\n\n"
                "• /quiet START END | /quiet off\n"
                "  Set daily quiet window (HH:MM IST) or disable it.\n"
                "  Example: /quiet 21:00 08:00 (or: /quiet off)\n\n"
                "• /alerts [scan|watchlist|market|digest on|off]\n"
                "  View alert configuration or toggle specific alert channels.\n"
                "  Example: /alerts (or: /alerts scan off, /alerts digest on)\n\n"
                "• /help\n"
                "  Show this commands help menu.\n"
                "  Example: /help"
            )

        elif cmd == "/buy":
            # Usage: /buy SYMBOL ENTRY_PRICE QTY [STOP] [TARGET] [#tag1 #tag2 ...]
            tags = [arg.strip() for arg in args if arg.strip().startswith("#")]
            non_tag_args = [arg for arg in args if not arg.strip().startswith("#")]

            if len(non_tag_args) < 3:
                return "⚠️ Usage: /buy SYMBOL ENTRY_PRICE QTY [STOP] [TARGET] [#tag1 #tag2 ...]\nExample: /buy PERSISTENT 5200 10 4950 5700 #breakout #plan_followed"

            raw_sym = non_tag_args[0].strip().upper()
            sym = raw_sym if raw_sym.endswith(".NS") else f"{raw_sym}.NS"

            try:
                entry_price = float(non_tag_args[1])
                qty = int(float(non_tag_args[2]))
            except ValueError:
                return "⚠️ Invalid format: Entry price and quantity must be valid numbers."

            if entry_price <= 0 or qty <= 0:
                return "⚠️ Entry price and quantity must be positive numbers."

            stop = None
            target = None
            if len(non_tag_args) >= 4:
                try:
                    stop = float(non_tag_args[3])
                except ValueError:
                    return "⚠️ Invalid format: Stop loss must be a number."
            if len(non_tag_args) >= 5:
                try:
                    target = float(non_tag_args[4])
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
                "planned_stop": round(stop, 2) if stop is not None else None,
                "target": round(target, 2) if target is not None else None,
                "tags": tags,
            }
            open_positions.append(new_pos)
            save_open_positions(open_positions)

            stop_str = f"₹{stop:,.2f}" if stop is not None else "None"
            target_str = f"₹{target:,.2f}" if target is not None else "None"
            tags_line = f"\nTags: {' '.join(tags)}" if tags else ""

            return (
                f"✅ POSITION OPENED:\n"
                f"Symbol: {sym}\n"
                f"Entry: ₹{entry_price:,.2f} | Qty: {qty}\n"
                f"Stop: {stop_str} | Target: {target_str}\n"
                f"Date: {today_str}"
                f"{tags_line}"
            )

        elif cmd == "/sell":
            # Usage: /sell SYMBOL EXIT_PRICE [NOTE] [#tag1 #tag2 ...]
            sell_tags = [arg.strip() for arg in args if arg.strip().startswith("#")]
            non_tag_args = [arg for arg in args if not arg.strip().startswith("#")]

            if len(non_tag_args) < 2:
                return "⚠️ Usage: /sell SYMBOL EXIT_PRICE [NOTE] [#tag1 #tag2 ...]\nExample: /sell PERSISTENT 5600 Exited at 2R target #plan_followed"

            raw_sym = non_tag_args[0].strip().upper()
            search_sym = raw_sym[:-3] if raw_sym.endswith(".NS") else raw_sym

            try:
                exit_price = float(non_tag_args[1])
            except ValueError:
                return "⚠️ Invalid format: Exit price must be a valid number."

            note = " ".join(non_tag_args[2:]).strip() if len(non_tag_args) > 2 else ""

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
            planned_stop = matched_pos.get("planned_stop", stop_val)
            target_val = matched_pos.get("target")

            pnl = (exit_price - entry_price) * qty
            pnl_pct = ((exit_price - entry_price) / entry_price) * 100.0 if entry_price > 0 else 0.0

            r_mult = None
            if stop_val is not None:
                risk_per_unit = entry_price - float(stop_val)
                if abs(risk_per_unit) > 1e-4:
                    r_mult = (exit_price - entry_price) / risk_per_unit

            today_str = datetime.date.today().isoformat()

            # Holding period calculation
            holding_days = 0
            try:
                d_entry = datetime.date.fromisoformat(str(entry_date)[:10])
                d_exit = datetime.date.fromisoformat(str(today_str)[:10])
                holding_days = (d_exit - d_entry).days
            except Exception:
                holding_days = 0

            # Tags handling (combine buy tags and sell tags without duplicates)
            pos_tags = matched_pos.get("tags") or []
            if not isinstance(pos_tags, list):
                pos_tags = []
            combined_tags = list(dict.fromkeys(pos_tags + sell_tags))

            # Mistake tracking
            # 1) If exit price is worse than planned_stop: "stop_moved"
            # 2) If held more than 5 days with return under 3%: "time_stop_ignored"
            # 3) Otherwise mistake is null
            mistake = None
            planned_stop_num = None
            if planned_stop is not None:
                try:
                    planned_stop_num = float(planned_stop)
                except (ValueError, TypeError):
                    planned_stop_num = None

            if planned_stop_num is not None and exit_price < planned_stop_num:
                mistake = "stop_moved"
            elif holding_days > 5 and pnl_pct < 3.0:
                mistake = "time_stop_ignored"

            closed_trade = {
                "symbol": matched_pos["symbol"],
                "entry_date": entry_date,
                "entry_price": round(entry_price, 2),
                "qty": qty,
                "stop": round(float(stop_val), 2) if stop_val is not None else None,
                "planned_stop": round(planned_stop_num, 2) if planned_stop_num is not None else None,
                "target": round(float(target_val), 2) if target_val is not None else None,
                "exit_date": today_str,
                "exit_price": round(exit_price, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2),
                "r_multiple": round(r_mult, 2) if r_mult is not None else None,
                "note": note,
                "tags": combined_tags,
                "mistake": mistake,
            }

            trades = load_trades()
            trades.append(closed_trade)
            save_trades(trades)

            sign = "+" if pnl >= 0 else ""
            r_str = f"{r_mult:+.2f}R" if r_mult is not None else "N/A"
            note_str = f"\nNote: {note}" if note else ""
            tags_str = f"\nTags: {' '.join(combined_tags)}" if combined_tags else ""
            mistake_str = f"\n⚠️ Mistake: {mistake}" if mistake else ""

            return (
                f"🎯 POSITION CLOSED:\n"
                f"Symbol: {closed_trade['symbol']}\n"
                f"Entry: ₹{entry_price:,.2f} ({entry_date}) -> Exit: ₹{exit_price:,.2f} ({today_str})\n"
                f"Qty: {qty}\n"
                f"PnL: {sign}₹{pnl:,.2f} ({sign}{pnl_pct:.2f}%)\n"
                f"R-Multiple: {r_str}"
                f"{note_str}"
                f"{tags_str}"
                f"{mistake_str}"
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
                tags_str = f" | Tags: {' '.join(p['tags'])}" if p.get("tags") else ""
                lines.append(f"{i}) {sym_clean} (Qty: {q}){tags_str}")
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
                tag_line = f" | Tags: {' '.join(t.get('tags', []))}" if t.get("tags") else ""
                mistake_line = f" | ⚠️ {t.get('mistake')}" if t.get("mistake") else ""
                lines.append(
                    f"• {t['symbol']}: {sign}₹{pnl:,.2f} ({sign}{t['pnl_pct']:.1f}%) | R: {r_str}{tag_line}{mistake_line}\n"
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

            # Tag & Mistake stats
            breakout_trades = [t for t in trades if "#breakout" in [tag.lower() for tag in (t.get("tags") or [])]]
            pullback_trades = [t for t in trades if "#pullback" in [tag.lower() for tag in (t.get("tags") or [])]]
            plan_trades = [t for t in trades if "#plan_followed" in [tag.lower() for tag in (t.get("tags") or [])]]
            mistake_trades = [t for t in trades if t.get("mistake")]

            breakout_wr = (len([t for t in breakout_trades if t["pnl"] > 0]) / len(breakout_trades) * 100) if breakout_trades else 0.0
            pullback_wr = (len([t for t in pullback_trades if t["pnl"] > 0]) / len(pullback_trades) * 100) if pullback_trades else 0.0
            plan_wr = (len([t for t in plan_trades if t["pnl"] > 0]) / len(plan_trades) * 100) if plan_trades else 0.0

            discipline_lines = [
                f"\n🎯 SETUP & DISCIPLINE AUDIT:",
                f"• #breakout Win Rate: {breakout_wr:.1f}% ({len(breakout_trades)} trades)" if breakout_trades else "• #breakout: 0 trades",
                f"• #pullback Win Rate: {pullback_wr:.1f}% ({len(pullback_trades)} trades)" if pullback_trades else "• #pullback: 0 trades",
                f"• #plan_followed Win Rate: {plan_wr:.1f}% ({len(plan_trades)} trades)" if plan_trades else "• #plan_followed: 0 trades",
                f"• Recorded Mistakes: {len(mistake_trades)}"
            ]

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
                f"• Worst Trade: {worst_sign}₹{worst_trade:,.2f}\n"
                + "\n".join(discipline_lines)
            )

        elif cmd == "/mute":
            # Usage: /mute [duration] e.g. /mute 4h, /mute 30m, /mute until 07:00; default 8h.
            settings = load_alert_settings()
            now_ist = get_now_ist()
            arg_str = " ".join(args).strip().lower()

            target_dt = None
            if not arg_str:
                target_dt = now_ist + datetime.timedelta(hours=8)
            elif arg_str.startswith("until"):
                time_str = arg_str.replace("until", "").strip()
                match = re.match(r"^(\d{1,2}):(\d{2})$", time_str)
                if not match:
                    return "⚠️ Invalid format for /mute until. Example: /mute until 07:00"
                h, m = int(match.group(1)), int(match.group(2))
                if not (0 <= h <= 23 and 0 <= m <= 59):
                    return "⚠️ Invalid time: Hour must be 00-23, minute 00-59."
                target_dt = now_ist.replace(hour=h, minute=m, second=0, microsecond=0)
                if target_dt <= now_ist:
                    target_dt += datetime.timedelta(days=1)
            else:
                match = re.match(r"^(\d+(?:\.\d+)?)\s*(h|m|d)$", arg_str)
                if match:
                    val = float(match.group(1))
                    unit = match.group(2)
                    if unit == "h":
                        target_dt = now_ist + datetime.timedelta(hours=val)
                    elif unit == "m":
                        target_dt = now_ist + datetime.timedelta(minutes=val)
                    elif unit == "d":
                        target_dt = now_ist + datetime.timedelta(days=val)
                else:
                    return "⚠️ Invalid mute duration. Examples: /mute 4h, /mute 30m, /mute until 07:00, or /mute (defaults to 8h)"

            settings["mute_until"] = target_dt.isoformat()
            save_alert_settings(settings)
            formatted_time = target_dt.strftime("%H:%M IST (%d %b)")
            return f"Muted until {formatted_time}. /unmute to cancel."

        elif cmd == "/unmute":
            settings = load_alert_settings()
            settings["mute_until"] = None
            save_alert_settings(settings)
            return "🔔 Unmuted. Alerts and replies restored."

        elif cmd == "/quiet":
            # Usage: /quiet START END (e.g. /quiet 21:00 08:00) or /quiet off
            settings = load_alert_settings()
            if not args:
                q_s = settings.get("quiet_start")
                q_e = settings.get("quiet_end")
                if q_s and q_e and q_s != "off" and q_e != "off":
                    return f"🌙 Current quiet window: {q_s} - {q_e} IST.\nUsage: /quiet START END (e.g. /quiet 21:00 08:00) or /quiet off"
                return "🌙 Quiet window is currently disabled.\nUsage: /quiet START END (e.g. /quiet 21:00 08:00)"

            if len(args) == 1 and args[0].lower() == "off":
                settings["quiet_start"] = "off"
                settings["quiet_end"] = "off"
                save_alert_settings(settings)
                return "🌙 Quiet window disabled. Proactive alerts allowed at any hour."

            if len(args) == 2:
                start_raw, end_raw = args[0].strip(), args[1].strip()
                time_pat = r"^([01]?\d|2[0-3]):([0-5]\d)$"
                m_start = re.match(time_pat, start_raw)
                m_end = re.match(time_pat, end_raw)
                if not m_start or not m_end:
                    return "⚠️ Invalid format: /quiet START END must use HH:MM (e.g. /quiet 21:00 08:00) or /quiet off"

                start_str = f"{int(m_start.group(1)):02d}:{m_start.group(2)}"
                end_str = f"{int(m_end.group(1)):02d}:{m_end.group(2)}"

                settings["quiet_start"] = start_str
                settings["quiet_end"] = end_str
                save_alert_settings(settings)
                return f"🌙 Quiet window set to {start_str} - {end_str} IST."

            return "⚠️ Usage: /quiet START END (e.g. /quiet 21:00 08:00) or /quiet off"

        elif cmd == "/alerts":
            # Usage:
            # /alerts -> show current status
            # /alerts scan on|off
            # /alerts watchlist on|off
            # /alerts market on|off
            # /alerts digest on|off
            settings = load_alert_settings()

            if not args:
                now_ist = get_now_ist()
                mute_str = "Off (not muted)"
                mute_until_val = settings.get("mute_until")
                if mute_until_val:
                    try:
                        mute_dt = datetime.datetime.fromisoformat(mute_until_val)
                        if mute_dt.tzinfo is None:
                            mute_dt = mute_dt.replace(tzinfo=IST_TZ)
                        if now_ist < mute_dt:
                            mute_str = f"Muted until {mute_dt.strftime('%H:%M IST (%d %b)')}"
                    except Exception:
                        pass

                q_s = settings.get("quiet_start")
                q_e = settings.get("quiet_end")
                if q_s and q_e and q_s != "off" and q_e != "off":
                    quiet_str = f"{q_s} - {q_e} IST"
                else:
                    quiet_str = "Disabled (proactive alerts allowed any hour)"

                quiet_env_active = (os.getenv("QUIET", "0").strip() == "1")
                quiet_env_str = "ACTIVE (forcing silence)" if quiet_env_active else "Inactive"

                en = settings.get("enable", {})
                scan_en = "ON" if en.get("scan", True) else "OFF"
                wl_en = "ON" if en.get("watchlist", True) else "OFF"
                mkt_en = "ON" if en.get("market", True) else "OFF"
                digest_en = "ON" if settings.get("digest", False) else "OFF"

                return (
                    "⚙️ TELEGRAM ALERT SETTINGS:\n\n"
                    f"• Mute State: {mute_str}\n"
                    f"• Quiet Window: {quiet_str}\n"
                    f"• QUIET Env: {quiet_env_str}\n"
                    f"• Scan Alerts: {scan_en}\n"
                    f"• Watchlist Alerts: {wl_en}\n"
                    f"• Market Alerts: {mkt_en}\n"
                    f"• Digest Mode: {digest_en}\n\n"
                    "Commands to modify:\n"
                    "• /mute [duration] | /unmute\n"
                    "• /quiet START END | /quiet off\n"
                    "• /alerts scan on|off\n"
                    "• /alerts watchlist on|off\n"
                    "• /alerts market on|off\n"
                    "• /alerts digest on|off"
                )

            subcmd = args[0].lower()
            if len(args) < 2:
                return "⚠️ Usage: /alerts scan on|off, /alerts watchlist on|off, /alerts market on|off, /alerts digest on|off"

            state_val = args[1].lower()
            if state_val not in ("on", "off"):
                return f"⚠️ Invalid option '{args[1]}': choose 'on' or 'off'."

            bool_val = (state_val == "on")

            if subcmd in ("scan", "watchlist", "market"):
                if "enable" not in settings or not isinstance(settings["enable"], dict):
                    settings["enable"] = dict(DEFAULT_ALERT_SETTINGS["enable"])
                settings["enable"][subcmd] = bool_val
                save_alert_settings(settings)
                status_icon = "✅" if bool_val else "⏸️"
                return f"{status_icon} Alerts for '{subcmd}' set to {state_val.upper()}."

            elif subcmd == "digest":
                settings["digest"] = bool_val
                save_alert_settings(settings)
                status_icon = "✅" if bool_val else "⏸️"
                desc = "evening alerts combined into 1 message" if bool_val else "alerts sent individually"
                return f"{status_icon} Digest mode set to {state_val.upper()} ({desc})."

            else:
                return f"⚠️ Unknown alerts sub-command: '{subcmd}'. Choose scan, watchlist, market, or digest."

        else:
            return f"❓ Unknown command: {cmd}\nType /help to see all available commands."

    except Exception as exc:
        print(f"Error handling command '{text}': {exc}")
        return f"⚠️ Error processing command: {exc}"


def select_new_updates(
    updates: List[Dict[str, Any]],
    offset: Optional[int]
) -> Tuple[List[Dict[str, Any]], Optional[int]]:
    """
    Pure helper to partition incoming Telegram updates according to persistent offset bookmark.
    - If offset is None (first run / lost bookmark / silent baseline):
        returns ([], max(update_id)+1) if updates exist, else ([], None).
    - If offset is valid (int):
        returns only updates with id > offset, and new_offset = max(their ids)+1 (or offset if none);
        older/equal ids are ignored.
    - If empty updates list:
        returns ([], offset).
    """
    if not updates:
        return [], offset

    if offset is None:
        valid_ids = [u["update_id"] for u in updates if isinstance(u, dict) and u.get("update_id") is not None]
        if not valid_ids:
            return [], None
        return [], max(valid_ids) + 1

    new_items = [
        u for u in updates
        if isinstance(u, dict) and u.get("update_id") is not None and u["update_id"] > offset
    ]
    if new_items:
        new_offset = max(u["update_id"] for u in new_items) + 1
        return new_items, new_offset
    return [], offset


def poll_once() -> None:
    """
    Check for new Telegram updates, execute any commands, and update offset.
    Follows silent baseline rule: if offset file was missing/empty, establishes
    the baseline without replying, commits tg_offset.txt, and skips the reply phase.
    """
    last_offset = load_tg_offset()

    # SILENT BASELINE RULE
    if last_offset is None:
        print(f"No persistent offset found in {TG_OFFSET_FILE}. Establishing silent baseline...")
        updates = get_updates(offset=None)
        _, new_offset = select_new_updates(updates, None)
        if new_offset is not None:
            save_tg_offset(new_offset)
            print(f"Silent baseline established: offset bookmark set to {new_offset}. Skipping reply phase entirely.")
            git_commit_listener_updates("Establish Telegram silent baseline offset [skip ci]")
        else:
            print("Silent baseline: No pending Telegram updates found.")
        return

    # Valid offset exists -> process new updates
    updates = get_updates(offset=last_offset)
    if not updates:
        return

    # In Telegram, last_offset in tg_offset.txt is already highest_id + 1.
    # Passing (last_offset - 1) as the reference offset to select_new_updates ensures:
    # (1) Any update with id >= last_offset is captured as new.
    # (2) Any older update with id <= last_offset - 1 is safely ignored.
    new_updates, new_offset = select_new_updates(updates, last_offset - 1)

    for update in new_updates:
        message = update.get("message") or update.get("channel_post")
        if not message:
            continue

        text = message.get("text")
        chat = message.get("chat") or {}
        chat_id = chat.get("id")

        if text and chat_id:
            reply = handle_command(text, chat_id)
            if reply:
                send_telegram(reply, kind="reply")

    if new_offset is not None and new_offset != last_offset:
        save_tg_offset(new_offset)
        git_commit_listener_updates("Auto-update Telegram offset and journal [skip ci]")


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


def git_commit_and_push(files: List[str], commit_message: str) -> bool:
    """
    Robust git helper for auto-committing and pushing files to origin main.
    Before pushing, runs 'git pull --rebase origin main'.
    On conflict/failure retries the push once.
    Wrapped in try/except so git errors never crash the run.
    """
    if os.getenv("SKIP_GIT_PUSH", "0").strip() == "1":
        print("SKIP_GIT_PUSH=1: Skipping git commit & push.")
        return True

    try:
        import subprocess

        # Set default git identity if unset (for serverless environments)
        name_check = subprocess.run(["git", "config", "user.name"], capture_output=True, text=True)
        if not name_check.stdout.strip():
            subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=False)
            subprocess.run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"], check=False)

        # Stage files that exist
        staged_any = False
        for f in files:
            if os.path.exists(f):
                add_res = subprocess.run(["git", "add", f], check=False, capture_output=True, text=True)
                if add_res.returncode == 0:
                    staged_any = True
                else:
                    print(f"Warning: git add {f} returned code {add_res.returncode}: {add_res.stderr.strip()}")

        if not staged_any:
            return True

        diff_proc = subprocess.run(["git", "diff", "--staged", "--quiet"], capture_output=True)
        if diff_proc.returncode == 0:
            print(f"No changes in {files} to commit.")
            return True

        commit_proc = subprocess.run(
            ["git", "commit", "-m", commit_message],
            capture_output=True,
            text=True,
            check=False,
        )
        if commit_proc.returncode != 0:
            print(f"Git commit failed (code {commit_proc.returncode}): {commit_proc.stderr.strip()}")
            return False
        print(f"Git committed: {commit_proc.stdout.strip()}")

        # Pull with rebase before pushing
        pull_proc = subprocess.run(
            ["git", "pull", "--rebase", "origin", "main"],
            capture_output=True,
            text=True,
        )
        if pull_proc.returncode != 0:
            print(f"Warning: git pull --rebase failed (code {pull_proc.returncode}): {pull_proc.stderr.strip()}. Aborting rebase if in progress.")
            subprocess.run(["git", "rebase", "--abort"], capture_output=True)

        push_proc = subprocess.run(
            ["git", "push", "origin", "HEAD:main"],
            capture_output=True,
            text=True,
        )
        if push_proc.returncode == 0:
            print("Git pushed updates to origin main.")
            return True

        # Push failed, retry once with pull --rebase
        print(f"Git push failed (code {push_proc.returncode}: {push_proc.stderr.strip()}), retrying push once...")
        pull_retry = subprocess.run(
            ["git", "pull", "--rebase", "origin", "main"],
            capture_output=True,
            text=True,
        )
        if pull_retry.returncode != 0:
            subprocess.run(["git", "rebase", "--abort"], capture_output=True)

        push_retry = subprocess.run(
            ["git", "push", "origin", "HEAD:main"],
            capture_output=True,
            text=True,
        )
        if push_retry.returncode == 0:
            print("Git pushed updates to origin main on retry.")
            return True
        else:
            print(f"Git push retry failed (code {push_retry.returncode}): {push_retry.stderr.strip()}")
            return False

    except Exception as exc:
        print(f"Git auto-commit failed (non-blocking): {exc}")
        return False


def git_commit_scan_results() -> None:
    """
    Commit and push scan_results.json, deals.json, and events.json to origin main.
    Skips if SKIP_GIT_PUSH environment variable is set to '1'.
    Fails safely so git errors never break the scanner.
    """
    files_to_commit = [SCAN_RESULTS_FILE]
    if os.path.exists(DEALS_FILE):
        files_to_commit.append(DEALS_FILE)
    if os.path.exists(EVENTS_FILE):
        files_to_commit.append(EVENTS_FILE)
    if os.path.exists(OPEN_POSITIONS_FILE):
        files_to_commit.append(OPEN_POSITIONS_FILE)
    if os.path.exists(LAST_ALERT_FILE):
        files_to_commit.append(LAST_ALERT_FILE)
    git_commit_and_push(files_to_commit, "update scan results, deals, and events [skip ci]")


def git_commit_listener_updates(commit_message: str = "Auto-update Telegram offset and journal [skip ci]") -> None:
    """
    Commit and push listener updates (tg_offset.txt, alert_settings.json, trades.json, open_positions.json).
    Skips if SKIP_GIT_PUSH environment variable is set to '1'.
    Fails safely so git errors never break the listener.
    """
    files = [TG_OFFSET_FILE, ALERT_SETTINGS_FILE, TRADES_FILE, OPEN_POSITIONS_FILE]
    git_commit_and_push(files, commit_message)


# =====================================================================
# 11) SCRIPT ENTRY POINT
# =====================================================================
if __name__ == "__main__":
    if "--poll" in sys.argv:
        poll_loop()  # long-running, for the listener workflow
    else:
        # Check if daily proactive scan alerts have already been sent for today
        today_ist_str = get_now_ist().strftime("%Y-%m-%d")
        already_alerted_today = False
        force_alert_active = (os.getenv("FORCE_ALERT", "0").strip() == "1" or os.getenv("FORCE_RESEND", "0").strip() == "1")
        if os.path.exists(LAST_ALERT_FILE) and not force_alert_active:
            try:
                with open(LAST_ALERT_FILE, "r", encoding="utf-8") as f:
                    already_alerted_today = (f.read().strip() == today_ist_str)
            except Exception:
                pass

        if already_alerted_today:
            print(f"Daily proactive Telegram alert already sent for today ({today_ist_str}). Running in quiet mode for dashboard refresh.")
            os.environ["QUIET"] = "1"

        settings = load_alert_settings()
        is_digest = settings.get("digest", False)

        # 1. Run daily setup scanner
        signals, scanned_count, is_mkt_ok = run_scanner()

        # 2. Build watchlist candidates & send Telegram alert
        watchlist_candidates = get_watchlist_candidates()
        open_pos, warn_lines = evaluate_open_positions_events()
        _LANDMINES = compute_landmines(watchlist_candidates, _LAST_ON_DECK, open_pos)

        if SEND_WATCHLIST:
            wl_text = build_watchlist_text(watchlist_candidates)
            if is_digest:
                _DIGEST_MESSAGES.append(("watchlist", wl_text))
            else:
                send_telegram(wl_text, kind="proactive", msg_type="watchlist")

        # In digest mode, combine valid parts into 1 message and send once
        if is_digest and _DIGEST_MESSAGES:
            enable_flags = settings.get("enable", {})
            valid_parts = [
                text for mtype, text in _DIGEST_MESSAGES
                if enable_flags.get(mtype, True) and text.strip()
            ]
            if valid_parts:
                separator = "\n\n" + ("-" * 30) + "\n\n"
                combined_digest = separator.join(valid_parts)
                send_telegram(combined_digest, kind="proactive", msg_type="scan")
            _DIGEST_MESSAGES.clear()

        # Record today's alert date if run was active
        if not already_alerted_today and os.getenv("QUIET", "0").strip() != "1":
            try:
                with open(LAST_ALERT_FILE, "w", encoding="utf-8") as f:
                    f.write(today_ist_str)
            except Exception as exc:
                print(f"Warning writing {LAST_ALERT_FILE}: {exc}")

        # 3. Publish scan_results.json for web dashboard
        ist_tz = datetime.timezone(datetime.timedelta(hours=5, minutes=30))
        now_ist = datetime.datetime.now(ist_tz).isoformat()

        total_scanned = scanned_count if scanned_count > 0 else len(get_symbols())
        scan_results = {
            "updated_at": now_ist,
            "market_ok": is_mkt_ok,
            "signals": signals,
            "watchlist": watchlist_candidates,
            "on_deck": _LAST_ON_DECK,
            "scanned_count": total_scanned,
            "leaders_board": _LEADERS_BOARD,
            "inst_summary": _INST_SUMMARY,
            "deals_stale": _DEALS_STALE,
            "landmines": _LANDMINES,
            "correlation": compute_open_positions_correlation(open_pos),
            "market_summary": compute_market_summary(),
        }

        with open(SCAN_RESULTS_FILE, "w", encoding="utf-8") as f:
            json.dump(scan_results, f, indent=2, ensure_ascii=False)
        print(f"Published scan results to {SCAN_RESULTS_FILE}")

        # 4. Attempt git auto-commit of scan_results.json
        git_commit_scan_results()

