"""
Midcap Swing Scanner - Data Access Layer (Version 2)
Provides robust market data retrieval, historical loaders, and caching.
"""

from data.data_feed import (
    get_history,
    clear_history_cache,
)

__all__ = [
    "get_history",
    "clear_history_cache",
]
