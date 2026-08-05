"""
data/external_loaders.py — Loaders for cross-asset, FICC, and scoring data.
All data from the unified DATA.xlsx workbook.
Cache keys include source hash + production date for date-sensitive loaders.
"""
from __future__ import annotations
from pathlib import Path
from functools import lru_cache
import pandas as pd

try:
    import streamlit as st
    _HAS_ST = True
except Exception:
    _HAS_ST = False

def _cache_data(**_kwargs):
    if _HAS_ST:
        return st.cache_data(**_kwargs)
    def decorator(func):
        return lru_cache(maxsize=4)(func)
    return decorator

from data.loader import load_data, get_series, source_signature
from data.date_integrity import current_production_date

DATA_DIR = Path(__file__).parent
DATA_PATH = DATA_DIR / "DATA.xlsx"

PULSAR_SHEETS = ["Macro_GDP", "Macro_CPI", "Macro_Fiscal", "Rates_10Y",
                 "Equity_ToT", "Equity_FCI", "Equity_EPS", "Equity_Prices"]

_COL_MAP = {
    "SPX INDEX": "SPX", "DXY CURNCY": "DXY", "USGG10YR INDEX": "USGG10YR",
    "VIX INDEX": "VIX", "MOVE INDEX": "MOVE",
    "FXJPEMCS INDEX": "FXJPEMCS", "BCOM INDEX": "BCOM", "SPW INDEX": "SPW",
    "LF98OAS INDEX": "LF98OAS",
    "JYBSS12M CURNCY": "JYBSS12M",
    "USYC2Y10 INDEX": "USYC2Y10", "USGGBE10 INDEX": "USGGBE10",
    "USGGT10Y INDEX": "USGGT10Y",
    "USSWAP2 CURNCY": "USSWAP2", "USSWAP10 CURNCY": "USSWAP10",
    "USSWAP30 CURNCY": "USSWAP30",
    "HG1 COMDTY": "HG1", "CL1 COMDTY": "CL1",
    "GC1 COMDTY": "GC1", "S 1 COMDTY": "S1",
    "LUACOAS INDEX": "LUACOAS", "ITRXEBE CBBT CURNCY": "ITRXEBE",
}

def _norm_cols(df):
    renames = {c: _COL_MAP[str(c).strip()] for c in df.columns if str(c).strip() in _COL_MAP}
    return df.rename(columns=renames)

# ── Cross-asset (keyed by hash + production date) ──
def load_crossasset():
    return _load_crossasset_cached(source_signature(), current_production_date().isoformat())

@_cache_data(show_spinner=False)
def _load_crossasset_cached(source_hash, production_date):
    df = load_data(include_future=False)
    df = _norm_cols(df)
    req = ["SPX", "USGG10YR", "DXY"]
    if any(c not in df.columns for c in req): return None
    out = df[req].dropna(how="all")
    return out if len(out) else None

# ── FICC (keyed by hash + production date) ──
def load_ficc():
    return _load_ficc_cached(source_signature(), current_production_date().isoformat())

@_cache_data(show_spinner=False)
def _load_ficc_cached(source_hash, production_date):
    df = load_data(include_future=False)
    df = _norm_cols(df)
    cols = [c for c in _COL_MAP.values() if c in df.columns]
    if not cols: return None
    out = df[list(set(cols))].dropna(how="all")
    return out if len(out) else None

# ── Scoring (keyed by hash only — date filtering done by determine_scoring_asof) ──
def load_pulsar():
    return _load_pulsar_cached(source_signature())

@_cache_data(show_spinner=False)
def _load_pulsar_cached(source_hash):
    if not DATA_PATH.exists(): return None
    try:
        from models.scoring.engine import load_all
        return load_all(str(DATA_PATH))
    except Exception:
        return None

def ficc_has_columns(required):
    df = load_ficc()
    if df is None: return required
    return [c for c in required if c not in df.columns]

# ── SPX Sector Weights (keyed by hash + production date) ──
def load_spx_sector_weights(include_future: bool = False, current_date=None):
    """Load SPX_Sector_Weights using an explicit production-date cache key.

    ``current_date`` is honoured for deterministic audits/tests. Missing values
    are preserved; no weight is filled, normalised, or replaced with zero.
    """
    production_date = current_production_date(current_date=current_date).isoformat()
    return _load_sector_weights_cached(
        source_signature(),
        production_date,
        bool(include_future),
    )

@_cache_data(show_spinner=False)
def _load_sector_weights_cached(source_hash, production_date, include_future):
    if not DATA_PATH.exists(): return None
    try:
        w = pd.read_excel(DATA_PATH, sheet_name="SPX_Sector_Weights")
    except Exception:
        return None
    if "Date" not in w.columns:
        return None
    w["Date"] = pd.to_datetime(w["Date"], errors="coerce")
    w = w.dropna(subset=["Date"]).sort_values("Date").set_index("Date")
    # Coerce weight columns to numeric
    for c in w.columns:
        w[c] = pd.to_numeric(w[c], errors="coerce")
    if not include_future:
        cd = pd.Timestamp(production_date).date()
        w = w[w.index.date <= cd]
    return w if len(w) else None
