import pytest
import pandas as pd
from typing import Any
import main


def make_index_df(close: float, sma50: float, sma200: float, length: int = 250) -> pd.DataFrame:
    """Helper to construct a mock index dataframe with defined Close, SMA50, and SMA200."""
    data = {
        "Close": [close] * length,
        "SMA50": [sma50] * length,
        "SMA200": [sma200] * length,
    }
    return pd.DataFrame(data)


@pytest.fixture(autouse=True)
def restore_real_market_ok(monkeypatch: pytest.MonkeyPatch):
    """Restore the unmocked market_ok function from main._REAL_MARKET_OK for market regime tests."""
    monkeypatch.setattr(main, "market_ok", main._REAL_MARKET_OK)


def test_market_ok_early_bull_recovery(monkeypatch: pytest.MonkeyPatch):
    """
    Early bull recovery: Nifty Close (25,299) > SMA50 (23,310) and Close > SMA200 (23,992),
    even though SMA50 (23,310) is still lagging below SMA200 (23,992).
    Must return True.
    """
    df = make_index_df(close=25299.35, sma50=23310.51, sma200=23992.20)
    monkeypatch.setattr(main, "get_cached_index_df", lambda: df)
    assert main.market_ok() is True


def test_market_ok_mature_bull_market(monkeypatch: pytest.MonkeyPatch):
    """
    Mature bull: Close > SMA50 > SMA200.
    Must return True.
    """
    df = make_index_df(close=26000.0, sma50=25000.0, sma200=24000.0)
    monkeypatch.setattr(main, "get_cached_index_df", lambda: df)
    assert main.market_ok() is True


def test_market_ok_correction_downtrend(monkeypatch: pytest.MonkeyPatch):
    """
    Downtrend: Close below both 50-DMA and 200-DMA.
    Must return False.
    """
    df = make_index_df(close=22500.0, sma50=23500.0, sma200=24000.0)
    monkeypatch.setattr(main, "get_cached_index_df", lambda: df)
    assert main.market_ok() is False


def test_market_ok_bear_countertrend_bounce(monkeypatch: pytest.MonkeyPatch):
    """
    Bear market bounce: Price bounced above SMA50, but remains below SMA200 and SMA50 < SMA200.
    Must remain False to avoid bull traps.
    """
    df = make_index_df(close=23500.0, sma50=23200.0, sma200=24500.0)
    monkeypatch.setattr(main, "get_cached_index_df", lambda: df)
    assert main.market_ok() is False


def test_watchlist_candidates_populates_rs_even_if_not_prerun(monkeypatch: pytest.MonkeyPatch):
    """
    Verify get_watchlist_candidates() guarantees _RS_RATINGS is populated and not None.
    """
    # Reset global _RS_RATINGS
    main._RS_RATINGS = {}
    
    # Mock universe of 35 symbols with valid history
    symbols = [f"SYM{i}.NS" for i in range(35)]
    monkeypatch.setattr(main, "get_symbols", lambda: symbols)
    
    # Create simple history df
    df = pd.DataFrame({
        "Open": [100.0] * 60,
        "High": [105.0] * 60,
        "Low": [95.0] * 60,
        "Close": [102.0] * 60,
        "Volume": [100000] * 60,
    })
    monkeypatch.setattr(main, "get_history", lambda sym: df)
    monkeypatch.setattr(main, "market_ok", lambda: True)
    
    # Call get_watchlist_candidates
    candidates = main.get_watchlist_candidates()
    
    # Assert _RS_RATINGS is now populated
    assert len(main._RS_RATINGS) >= 30
    for sym, rs in main._RS_RATINGS.items():
        assert rs is not None
        assert 1 <= rs <= 99
