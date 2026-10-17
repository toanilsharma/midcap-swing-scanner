"""
Daily NIFTY Midcap 100 Swing-Trading Scanner with Telegram Alerts.
Implements momentum trend-following and pullback setups with discipline rules.
"""

import io
import math
import os
import re
import sys
import time
from typing import Optional, Dict, Any, List

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

# Cache for the index historical dataframe
_INDEX_CACHE: Optional[pd.DataFrame] = None


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

    # 3) Setup trigger check
    last_row = df.iloc[-1]
    if last_row["SIGNAL"]:
        signal_type = "BREAKOUT"
    elif ENABLE_PULLBACK and last_row["SIGNAL_PULLBACK"]:
        signal_type = "PULLBACK"
    else:
        return None

    # 4) Entry and Stop Loss
    entry = float(last_row["Close"])
    atr = float(last_row["ATR14"])
    if pd.isna(entry) or pd.isna(atr) or atr <= 0 or entry <= 0:
        return None

    stop = entry - (ATR_STOP_MULTIPLIER * atr)
    # Floor stop loss at 7% (max 7% risk from entry)
    stop = max(stop, entry * 0.93)
    if stop >= entry:
        return None

    # 5) Sizing and target
    risk_per_unit = entry - stop
    target = entry + (TARGET_R_MULTIPLE * risk_per_unit)
    qty = math.floor((CAPITAL * RISK_PCT) / risk_per_unit)
    if qty <= 0:
        return None

    risk_amount = qty * risk_per_unit

    return {
        "Signal Date": pd.to_datetime(last_row["Date"]).strftime("%Y-%m-%d"),
        "Symbol": symbol,
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


def run_scanner() -> None:
    """Execute the full scan across all candidate symbols."""
    print("Checking market regime filter...")
    if not market_ok():
        msg = "🔴 MARKET FILTER: Index not in uptrend. No new entries today (O'Neil M-rule)."
        print(msg)
        send_telegram(msg)
        return

    symbols = get_symbols()
    total = len(symbols)
    print(f"Scanning {total} symbols for swing setups...")

    messages: List[str] = []

    for i, sym in enumerate(symbols, start=1):
        print(f"{i}/{total}: {sym}")
        sig = scan_symbol(sym)
        if sig:
            formatted = f"{format_signal(sig)}\n\n{DISCIPLINE_CARD}"
            messages.append(formatted)
        time.sleep(0.25)

    if messages:
        joined_message = "\n\n----\n\n".join(messages)
        send_telegram(joined_message)
    elif SEND_NO_SIGNAL_MESSAGE:
        send_telegram("No new midcap swing signals today.")


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
    trend_str = "YES" if bool(last_row["TREND_OK"]) else "no"
    coiling_str = "YES" if bool(last_row["SETUP_OK"]) else "no"
    dist_pct = round(((high20_val - close_val) / close_val) * 100, 2)

    return {
        "Symbol": sym_name,
        "Trend": trend_str,
        "Coiling": coiling_str,
        "DistToBreakout%": dist_pct,
        "Close": round(close_val, 2),
    }


def build_watchlist_text() -> str:
    """
    Scan symbols to build a watchlist of stocks in an uptrend near breakout.
    """
    symbols = get_symbols()
    watchlist_candidates: List[Dict[str, Any]] = []

    print("Building watchlist...")
    for sym in symbols:
        diag = diagnose(sym)
        if diag and diag["Trend"] == "YES" and diag["DistToBreakout%"] <= 5.0:
            watchlist_candidates.append(diag)
        time.sleep(0.2)

    if not watchlist_candidates:
        return "📋 Watchlist empty: no midcap in uptrend near breakout."

    # Sort ascending by distance to breakout
    watchlist_candidates.sort(key=lambda x: x["DistToBreakout%"])

    lines = ["📋 MIDCAP WATCHLIST (near breakout)"]
    for item in watchlist_candidates:
        line = (
            f"{item['Symbol']} | {item['DistToBreakout%']}% away | "
            f"Close {item['Close']} | Coiling: {item['Coiling']}"
        )
        lines.append(line)

    return "\n".join(lines)


# =====================================================================
# 10) SCRIPT ENTRY POINT
# =====================================================================
if __name__ == "__main__":
    run_scanner()
    if SEND_WATCHLIST:
        wl_text = build_watchlist_text()
        send_telegram(wl_text)
