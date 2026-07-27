"""
models/cross_asset/directional.py
=================================
8-regime directional classification using vol-scaled signals on
SPX / UST 10Y / DXY. Pure functions — no Streamlit.

Default: 20-day change ÷ 21-day trailing realized volatility.
The sign of each vol-scaled signal determines UP/DOWN.
2^3 = 8 directional regimes.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = ["SPX", "USGG10YR", "DXY"]

REGIMES_8 = {
    "R1": {"spx": "UP",   "rates": "UP",   "dxy": "UP",   "label": "SPX ↑ Rates ↑ DXY ↑", "color": "#22c55e"},
    "R2": {"spx": "UP",   "rates": "UP",   "dxy": "DOWN", "label": "SPX ↑ Rates ↑ DXY ↓", "color": "#06b6d4"},
    "R3": {"spx": "UP",   "rates": "DOWN", "dxy": "UP",   "label": "SPX ↑ Rates ↓ DXY ↑", "color": "#84cc16"},
    "R4": {"spx": "UP",   "rates": "DOWN", "dxy": "DOWN", "label": "SPX ↑ Rates ↓ DXY ↓", "color": "#3b82f6"},
    "R5": {"spx": "DOWN", "rates": "UP",   "dxy": "UP",   "label": "SPX ↓ Rates ↑ DXY ↑", "color": "#f97316"},
    "R6": {"spx": "DOWN", "rates": "UP",   "dxy": "DOWN", "label": "SPX ↓ Rates ↑ DXY ↓", "color": "#eab308"},
    "R7": {"spx": "DOWN", "rates": "DOWN", "dxy": "UP",   "label": "SPX ↓ Rates ↓ DXY ↑", "color": "#a855f7"},
    "R8": {"spx": "DOWN", "rates": "DOWN", "dxy": "DOWN", "label": "SPX ↓ Rates ↓ DXY ↓", "color": "#ef4444"},
}


def classify_8regime(prices: pd.DataFrame, mode: str = "vol_scaled",
                     lookback: int = 20, vol_window: int = 21) -> pd.DataFrame:
    """Classify each day into one of 8 directional regimes.
    Cleans prices to valid observations first so 20D = 20 trading days."""
    clean = prices[["SPX", "USGG10YR", "DXY"]].dropna()
    if len(clean) < lookback + vol_window + 1:
        return pd.DataFrame()

    spx_ret = np.log(clean["SPX"]).diff()
    ust_diff = clean["USGG10YR"].diff()
    dxy_ret = np.log(clean["DXY"]).diff()

    if mode == "vol_scaled":
        spx_20d = np.log(clean["SPX"]).diff(lookback)
        ust_20d = clean["USGG10YR"].diff(lookback)
        dxy_20d = np.log(clean["DXY"]).diff(lookback)
        spx_vol = spx_ret.rolling(vol_window).std()
        ust_vol = ust_diff.rolling(vol_window).std()
        dxy_vol = dxy_ret.rolling(vol_window).std()
        spx_sig = spx_20d / spx_vol.replace(0, np.nan)
        ust_sig = ust_20d / ust_vol.replace(0, np.nan)
        dxy_sig = dxy_20d / dxy_vol.replace(0, np.nan)
    else:
        spx_sig = np.log(clean["SPX"]).diff(lookback)
        ust_sig = clean["USGG10YR"].diff(lookback)
        dxy_sig = np.log(clean["DXY"]).diff(lookback)

    def _regime(row):
        s = "UP" if row["spx"] >= 0 else "DOWN"
        r = "UP" if row["rates"] >= 0 else "DOWN"
        d = "UP" if row["dxy"] >= 0 else "DOWN"
        for rk, rv in REGIMES_8.items():
            if rv["spx"] == s and rv["rates"] == r and rv["dxy"] == d:
                return rk
        return "R1"

    df = pd.DataFrame({
        "spx": spx_sig, "rates": ust_sig, "dxy": dxy_sig,
        "spx_signal": spx_sig, "rates_signal": ust_sig, "dxy_signal": dxy_sig,
    }).dropna()
    df["regime"] = df.apply(_regime, axis=1)
    return df


def days_in_current_regime(regime_series: pd.Series) -> int:
    """Count how many consecutive days the latest regime has been active."""
    if regime_series.empty:
        return 0
    current = regime_series.iloc[-1]
    count = 0
    for v in regime_series.iloc[::-1]:
        if v == current:
            count += 1
        else:
            break
    return count


# Backward-compatible alias
_days_in_current = days_in_current_regime


def regime_stats(regime_series: pd.Series, window_years: int = 2) -> pd.DataFrame:
    """Regime frequency table over the trailing window_years period."""
    if regime_series.empty:
        return pd.DataFrame()
    cutoff = regime_series.index.max() - pd.DateOffset(years=window_years)
    s = regime_series.loc[regime_series.index >= cutoff]
    total = len(s)
    current = s.iloc[-1] if len(s) else None

    changes = s != s.shift()
    run_ids = changes.cumsum()
    runs_list = []
    for _, grp in pd.DataFrame({"regime": s, "run": run_ids}).groupby("run"):
        runs_list.append({"regime": grp["regime"].iloc[0], "duration": len(grp)})
    runs_df = pd.DataFrame(runs_list)

    rows = []
    for i in range(1, 9):
        rk = f"R{i}"
        info = REGIMES_8[rk]
        sub = runs_df[runs_df["regime"] == rk]
        days = int(sub["duration"].sum()) if len(sub) else 0
        n_runs = len(sub)
        avg_run = float(sub["duration"].mean()) if n_runs else 0
        rows.append({
            "Regime": rk, "Description": info["label"], "Days": days,
            f"% of {window_years}Y": f"{days / total * 100:.1f}%" if total else "—",
            "Runs": n_runs, "AvgRun": round(avg_run, 1), "Active": rk == current,
        })
    return pd.DataFrame(rows)
