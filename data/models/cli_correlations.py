"""
models/cli_correlations.py
==========================
Rolling correlations between the Composite Liquidity Index and external assets
(HSI, Bitcoin, or any other series).

Pure functions — no Streamlit. Only produces output when both series have
real data. Does NOT fabricate, proxy, or substitute any missing series.

Required tickers (not yet in DATA.xlsx):
  - HSI INDEX (Hang Seng daily close)
  - XBTUSD BGN Curncy or equivalent (Bitcoin daily close)
"""
from __future__ import annotations

import pandas as pd
import numpy as np


# Tickers we'd use if they were in DATA.xlsx
CORR_TARGETS = {
    "HSI": {
        "candidates": ["HSI INDEX", "HSI EQUITY"],
        "label": "Hang Seng Index",
        "transform": "log_return",  # correlate CLI level change vs HSI log return
    },
    "BTC": {
        "candidates": ["XBTUSD BGN CURNCY", "XBTUSD INDEX", "BTCUSD CURNCY"],
        "label": "Bitcoin (USD)",
        "transform": "log_return",
    },
    "SPX": {
        "candidates": ["SPX INDEX"],
        "label": "S&P 500",
        "transform": "log_return",
    },
}


def find_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Find the first matching column from a list of candidates."""
    df_cols_upper = {c.upper().strip(): c for c in df.columns}
    for cand in candidates:
        key = cand.upper().strip()
        if key in df_cols_upper:
            return df_cols_upper[key]
    return None


def available_targets(df: pd.DataFrame) -> dict[str, str]:
    """Return {target_key: actual_column_name} for targets that exist in the data."""
    out = {}
    for key, info in CORR_TARGETS.items():
        col = find_column(df, info["candidates"])
        if col is not None:
            s = df[col].dropna()
            if len(s) > 20:  # minimum for a rolling window
                out[key] = col
    return out


def build_rolling_correlation(cli_series: pd.Series, asset_series: pd.Series,
                              window: int = 20,
                              transform: str = "log_return") -> pd.Series:
    """Compute rolling correlation between CLI level changes and asset returns.

    cli_series: the Composite Liquidity Index level (higher = looser)
    asset_series: the raw price/level of the external asset
    transform: "log_return" (default) or "level_change"

    Returns a Series of rolling correlations indexed by date.
    """
    cli_chg = cli_series.diff()

    if transform == "log_return":
        asset_chg = np.log(asset_series).diff()
    else:
        asset_chg = asset_series.diff()

    # Align on common non-NaN dates
    both = pd.DataFrame({"cli": cli_chg, "asset": asset_chg}).dropna()
    if len(both) < window + 1:
        return pd.Series(dtype=float)

    return both["cli"].rolling(window).corr(both["asset"])


def build_all_correlations(df: pd.DataFrame, cli_index: pd.Series,
                           window: int = 20) -> dict[str, pd.Series]:
    """Build rolling correlations for all available targets.

    Returns {target_key: correlation_series}. Empty dict if no targets available.
    Does NOT fabricate correlations for missing data.
    """
    targets = available_targets(df)
    if not targets:
        return {}

    result = {}
    for key, col in targets.items():
        info = CORR_TARGETS[key]
        corr = build_rolling_correlation(
            cli_index, df[col], window=window,
            transform=info.get("transform", "log_return"),
        )
        if len(corr.dropna()) > 0:
            result[key] = corr
    return result
