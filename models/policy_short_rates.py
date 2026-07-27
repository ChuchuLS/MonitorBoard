"""
models/policy_short_rates.py — Policy plumbing analytics.
See the Phase 6 spec for full documentation.
"""
from __future__ import annotations
import numpy as np, pandas as pd

POLICY_TICKERS = {
    "SOFR": "SOFRRATE INDEX", "EFFR": "FEDL01 INDEX", "IORB": "IRRBIOER INDEX",
    "TGCR": "TGCRRATE INDEX", "BGCR": "USBGRATE INDEX",
    "GCF": "UREPGATO INDEX", "TPR": "UREPTATO INDEX",
    "FED_TARGET_LOWER": "FDTRFTRL INDEX",
    "FED_RESERVES": "FARBRBFB INDEX", "FED_REPO": "FARWCBLS INDEX",
}
SPREAD_KEYS = ["SOFR", "EFFR", "TGCR", "BGCR", "GCF", "TPR"]
SPREAD_LABELS = {k: f"{k} − IORB" for k in SPREAD_KEYS}

def _col(df, key):
    t = POLICY_TICKERS.get(key)
    return df[t] if t and t in df.columns else None

def available_policy_inputs(df):
    return {k: (_col(df, k) is not None and _col(df, k).dropna().shape[0] > 0) for k in POLICY_TICKERS}

def build_policy_spreads(df):
    iorb = _col(df, "IORB")
    if iorb is None: return pd.DataFrame()
    iorb = iorb.dropna()
    spreads = {}
    for key in SPREAD_KEYS:
        s = _col(df, key)
        if s is None: continue
        s = s.dropna()
        common = s.index.intersection(iorb.index)
        if len(common) < 10: continue
        spreads[SPREAD_LABELS[key]] = 100 * (s.reindex(common) - iorb.reindex(common))
    return pd.DataFrame(spreads)

def build_funding_pressure_score(df, lookback_days=252):
    spreads_df = build_policy_spreads(df)
    if spreads_df.empty:
        return {"score": np.nan, "status": "No data", "n_spreads": 0}
    z_vals = []
    for col in spreads_df.columns:
        s = spreads_df[col].dropna()
        if len(s) < 21: continue
        now = float(s.iloc[-1])
        tail = s.iloc[-lookback_days:] if len(s) >= lookback_days else s
        mu, sigma = float(tail.mean()), float(tail.std())
        z_vals.append((now - mu) / sigma if sigma > 0 else 0.0)
    if not z_vals:
        return {"score": np.nan, "status": "No data", "n_spreads": 0}
    avg_z = float(np.mean(z_vals))
    if avg_z < -1: status = "Easy"
    elif avg_z < 1: status = "Normal"
    elif avg_z < 2: status = "Tight"
    else: status = "Very tight"
    return {"score": round(avg_z, 2), "status": status, "n_spreads": len(z_vals)}
