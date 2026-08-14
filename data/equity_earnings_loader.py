"""Production-safe loaders for Equity_EPS and Equity_Prices.

The workbook stores Equity_EPS as independent Bloomberg BDH spills with
interleaved Date/value columns.  Equity_Prices uses one shared Date column.
This loader preserves each EPS series' own Date column and never forward-fills,
interpolates, or replaces missing values with zero.
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


def _cache_data(**kwargs):
    if _HAS_ST:
        return st.cache_data(**kwargs)
    def decorator(func):
        return lru_cache(maxsize=4)(func)
    return decorator


def _clean_label(value) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


# Newly added Bloomberg blocks can keep their own Date/value columns while the
# internal short-code row is blank. Resolve only the explicitly confirmed
# ticker rows below; never infer a code from another market or relabel a proxy.
# Normalisation is case/space insensitive so workbook display casing can change
# without breaking the production mapping.
_TICKER_CODE_ALIASES = {
    "CSIA500INDEX": "CSI_A500",
    "DJIINDEX": "DJI",
    "NIFTYINDEX": "NIFTY50",
    "VN30INDEX": "VN30",
}
_CODE_COUNTRY_FALLBACK = {
    "CSI_A500": "China",
    "DJI": "USA",
    "NIFTY50": "India",
    "VN30": "Vietnam",
}


def _normalise_token(value) -> str:
    return "".join(ch for ch in _clean_label(value).upper() if ch.isalnum())


def _canonical_code(raw_code, ticker) -> str:
    code = _clean_label(raw_code)
    if code:
        return code
    return _TICKER_CODE_ALIASES.get(_normalise_token(ticker), "")


def _parse_eps_sheet(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = pd.read_excel(path, sheet_name="Equity_EPS", header=None)
    if raw.empty or raw.shape[0] < 6 or raw.shape[1] < 2:
        return pd.DataFrame(), pd.DataFrame()

    series = {}
    meta_rows = []
    pair_count = raw.shape[1] // 2
    for pair in range(pair_count):
        date_col = pair * 2
        value_col = date_col + 1
        ticker = _clean_label(raw.iloc[4, value_col])
        code = _canonical_code(raw.iloc[3, value_col], ticker)
        if not code:
            continue
        dates = pd.to_datetime(raw.iloc[5:, date_col], errors="coerce")
        values = pd.to_numeric(raw.iloc[5:, value_col], errors="coerce")
        s = pd.Series(values.to_numpy(), index=dates, name=code)
        s = s[~s.index.isna()].dropna().sort_index()
        s = s[~s.index.duplicated(keep="last")]
        series[code] = s
        meta_rows.append({
            "code": code,
            "country": _clean_label(raw.iloc[2, value_col]) or _CODE_COUNTRY_FALLBACK.get(code, ""),
            "ticker": ticker,
            "eps_field": "BEST_EPS",
            "forecast_period_override": "1FY",
            "frequency": "weekly",
        })

    eps = pd.concat(series, axis=1).sort_index() if series else pd.DataFrame()
    metadata = pd.DataFrame(meta_rows).set_index("code") if meta_rows else pd.DataFrame()
    return eps, metadata


def _parse_price_sheet(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = pd.read_excel(path, sheet_name="Equity_Prices", header=None)
    if raw.empty or raw.shape[0] < 6 or raw.shape[1] < 2:
        return pd.DataFrame(), pd.DataFrame()

    dates = pd.to_datetime(raw.iloc[5:, 0], errors="coerce")
    series = {}
    meta_rows = []
    for value_col in range(1, raw.shape[1]):
        ticker = _clean_label(raw.iloc[4, value_col])
        code = _canonical_code(raw.iloc[3, value_col], ticker)
        if not code:
            continue
        values = pd.to_numeric(raw.iloc[5:, value_col], errors="coerce")
        s = pd.Series(values.to_numpy(), index=dates, name=code)
        s = s[~s.index.isna()].dropna().sort_index()
        s = s[~s.index.duplicated(keep="last")]
        series[code] = s
        meta_rows.append({
            "code": code,
            "country": _clean_label(raw.iloc[2, value_col]) or _CODE_COUNTRY_FALLBACK.get(code, ""),
            "ticker": ticker,
            "price_field": "workbook value; ticker row identifies cash index",
            "frequency": "daily",
        })

    prices = pd.concat(series, axis=1).sort_index() if series else pd.DataFrame()
    metadata = pd.DataFrame(meta_rows).set_index("code") if meta_rows else pd.DataFrame()
    return prices, metadata


def load_equity_earnings_data(include_future: bool = False, current_date=None) -> dict:
    """Load EPS and index-price panels with a production-date cache key."""
    production_date = current_production_date(current_date=current_date).isoformat()
    return _load_equity_earnings_cached(
        source_signature(), production_date, bool(include_future)
    )


@_cache_data(show_spinner=False)
def _load_equity_earnings_cached(source_hash, production_date, include_future) -> dict:
    if not DATA_PATH.exists():
        return {"eps": pd.DataFrame(), "prices": pd.DataFrame(), "metadata": pd.DataFrame()}

    eps, eps_meta = _parse_eps_sheet(DATA_PATH)
    prices, px_meta = _parse_price_sheet(DATA_PATH)
    cutoff = pd.Timestamp(production_date)
    if not include_future:
        if not eps.empty:
            eps = eps.loc[eps.index <= cutoff]
        if not prices.empty:
            prices = prices.loc[prices.index <= cutoff]

    metadata = eps_meta.join(px_meta, how="outer", lsuffix="_eps", rsuffix="_price")
    return {
        "eps": eps,
        "prices": prices,
        "metadata": metadata,
        "production_date": pd.Timestamp(production_date).date(),
        "source_hash": source_hash,
    }
