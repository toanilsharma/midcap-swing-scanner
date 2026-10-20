#!/usr/bin/env python3
"""
Midcap Swing Scanner - Rules-Replay Backtest Engine.
CORRECTNESS ANCHOR:
Imports add_indicators, diagnose_from_dataframe, compute_risk_parameters,
and evaluate_trade_exit directly from main.py so replay uses the exact live rules by construction.
"""

import argparse
import datetime
import glob
import gzip
import json
import os
import sys
from typing import Any, Dict, List, Optional
import numpy as np
import pandas as pd

from main import (
    add_indicators,
    diagnose_from_dataframe,
    compute_risk_parameters,
    evaluate_trade_exit,
    CAPITAL,
    RISK_PCT,
    ENABLE_PULLBACK,
)


def load_archive_data(archive_dir: str = "archive") -> pd.DataFrame:
    """
    Load and concatenate all monthly gzip CSV snapshots from the archive folder.
    Returns normalized DataFrame with Date, Open, High, Low, Close, Volume, symbol, date.
    """
    if not os.path.exists(archive_dir):
        return pd.DataFrame()

    files = sorted(glob.glob(os.path.join(archive_dir, "ohlcv_*.csv.gz")))
    if not files:
        files = sorted(glob.glob(os.path.join(archive_dir, "ohlcv_*.csv")))
    if not files:
        return pd.DataFrame()

    dfs: List[pd.DataFrame] = []
    for fpath in files:
        try:
            compression = "gzip" if fpath.endswith(".gz") else None
            df = pd.read_csv(fpath, compression=compression)
            # Normalize column names to lower
            df.columns = [c.strip().lower() for c in df.columns]
            dfs.append(df)
        except Exception as err:
            print(f"⚠️ Warning loading {fpath}: {err}", file=sys.stderr)

    if not dfs:
        return pd.DataFrame()

    master = pd.concat(dfs, ignore_index=True)
    required = ["date", "symbol", "open", "high", "low", "close", "volume"]
    for col in required:
        if col not in master.columns:
            return pd.DataFrame()

    master["date"] = master["date"].astype(str).str[:10]
    master["Date"] = pd.to_datetime(master["date"])
    master["Open"] = master["open"].astype(float)
    master["High"] = master["high"].astype(float)
    master["Low"] = master["low"].astype(float)
    master["Close"] = master["close"].astype(float)
    master["Volume"] = master["volume"].astype(float)

    master = master.drop_duplicates(subset=["date", "symbol"], keep="last")
    master = master.sort_values(by=["symbol", "Date"]).reset_index(drop=True)
    return master


def backtest(
    archive_dir: str = "archive",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    capital: float = CAPITAL,
    master_df: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """
    Day-by-day rules-replay backtest simulator.
    Loads archived bars, walks day by day, evaluates entries and exits mechanically.
    """
    capital_float = float(capital if capital is not None else CAPITAL)

    empty_result: Dict[str, Any] = {
        "period": {
            "start": start_date or "",
            "end": end_date or "",
        },
        "trades": [],
        "equity_curve": [{"date": start_date or "", "value": capital_float, "drawdown": 0.0}],
        "win_rate": 0.0,
        "avg_win_R": 0.0,
        "avg_loss_R": 0.0,
        "expectancy_R": 0.0,
        "profit_factor": 0.0,
        "max_drawdown_pct": 0.0,
        "by_grade": {
            "A+": {"trades": 0, "win_rate": 0.0, "expectancy_R": 0.0, "total_pnl": 0.0},
            "A": {"trades": 0, "win_rate": 0.0, "expectancy_R": 0.0, "total_pnl": 0.0},
            "B": {"trades": 0, "win_rate": 0.0, "expectancy_R": 0.0, "total_pnl": 0.0},
            "C": {"trades": 0, "win_rate": 0.0, "expectancy_R": 0.0, "total_pnl": 0.0},
        },
        "by_signal_type": {
            "BREAKOUT": {"trades": 0, "win_rate": 0.0, "expectancy_R": 0.0, "total_pnl": 0.0},
            "PULLBACK": {"trades": 0, "win_rate": 0.0, "expectancy_R": 0.0, "total_pnl": 0.0},
            "SPRING": {"trades": 0, "win_rate": 0.0, "expectancy_R": 0.0, "total_pnl": 0.0},
        },
        "tail_capture": {
            "pct_winners_past_2R": 0.0,
            "avg_R_of_tails": 0.0,
            "capped_vs_trailed_delta": 0.0,
        },
    }

    if master_df is None:
        master_df = load_archive_data(archive_dir)

    if master_df.empty:
        return empty_result

    # Normalize columns in case custom master_df was passed
    if "date" not in master_df.columns:
        for c in master_df.columns:
            if c.lower() == "date":
                master_df["date"] = master_df[c].astype(str).str[:10]
                break
    if "Date" not in master_df.columns:
        master_df["Date"] = pd.to_datetime(master_df["date"])
    for col in ["Open", "High", "Low", "Close", "Volume"]:
        if col not in master_df.columns:
            for c in master_df.columns:
                if c.lower() == col.lower():
                    master_df[col] = master_df[c].astype(float)
                    break
    if "symbol" not in master_df.columns:
        for c in master_df.columns:
            if c.lower() == "symbol":
                master_df["symbol"] = master_df[c].astype(str)
                break

    # All unique dates sorted
    all_dates = sorted(master_df["date"].unique().tolist())
    if not all_dates:
        return empty_result

    eval_dates = [d for d in all_dates if (start_date is None or d >= start_date) and (end_date is None or d <= end_date)]
    if not eval_dates:
        return empty_result

    current_cash = capital_float
    peak_equity = capital_float
    open_positions: List[Dict[str, Any]] = []
    closed_trades: List[Dict[str, Any]] = []
    equity_curve: List[Dict[str, Any]] = []
    trade_counter = 1

    # Pre-index bars by (symbol, date) for quick lookup
    # Group master_df by symbol
    symbol_groups = {sym: grp.sort_values(by="Date").reset_index(drop=True) for sym, grp in master_df.groupby("symbol")}

    for current_date in eval_dates:
        # 1. Evaluate exits for existing open positions
        for pos in list(open_positions):
            sym = pos["symbol"]
            sym_df = symbol_groups.get(sym)
            if sym_df is None:
                continue

            bar_row = sym_df[sym_df["date"] == current_date]
            if bar_row.empty:
                continue

            # Need EMA20 on trailing series for the runner trailing stop
            trailing_sub = sym_df[sym_df["date"] <= current_date]
            if "EMA20" not in trailing_sub.columns:
                trailing_sub = add_indicators(trailing_sub)
            current_bar = trailing_sub.iloc[-1]

            pos["holding_days"] += 1
            exit_event = evaluate_trade_exit(pos, current_bar, pos["holding_days"])

            if exit_event is not None:
                action = exit_event["action"]
                exit_price = float(exit_event["exit_price"])
                exit_qty = int(exit_event["qty"])
                reason = exit_event["reason"]

                if action == "PARTIAL_TARGET":
                    # Realize 50% partial at 2R target; runner stays open
                    partial_pnl = (exit_price - pos["entry_price"]) * exit_qty
                    pos["realized_pnl"] = pos.get("realized_pnl", 0.0) + partial_pnl
                    pos["partial_exit_price"] = exit_price
                    pos["partial_exit_date"] = current_date
                    current_cash += partial_pnl
                else:
                    # Full exit (STOP_LOSS, TARGET_FULL, TRAIL_EXIT, TIME_STOP)
                    exit_pnl = (exit_price - pos["entry_price"]) * exit_qty
                    total_pnl = pos.get("realized_pnl", 0.0) + exit_pnl
                    current_cash += exit_pnl
                    open_positions.remove(pos)

                    initial_risk_budget = pos["risk_per_unit"] * pos["qty"]
                    r_mult = total_pnl / initial_risk_budget if initial_risk_budget > 0 else 0.0
                    pnl_pct = ((pos["entry_price"] * pos["qty"] + total_pnl) / (pos["entry_price"] * pos["qty"]) - 1.0) * 100.0 if pos["entry_price"] > 0 else 0.0

                    capped_r = min(2.0, r_mult) if r_mult > 0 else r_mult
                    trailed_r = r_mult

                    exit_reason_str = reason
                    if pos.get("partial_taken"):
                        exit_reason_str = f"2R Partial + {reason}"

                    closed_trades.append({
                        "trade_id": pos["trade_id"],
                        "symbol": pos["symbol"],
                        "signal_type": pos["signal_type"],
                        "grade": pos["grade"],
                        "score": pos["score"],
                        "entry_date": pos["entry_date"],
                        "entry_price": round(pos["entry_price"], 2),
                        "stop": round(pos["initial_stop"], 2),
                        "target": round(pos["target"], 2),
                        "qty": pos["qty"],
                        "exit_date": current_date,
                        "exit_price": round(exit_price, 2),
                        "exit_reason": exit_reason_str,
                        "pnl": round(total_pnl, 2),
                        "pnl_pct": round(pnl_pct, 2),
                        "r_multiple": round(r_mult, 2),
                        "capped_r": round(capped_r, 2),
                        "trailed_r": round(trailed_r, 2),
                        "holding_days": pos["holding_days"],
                    })

        # 2. Check for new signals on current_date
        active_symbols_in_pos = {p["symbol"] for p in open_positions}

        for sym, sym_df in symbol_groups.items():
            if sym in active_symbols_in_pos:
                continue

            # Trailing window up to current_date
            window = sym_df[sym_df["date"] <= current_date]
            if len(window) < 15:  # Minimum for indicators
                continue

            ind_df = add_indicators(window)
            last_row = ind_df.iloc[-1]

            if last_row["date"] != current_date:
                continue

            sig_type = None
            if bool(last_row.get("SIGNAL", False)):
                sig_type = "BREAKOUT"
            elif ENABLE_PULLBACK and bool(last_row.get("SIGNAL_PULLBACK", False)):
                sig_type = "PULLBACK"

            if sig_type is not None:
                diag = diagnose_from_dataframe(ind_df, sym)
                grade = diag["grade"] if diag else "B"
                score = diag["score"] if diag else 60

                entry_val = float(last_row["Close"])
                atr_val = float(last_row["ATR14"])
                risk = compute_risk_parameters(
                    entry=entry_val,
                    atr=atr_val,
                    capital=capital_float,
                    risk_pct=RISK_PCT,
                )

                if risk is not None and risk["qty"] > 0:
                    pos = {
                        "trade_id": trade_counter,
                        "symbol": sym,
                        "signal_type": sig_type,
                        "grade": grade,
                        "score": score,
                        "entry_date": current_date,
                        "entry_price": risk["entry"],
                        "qty": risk["qty"],
                        "remaining_qty": risk["qty"],
                        "initial_stop": risk["stop"],
                        "current_stop": risk["stop"],
                        "target": risk["target"],
                        "risk_per_unit": risk["risk_per_unit"],
                        "partial_taken": False,
                        "realized_pnl": 0.0,
                        "holding_days": 0,
                        "highest_price": risk["entry"],
                    }
                    open_positions.append(pos)
                    active_symbols_in_pos.add(sym)
                    trade_counter += 1

        # 3. Calculate daily equity curve with open positions mark-to-market
        unrealized = 0.0
        for pos in open_positions:
            sym_df = symbol_groups.get(pos["symbol"])
            if sym_df is not None:
                cur_row = sym_df[sym_df["date"] == current_date]
                if not cur_row.empty:
                    cur_close = float(cur_row.iloc[-1]["Close"])
                    unrealized += (cur_close - pos["entry_price"]) * pos["remaining_qty"]

        daily_equity = current_cash + unrealized
        if daily_equity > peak_equity:
            peak_equity = daily_equity
        drawdown_pct = ((peak_equity - daily_equity) / peak_equity * 100.0) if peak_equity > 0 else 0.0

        equity_curve.append({
            "date": current_date,
            "value": round(daily_equity, 2),
            "drawdown": round(drawdown_pct, 2),
        })

    # Performance metrics calculation
    total_trades = len(closed_trades)
    winners = [t for t in closed_trades if t["r_multiple"] > 0]
    losers = [t for t in closed_trades if t["r_multiple"] <= 0]

    win_rate = round((len(winners) / total_trades * 100.0), 1) if total_trades > 0 else 0.0
    avg_win_R = round(sum(t["r_multiple"] for t in winners) / len(winners), 2) if winners else 0.0
    avg_loss_R = round(sum(t["r_multiple"] for t in losers) / len(losers), 2) if losers else 0.0
    expectancy_R = round((win_rate / 100.0 * avg_win_R) + ((1.0 - win_rate / 100.0) * avg_loss_R), 2)

    gross_profit = sum(t["pnl"] for t in winners)
    gross_loss = abs(sum(t["pnl"] for t in losers))
    profit_factor = round(gross_profit / gross_loss, 2) if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)
    max_dd_pct = round(max([e["drawdown"] for e in equity_curve], default=0.0), 2)

    # Breakdowns
    by_grade = {}
    for g in ["A+", "A", "B", "C"]:
        g_trades = [t for t in closed_trades if t["grade"] == g]
        g_win = [t for t in g_trades if t["r_multiple"] > 0]
        g_loss = [t for t in g_trades if t["r_multiple"] <= 0]
        g_wr = round(len(g_win) / len(g_trades) * 100.0, 1) if g_trades else 0.0
        g_aw = sum(t["r_multiple"] for t in g_win) / len(g_win) if g_win else 0.0
        g_al = sum(t["r_multiple"] for t in g_loss) / len(g_loss) if g_loss else 0.0
        g_exp = round((g_wr / 100.0 * g_aw) + ((1.0 - g_wr / 100.0) * g_al), 2)
        by_grade[g] = {
            "trades": len(g_trades),
            "win_rate": g_wr,
            "expectancy_R": g_exp,
            "total_pnl": round(sum(t["pnl"] for t in g_trades), 2),
        }

    by_signal_type = {}
    for s in ["BREAKOUT", "PULLBACK", "SPRING"]:
        s_trades = [t for t in closed_trades if t["signal_type"] == s]
        s_win = [t for t in s_trades if t["r_multiple"] > 0]
        s_loss = [t for t in s_trades if t["r_multiple"] <= 0]
        s_wr = round(len(s_win) / len(s_trades) * 100.0, 1) if s_trades else 0.0
        s_aw = sum(t["r_multiple"] for t in s_win) / len(s_win) if s_win else 0.0
        s_al = sum(t["r_multiple"] for t in s_loss) / len(s_loss) if s_loss else 0.0
        s_exp = round((s_wr / 100.0 * s_aw) + ((1.0 - s_wr / 100.0) * s_al), 2)
        by_signal_type[s] = {
            "trades": len(s_trades),
            "win_rate": s_wr,
            "expectancy_R": s_exp,
            "total_pnl": round(sum(t["pnl"] for t in s_trades), 2),
        }

    # Tail Capture
    tails = [t for t in winners if t["trailed_r"] > 2.0]
    pct_winners_past_2R = round(len(tails) / len(winners) * 100.0, 1) if winners else 0.0
    avg_R_of_tails = round(sum(t["trailed_r"] for t in tails) / len(tails), 2) if tails else 0.0
    total_trailed_R = sum(t["trailed_r"] for t in closed_trades)
    total_capped_R = sum(t["capped_r"] for t in closed_trades)
    capped_vs_trailed_delta = round(total_trailed_R - total_capped_R, 2)

    tail_capture = {
        "pct_winners_past_2R": pct_winners_past_2R,
        "avg_R_of_tails": avg_R_of_tails,
        "capped_vs_trailed_delta": capped_vs_trailed_delta,
    }

    results: Dict[str, Any] = {
        "period": {
            "start": eval_dates[0] if eval_dates else (start_date or ""),
            "end": eval_dates[-1] if eval_dates else (end_date or ""),
        },
        "trades": closed_trades,
        "equity_curve": equity_curve,
        "win_rate": win_rate,
        "avg_win_R": avg_win_R,
        "avg_loss_R": avg_loss_R,
        "expectancy_R": expectancy_R,
        "profit_factor": profit_factor,
        "max_drawdown_pct": max_dd_pct,
        "by_grade": by_grade,
        "by_signal_type": by_signal_type,
        "tail_capture": tail_capture,
    }

    return results


def main_cli():
    parser = argparse.ArgumentParser(description="Midcap Swing Scanner Rules-Replay Backtest Engine")
    parser.add_argument("--start", dest="start_date", help="Start date (YYYY-MM-DD)", default=None)
    parser.add_argument("--end", dest="end_date", help="End date (YYYY-MM-DD)", default=None)
    parser.add_argument("--archive-dir", dest="archive_dir", help="Path to archive directory", default="archive")
    parser.add_argument("--capital", dest="capital", type=float, help="Initial simulation capital", default=CAPITAL)
    parser.add_argument("--out", dest="out_file", help="Path to write JSON results", default="backtest_results.json")
    args = parser.parse_args()

    print(f"🚀 Running rules-replay backtest from {args.archive_dir}...")
    res = backtest(
        archive_dir=args.archive_dir,
        start_date=args.start_date,
        end_date=args.end_date,
        capital=args.capital,
    )

    with open(args.out_file, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=2)

    print(f"✅ Backtest completed. Output saved to {args.out_file}")
    print(f"Period: {res['period']['start']} -> {res['period']['end']}")
    print(f"Trades: {len(res['trades'])} | Win Rate: {res['win_rate']}% | Expectancy: {res['expectancy_R']}R | Max DD: {res['max_drawdown_pct']}%")
    print(f"Tail Capture: {res['tail_capture']['pct_winners_past_2R']}% past 2R, Delta: {res['tail_capture']['capped_vs_trailed_delta']}R")


if __name__ == "__main__":
    main_cli()
