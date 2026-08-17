"""Optional index-breadth input loader.

The current workbook does not contain constituent-level breadth series.  If a
future ``Index_Breadth`` sheet is supplied, it must be long-form with one row
per Date + Code and the documented semantic columns.  Missing columns and
observations remain missing; nothing is inferred from index-level prices.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

try:
    import streamlit as st
    _HAS_ST = True
except Exception:
    _HAS_ST = False

from data.date_integrity import current_production_date
from data.loader import source_signature


DATA_PATH = Path(__file__).parent / "DATA.xlsx"
SHEET_NAME = "Index_Breadth"

BREADTH_METRICS = {
    "advance_decline": "Advancers minus decliners",
    "new_52w_highs_pct": "% new 52-week highs",
    "new_52w_lows_pct": "% new 52-week lows",
    "above_50dma_pct": "% above 50DMA",
    "above_200dma_pct": "% above 200DMA",
    "rsi14_above70_pct": "% with 14-day RSI > 70",
    "rsi14_below30_pct": "% with 14-day RSI < 30",
    "index_put_call_ratio": "Index put/call ratio",
}

_COLUMN_ALIASES = {
    "date": "date",
    "code": "code",
    "index": "code",
    "indexcode": "code",
    "advancedecline": "advance_decline",
    "advancersminusdecliners": "advance_decline",
    "new52whighspct": "new_52w_highs_pct",
    "new52weekhighspct": "new_52w_highs_pct",
    "new52wlowspct": "new_52w_lows_pct",
    "new52weeklowspct": "new_52w_lows_pct",
    "above50dmapct": "above_50dma_pct",
    "above200dmapct": "above_200dma_pct",
    "rsi14above70pct": "rsi14_above70_pct",
    "rsi14below30pct": "rsi14_below30_pct",
    "indexputcallratio": "index_put_call_ratio",
    "putcallratio": "index_put_call_ratio",
}


def _cache_data(**kwargs):
    if _HAS_ST:
        return st.cache_data(**kwargs)
    def decorator(func):
        return lru_cache(maxsize=4)(func)
    return decorator


def _token(value) -> str:
    return "".join(ch for ch in str(value).lower() if ch.isalnum())


def load_index_breadth(include_future: bool = False, current_date=None) -> pd.DataFrame:
    production_date = current_production_date(current_date=current_date).isoformat()
    return _load_index_breadth_cached(
        source_signature(), production_date, bool(include_future)
    )


@_cache_data(show_spinner=False)
def _load_index_breadth_cached(source_hash, production_date, include_future) -> pd.DataFrame:
    if not DATA_PATH.exists():
        return pd.DataFrame()
    try:
        raw = pd.read_excel(DATA_PATH, sheet_name=SHEET_NAME)
    except Exception:
        return pd.DataFrame()
    if raw.empty:
        return pd.DataFrame()

    rename = {}
    for column in raw.columns:
        canonical = _COLUMN_ALIASES.get(_token(column))
        if canonical:
            rename[column] = canonical
    frame = raw.rename(columns=rename)
    if "date" not in frame.columns or "code" not in frame.columns:
        return pd.DataFrame()
    keep = ["date", "code"] + [c for c in BREADTH_METRICS if c in frame.columns]
    frame = frame[keep].copy()
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame["code"] = frame["code"].astype(str).str.strip()
    frame = frame.dropna(subset=["date"])
    frame = frame.loc[frame["code"].ne("")]
    for column in BREADTH_METRICS:
        if column not in frame.columns:
            frame[column] = pd.NA
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    if not include_future:
        frame = frame.loc[frame["date"] <= pd.Timestamp(production_date)]
    frame = frame.sort_values(["code", "date"])
    frame = frame.drop_duplicates(["code", "date"], keep="last")
    return frame.set_index(["date", "code"])[list(BREADTH_METRICS)]
