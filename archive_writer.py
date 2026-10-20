#!/usr/bin/env python3
"""
Nightly OHLCV Archive Writer.
Appends daily OHLCV snapshots for scanned symbols to monthly gzip-compressed CSV files:
archive/ohlcv_<YYYY-MM>.csv.gz
Format: date,symbol,open,high,low,close,volume
Fail-open: warnings on network/write errors never block or crash the daily scan.
"""

import os
import sys
from typing import Optional, List, Dict, Any
import pandas as pd
import main

ARCHIVE_DIR = "archive"
EXPECTED_COLUMNS = ["date", "symbol", "open", "high", "low", "close", "volume"]


def get_archive_filepath(year_month: str, archive_dir: str = ARCHIVE_DIR) -> str:
    return os.path.join(archive_dir, f"ohlcv_{year_month}.csv.gz")


def append_daily_snapshot(
    archive_dir: str = ARCHIVE_DIR,
    symbols: Optional[List[str]] = None,
    target_date: Optional[str] = None
) -> List[str]:
    """
    Extracts today's OHLCV bar for all scanned symbols and appends to the monthly archive.
    Fail-open: catches all exceptions, prints a warning, and returns empty list on failure.
    """
    try:
        os.makedirs(archive_dir, exist_ok=True)

        if symbols is None:
            symbols = main.get_symbols()

        if not symbols:
            print("⚠️ Archive writer: no symbols found to snapshot.")
            return []

        rows: List[Dict[str, Any]] = []

        print(f"Archiving daily OHLCV snapshot for {len(symbols)} symbols into {archive_dir}/...")
        for sym in symbols:
            try:
                df = main.get_history(sym)
                if df is None or df.empty:
                    continue

                last_bar = df.iloc[-1]
                bar_date = pd.to_datetime(last_bar["Date"]).strftime("%Y-%m-%d")

                if target_date and bar_date != target_date:
                    matching = df[pd.to_datetime(df["Date"]).dt.strftime("%Y-%m-%d") == target_date]
                    if not matching.empty:
                        last_bar = matching.iloc[-1]
                        bar_date = target_date
                    else:
                        continue

                rows.append({
                    "date": bar_date,
                    "symbol": sym,
                    "open": round(float(last_bar["Open"]), 2),
                    "high": round(float(last_bar["High"]), 2),
                    "low": round(float(last_bar["Low"]), 2),
                    "close": round(float(last_bar["Close"]), 2),
                    "volume": int(float(last_bar["Volume"])),
                })
            except Exception as sym_err:
                print(f"⚠️ Archive writer: failed bar extraction for {sym}: {sym_err}")

        if not rows:
            print("⚠️ Archive writer: no OHLCV rows extracted for archiving.")
            return []

        new_df = pd.DataFrame(rows)
        new_df["year_month"] = new_df["date"].str[:7]
        written_files: List[str] = []

        for ym, group in new_df.groupby("year_month"):
            archive_file = get_archive_filepath(str(ym), archive_dir=archive_dir)
            group_data = group[EXPECTED_COLUMNS]

            if os.path.exists(archive_file):
                try:
                    existing_df = pd.read_csv(archive_file, compression="gzip")
                    combined = pd.concat([existing_df, group_data], ignore_index=True)
                    combined = combined.drop_duplicates(subset=["date", "symbol"], keep="last")
                    combined = combined.sort_values(by=["date", "symbol"])
                except Exception as read_err:
                    print(f"⚠️ Archive writer: reading existing {archive_file} failed ({read_err}); overwriting with fresh rows")
                    combined = group_data.drop_duplicates(subset=["date", "symbol"], keep="last")
            else:
                combined = group_data.drop_duplicates(subset=["date", "symbol"], keep="last")
                combined = combined.sort_values(by=["date", "symbol"])

            combined.to_csv(archive_file, index=False, compression="gzip")
            file_size_kb = os.path.getsize(archive_file) / 1024.0
            print(f"✅ Archive updated: {archive_file} ({len(combined)} total rows, {file_size_kb:.1f} KB)")
            written_files.append(archive_file)

        if os.getenv("SKIP_GIT_PUSH") != "1" and written_files:
            try:
                main.git_commit_and_push(written_files, "archive: append daily OHLCV snapshot [skip ci]")
            except Exception as git_err:
                print(f"⚠️ Archive writer: auto-commit non-fatal warning: {git_err}")

        return written_files

    except Exception as exc:
        print(f"⚠️ Archive writer fail-open: {exc}")
        return []


if __name__ == "__main__":
    append_daily_snapshot()
