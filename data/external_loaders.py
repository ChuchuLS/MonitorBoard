"""
data/external_loaders.py
========================
Loaders for cross-asset, FICC, and scoring-model data.

All data now lives in the unified DATA.xlsx workbook:
  - Sheet1: daily market data (liquidity, rates, credit, cross-asset, FICC, FX)
  - Macro_GDP / Macro_CPI / etc.: scoring-model sheets

These functions preserve the original loader names for compatibility
(load_crossasset, load_ficc, load_pulsar) but they all read from DATA.xlsx.
No separate external files are used.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

# Guarded Streamlit import so this module works headless (smoke_test.py, scripts).
try:
    import streamlit as st
    _HAS_ST = True
except Exception:
    _HAS_ST = False


def _cache_data(**kwargs):
    """Use st.cache_data when Streamlit is available, otherwise no-op."""
    if _HAS_ST:
        return st.cache_data(**kwargs)
    return lambda f: f

from data.loader import load_data, get_series

DATA_DIR = Path(__file__).parent
DATA_PATH = DATA_DIR / "DATA.xlsx"

# Pulsar sheets expected inside DATA.xlsx (multi-sheet BDH format)
PULSAR_SHEETS = ["Macro_GDP", "Macro_CPI", "Macro_Fiscal", "Rates_10Y",
                 "Equity_ToT", "Equity_FCI", "Equity_EPS", "Equity_Prices"]

# Column name normalization (Bloomberg -> short code)
_COL_MAP = {
    "SPX INDEX": "SPX", "DXY CURNCY": "DXY", "USGG10YR INDEX": "USGG10YR",
    "BCOM INDEX": "BCOM", "LF98OAS INDEX": "LF98OAS",
    "USYC2Y10 INDEX": "USYC2Y10", "USGGBE10 INDEX": "USGGBE10",
    "SPW INDEX": "SPW", "VIX INDEX": "VIX",
    "FXJPEMCS INDEX": "FXJPEMCS", "JYBSS12M CURNCY": "JYBSS12M",
    "HG1 COMDTY": "HG1", "CL1 COMDTY": "CL1",
    "GC1 COMDTY": "GC1", "S 1 COMDTY": "S1",
    "LUACOAS INDEX": "LUACOAS", "ITRXEBE CBBT CURNCY": "ITRXEBE",
    "MOVE INDEX": "MOVE", "USGGT10Y INDEX": "USGGT10Y",
}


def _norm_cols(df: pd.DataFrame) -> pd.DataFrame:
    renames = {}
    for c in df.columns:
        key = str(c).strip()
        if key in _COL_MAP:
            renames[c] = _COL_MAP[key]
    return df.rename(columns=renames)


@_cache_data(show_spinner=False)
def load_crossasset() -> pd.DataFrame | None:
    """Load SPX / USGG10YR / DXY from DATA.xlsx Sheet1.

    Returns a DataFrame with normalized short column names, or None if
    the required columns are missing from Sheet1.
    """
    df = load_data()
    df = _norm_cols(df)
    required = ["SPX", "USGG10YR", "DXY"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return None
    out = df[required].dropna(how="all")
    return out if len(out) else None


@_cache_data(show_spinner=False)
def load_ficc() -> pd.DataFrame | None:
    """Load FICC / FX PCA columns from DATA.xlsx Sheet1.

    Returns a DataFrame with normalized short column names, or None if
    critical columns are missing from Sheet1.
    """
    df = load_data()
    df = _norm_cols(df)
    # Return all normalized columns that exist
    ficc_cols = [c for c in _COL_MAP.values() if c in df.columns]
    if not ficc_cols:
        return None
    out = df[list(set(ficc_cols))].dropna(how="all")
    return out if len(out) else None


@_cache_data(show_spinner=False)
def load_pulsar() -> dict | None:
    """Load scoring-model sheets from DATA.xlsx.

    Reads the Macro_GDP, Macro_CPI, Macro_Fiscal, Rates_10Y, Equity_*
    sheets embedded in DATA.xlsx. The scoring engine's read_sheet()
    function handles the BDH-style format (header row 4, data from row 6).
    """
    if not DATA_PATH.exists():
        return None
    try:
        from models.scoring.engine import load_all
        return load_all(str(DATA_PATH))
    except Exception:
        return None


def ficc_has_columns(required: list[str]) -> list[str]:
    df = load_ficc()
    if df is None:
        return required
    return [c for c in required if c not in df.columns]
