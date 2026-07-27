"""
models/global_rates.py
======================
Cross-country government yield curve analytics: 10Y overlay, curve snapshots,
2s10s slope ranking, 1M changes.

Pure functions — no Streamlit. Uses ticker definitions from config/tickers.py
and reads from DATA.xlsx / Sheet1 via the main loader's DataFrame.
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from config.tickers import TICKERS, REGIME_COUNTRIES

STANDARD_TENORS = ["2Y", "5Y", "10Y", "30Y"]
TENOR_NUMERIC = {"2Y": 2, "5Y": 5, "10Y": 10, "30Y": 30}

COUNTRY_LABELS = {
    "US": "United States", "DE": "Germany", "JP": "Japan",
    "UK": "United Kingdom", "CA": "Canada", "AU": "Australia",
    "CH": "Switzerland",
}


def _ticker(country: str, tenor: str) -> str | None:
    key = f"{country}_{tenor}"
    return TICKERS.get(key)


def available_country_curves(df: pd.DataFrame) -> dict:
    """Return {country: [available tenors]} for countries with ≥1 tenor of data."""
    out = {}
    for country in REGIME_COUNTRIES:
        tenors = []
        for t in STANDARD_TENORS:
            tick = _ticker(country, t)
            if tick and tick in df.columns and df[tick].dropna().shape[0] > 0:
                tenors.append(t)
        if tenors:
            out[country] = tenors
    return out


def _yield(df: pd.DataFrame, country: str, tenor: str) -> pd.Series:
    tick = _ticker(country, tenor)
    if tick and tick in df.columns:
        return df[tick]
    return pd.Series(dtype=float)


def build_10y_overlay(df: pd.DataFrame, lookback_days: int = 252) -> pd.DataFrame:
    """Normalized 10Y yield overlay: each country scaled to own lookback min/max."""
    countries = available_country_curves(df)
    out = pd.DataFrame(index=df.index)
    for c, tenors in countries.items():
        if "10Y" not in tenors:
            continue
        s = _yield(df, c, "10Y").dropna()
        if len(s) < lookback_days // 2:
            continue
        tail = s.iloc[-lookback_days:] if len(s) >= lookback_days else s
        lo, hi = tail.min(), tail.max()
        rng = hi - lo
        if rng > 0:
            out[c] = (s - lo) / rng
        else:
            out[c] = 0.5
    return out.iloc[-lookback_days:] if len(out) >= lookback_days else out


def build_curve_snapshots(df: pd.DataFrame, asof=None) -> pd.DataFrame:
    """Latest yield curve snapshot for each available country."""
    countries = available_country_curves(df)
    if asof is None:
        asof = df.index.max()
    rows = []
    for c, tenors in countries.items():
        for t in tenors:
            s = _yield(df, c, t)
            val = s.loc[:asof].dropna()
            if len(val):
                rows.append({"country": c, "label": COUNTRY_LABELS.get(c, c),
                             "tenor": t, "tenor_num": TENOR_NUMERIC[t],
                             "yield": float(val.iloc[-1])})
    return pd.DataFrame(rows)


def build_slope_ranking(df: pd.DataFrame, front: str = "2Y",
                        back: str = "10Y") -> pd.DataFrame:
    """2s10s (or any pair) slope ranking across countries, steepest first."""
    countries = available_country_curves(df)
    rows = []
    for c, tenors in countries.items():
        if front not in tenors or back not in tenors:
            continue
        f_s = _yield(df, c, front).dropna()
        b_s = _yield(df, c, back).dropna()
        if len(f_s) == 0 or len(b_s) == 0:
            continue
        f_val = float(f_s.iloc[-1])
        b_val = float(b_s.iloc[-1])
        slope_bp = 100 * (b_val - f_val)
        rows.append({"country": c, "label": COUNTRY_LABELS.get(c, c),
                     f"{front}": f_val, f"{back}": b_val,
                     "slope_bp": slope_bp, "inverted": slope_bp < 0})
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values("slope_bp", ascending=False).reset_index(drop=True)
    return out


def country_1m_changes(df: pd.DataFrame, lookback_days: int = 21) -> pd.DataFrame:
    """1M change in 10Y yield for each country."""
    countries = available_country_curves(df)
    rows = []
    for c, tenors in countries.items():
        if "10Y" not in tenors:
            continue
        s = _yield(df, c, "10Y").dropna()
        if len(s) <= lookback_days:
            continue
        now = float(s.iloc[-1])
        ago = float(s.iloc[-lookback_days - 1])
        chg_bp = 100 * (now - ago)
        rows.append({"country": c, "label": COUNTRY_LABELS.get(c, c),
                     "yield_10y": now, "yield_10y_1m_ago": ago,
                     "change_1m_bp": chg_bp})
    out = pd.DataFrame(rows)
    if not out.empty:
        out = out.sort_values("change_1m_bp", ascending=False).reset_index(drop=True)
    return out
