#!/usr/bin/env python3
"""
scripts/data_inventory.py
=========================
Audit every column in DATA.xlsx Sheet1 against the ticker registry.
Outputs: registered, unregistered, candidate columns, and RRP candidates.

Usage: python scripts/data_inventory.py
"""
import sys, os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pandas as pd
from config.tickers import (
    TICKERS, SPX_SECTOR_TICKERS, SPX_SECTOR_ETF_PROXIES,
    POLICY_FUTURES_TICKERS, RRP_CANDIDATES,
)

df = pd.read_excel("data/DATA.xlsx", sheet_name="Sheet1", nrows=5)
all_cols = set(str(c).strip().upper() for c in df.columns if not str(c).startswith("Unnamed"))

# Registered tickers (main TICKERS dict)
registered = set()
for key, tick in TICKERS.items():
    registered.add(tick.upper().strip())

# Also check sector, futures, etc.
for d in [SPX_SECTOR_TICKERS, SPX_SECTOR_ETF_PROXIES, POLICY_FUTURES_TICKERS]:
    for _, tick in d.items():
        registered.add(tick.upper().strip())

matched = all_cols & registered
unregistered = all_cols - registered

print(f"Sheet1: {len(all_cols)} data columns")
print(f"  Registered in config/tickers.py: {len(matched)}")
print(f"  Unregistered: {len(unregistered)}")
print()

if unregistered:
    print("=== UNREGISTERED COLUMNS ===")
    for c in sorted(unregistered):
        note = ""
        uc = c.upper()
        if "RRP" in uc:
            note = " ← RRP CANDIDATE (needs confirmation)"
        elif "GOVT" in uc:
            note = " ← possible real yield / linker"
        elif "CURNCY" in uc and "BGN" in uc:
            note = " ← possible FX spot"
        elif "EQUITY" in uc:
            note = " ← possible equity / ETF"
        elif "COMB" in uc:
            note = " ← possible futures contract"
        elif "INDEX" in uc:
            note = " ← possible index"
        print(f"  {c}{note}")

print()
print("=== RRP CANDIDATES (needs confirmation) ===")
for tick, info in RRP_CANDIDATES.items():
    present = tick.upper() in all_cols
    print(f"  {tick:25s}  {'IN DATA' if present else 'NOT IN DATA'}  "
          f"status={info['status']}  use={info['possible_use']}")

if __name__ == "__main__":
    pass
