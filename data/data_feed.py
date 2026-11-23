"""
Midcap Swing Scanner - Historical Data Feed & Cache (Version 2)
Retrieves clean, standardized daily OHLCV bars from Yahoo Finance with 5-year lookback
to ensure complete history for 200-SMA, 52-week High/Low, and multi-year backtesting.
"""

import time
import logging
from typing import Optional, Dict
import pandas as pd
import yfinance as yf

# Suppress yfinance verbose console output
logging.getLogger("yfinance").setLevel(logging.CRITICAL)

_HISTORY_CACHE: Dict[str, pd.DataFrame] = {}


def clear_history_cache() -> None:
    """Clear in-memory historical DataFrame cache."""
    global _HISTORY_CACHE
    _HISTORY_CACHE.clear()


def get_history(
    symbol: str,
    period: str = "5y",
    interval: str = "1d",
    use_cache: bool = True,
    max_retries: int = 2,
    retry_delay: float = 1.0,
) -> Optional[pd.DataFrame]:
    """
    Download daily historical data for the symbol from Yahoo Finance.
    Returns clean DataFrame with standardized columns: [Date, Open, High, Low, Close, Volume].
    Uses 5-year default lookback to ensure sufficient warmup bars for 200-SMA and 52-week metrics.
    Caches downloaded frames in memory to avoid redundant network calls.
    """
    clean_sym = symbol.strip().upper()
    cache_key = f"{clean_sym}_{period}_{interval}"

    if use_cache and cache_key in _HISTORY_CACHE:
        return _HISTORY_CACHE[cache_key].copy()

    for attempt in range(max_retries + 1):
        try:
            df = yf.download(
                clean_sym,
                period=period,
                interval=interval,
                auto_adjust=False,
                progress=False,
            )

            if df is None or df.empty:
                if attempt < max_retries:
                    time.sleep(retry_delay * (attempt + 1))
                    continue
                return None

            # Reset index to extract Date column
            df = df.reset_index()

            # Flatten MultiIndex columns if present (common in newer yfinance versions)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            # Ensure first column is named Date
            df.rename(columns={df.columns[0]: "Date"}, inplace=True)

            # Validate required columns
            required_cols = ["Date", "Open", "High", "Low", "Close", "Volume"]
            for col in required_cols:
                if col not in df.columns:
                    return None

            df = df[required_cols].copy()

            # Standardize datetime and remove timezone offsets
            df["Date"] = pd.to_datetime(df["Date"])
            if df["Date"].dt.tz is not None:
                df["Date"] = df["Date"].dt.tz_localize(None)

            # Standardize numeric columns
            df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce").fillna(0.0)
            for num_col in ["Open", "High", "Low", "Close"]:
                df[num_col] = pd.to_numeric(df[num_col], errors="coerce")

            df = df.dropna(subset=["Close"]).reset_index(drop=True)
            if df.empty:
                return None

            if use_cache:
                _HISTORY_CACHE[cache_key] = df

            return df.copy()

        except Exception as exc:
            if attempt < max_retries:
                time.sleep(retry_delay * (attempt + 1))
            else:
                return None

    return None
