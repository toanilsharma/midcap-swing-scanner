"""
Midcap Swing Scanner - Mathematical Indicators & Smoothing Engine (Version 2)
Implements J. Welles Wilder's exponential smoothing for ATR and RSI, moving averages,
Bollinger/Keltner squeeze detection, and Minervini Stage-2 trend filters.
"""

from typing import Optional
import numpy as np
import pandas as pd
from core.config import (
    VOLUME_SPIKE_MULTIPLIER,
    SETUP_WINDOW_DAYS,
    ENABLE_SQUEEZE,
    MIN_HISTORY_BARS,
)


def compute_true_range(df: pd.DataFrame) -> pd.Series:
    """
    Compute True Range (TR) for each daily bar:
    TR = max(High - Low, |High - Close_prev|, |Low - Close_prev|)
    """
    prev_close = df["Close"].shift(1)
    tr1 = df["High"] - df["Low"]
    tr2 = (df["High"] - prev_close).abs()
    tr3 = (df["Low"] - prev_close).abs()
    return pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)


def compute_wilder_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Compute Average True Range (ATR) using J. Welles Wilder's Exponential Smoothing:
    ATR_t = (ATR_{t-1} * (period - 1) + TR_t) / period
    Equivalent to exponential moving average with alpha = 1 / period.
    """
    tr = compute_true_range(df)
    # alpha = 1 / period produces exact Wilder smoothing
    atr = tr.ewm(alpha=1.0 / period, adjust=False).mean()
    # Mask initial bars prior to period so insufficient data is not treated as valid
    if len(df) < period:
        return pd.Series(index=df.index, dtype=float)
    return atr


def compute_wilder_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """
    Compute Relative Strength Index (RSI) using J. Welles Wilder's Smoothing:
    Smoothed Gain_t = (Gain_{t-1} * (period - 1) + Current_Gain) / period
    Smoothed Loss_t = (Loss_{t-1} * (period - 1) + Current_Loss) / period
    RS = Smoothed Gain / Smoothed Loss
    RSI = 100 - (100 / (1 + RS))
    """
    diff = series.diff()
    gains = diff.clip(lower=0.0)
    losses = (-diff).clip(lower=0.0)

    # Wilder smoothing via ewm with alpha = 1 / period
    smoothed_gains = gains.ewm(alpha=1.0 / period, adjust=False).mean()
    smoothed_losses = losses.ewm(alpha=1.0 / period, adjust=False).mean()

    # Calculate RS and RSI safely
    rs = smoothed_gains / smoothed_losses.replace(0.0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))

    # Boundary handling:
    # If loss is 0 and gain > 0, RSI = 100
    # If gain is 0 and loss > 0, RSI = 0
    # If both are 0, RSI = 50
    rsi = rsi.where(smoothed_losses > 0.0, 100.0)
    rsi = rsi.where(smoothed_gains > 0.0, 0.0)
    both_zero = (smoothed_gains == 0.0) & (smoothed_losses == 0.0)
    rsi = rsi.where(~both_zero, 50.0)

    return rsi


def compute_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute complete set of quantitative technical indicators for daily swing analysis:
    - Moving averages (SMA50, SMA150, SMA200, EMA20)
    - Volume metrics (VOL5, VOL50)
    - Volatility & Range (True Range, Wilder ATR14, RANGE5, RANGE50)
    - Oscillators (Wilder RSI14, Wilder RSI2)
    - 52-Week High & Low (with strict 250-bar minimum period validation)
    - Volatility Squeeze (Bollinger Bands inside Keltner Channels)
    - Minervini Stage-2 Trend Filter (fail-closed if history < 200 bars)
    """
    df = df.copy()

    # 1. Moving averages of Close
    df["SMA50"] = df["Close"].rolling(50, min_periods=50).mean()
    df["SMA150"] = df["Close"].rolling(150, min_periods=150).mean()
    df["SMA200"] = df["Close"].rolling(200, min_periods=200).mean()
    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()

    # 2. Moving averages of Volume
    df["VOL5"] = df["Volume"].rolling(5, min_periods=5).mean()
    df["VOL50"] = df["Volume"].rolling(50, min_periods=50).mean()

    # 3. Volatility & Ranges
    hl_range = df["High"] - df["Low"]
    df["RANGE5"] = hl_range.rolling(5, min_periods=5).mean()
    df["RANGE50"] = hl_range.rolling(50, min_periods=50).mean()

    df["true_range"] = compute_true_range(df)
    df["ATR14"] = compute_wilder_atr(df, period=14)

    # 4. Oscillators (Wilder RSI)
    df["RSI14"] = compute_wilder_rsi(df["Close"], period=14)
    df["RSI2"] = compute_wilder_rsi(df["Close"], period=2)

    # 5. 52-week High and Low (Strict 250-bar requirement)
    df["HIGH52W"] = df["High"].rolling(252, min_periods=250).max()
    df["LOW52W"] = df["Low"].rolling(252, min_periods=250).min()
    df["HAS_52W_DATA"] = df["HIGH52W"].notna() & df["LOW52W"].notna()

    # 6. 20-day High excluding today
    df["HIGH20"] = df["High"].rolling(20, min_periods=20).max().shift(1)

    # 7. Squeeze condition: Bollinger Bands inside Keltner Channels
    sma20 = df["Close"].rolling(20, min_periods=20).mean()
    std20 = df["Close"].rolling(20, min_periods=20).std()
    bb_upper = sma20 + (2.0 * std20)
    bb_lower = sma20 - (2.0 * std20)

    atr20 = compute_wilder_atr(df, period=20)
    kc_upper = sma20 + (1.5 * atr20)
    kc_lower = sma20 - (1.5 * atr20)
    df["SQUEEZE_ON"] = (bb_upper < kc_upper) & (bb_lower > kc_lower)

    # 8. Setup conditions: volume contraction & price tightening
    df["VOL_DRYUP"] = df["VOL5"] < (0.80 * df["VOL50"])
    df["PRICE_TIGHT"] = df["RANGE5"] < (0.80 * df["RANGE50"])
    df["SETUP_OK"] = df["VOL_DRYUP"] & df["PRICE_TIGHT"]

    # 9. Setup window: active if setup or squeeze occurred within SETUP_WINDOW_DAYS, shifted by 1 day
    coiling = df["SETUP_OK"] | (df["SQUEEZE_ON"] if ENABLE_SQUEEZE else False)
    df["SETUP_WINDOW"] = coiling.astype(float).rolling(SETUP_WINDOW_DAYS).max().shift(1) > 0

    # 10. Breakout triggers
    df["BREAKOUT"] = (df["Close"] > df["HIGH20"]) & (df["Close"].shift(1) <= df["HIGH20"])
    df["VOL_SPIKE"] = df["Volume"] > (VOLUME_SPIKE_MULTIPLIER * df["VOL50"])

    # 11. Strong close (>60% of candle's range)
    safe_hl = (df["High"] - df["Low"]).replace(0.0, np.nan)
    df["STRONG_CLOSE"] = ((df["Close"] - df["Low"]) / safe_hl) > 0.60

    # 12. Pullback trigger
    df["PULLBACK"] = (df["RSI2"] < 10) & (df["RSI2"].shift(1) >= 10) & (df["Close"] > df["Close"].shift(1))

    # 13. Trend Filter (Minervini / O'Neil Stage-2) — Fail-closed if history insufficient
    sma_cross = df["SMA150"] > df["SMA200"]
    sma200_slope = df["SMA200"] > df["SMA200"].shift(20)

    df["TREND_OK"] = (
        df["HAS_52W_DATA"]
        & (df["Close"] > df["SMA150"])
        & (df["Close"] > df["SMA200"])
        & sma_cross
        & sma200_slope
        & (df["SMA50"] > df["SMA150"])
        & (df["SMA50"] > df["SMA200"])
        & (df["Close"] > df["SMA50"])
        & (df["Close"] > 1.30 * df["LOW52W"])
        & (df["Close"] > 0.75 * df["HIGH52W"])
    ).fillna(False)

    # 14. Master signals
    df["SIGNAL"] = (
        df["TREND_OK"]
        & df["SETUP_WINDOW"]
        & df["BREAKOUT"]
        & df["VOL_SPIKE"]
        & df["STRONG_CLOSE"]
    ).fillna(False)

    df["SIGNAL_PULLBACK"] = (df["TREND_OK"] & df["PULLBACK"]).fillna(False)

    return df
