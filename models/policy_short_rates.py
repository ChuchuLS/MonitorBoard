"""
models/policy_short_rates.py
============================
Policy plumbing analytics. Pure functions — no Streamlit.

Uses ONLY confirmed ticker mappings from config.tickers.TICKERS.
Does NOT use RRP_CANDIDATES, TOMOTCSO, RRPQTOON, or RRPQONAR.

Units: spot rates in %, spreads in bp (basis points).
       spread_bp = 100 * (rate_% - IORB_%)

Pressure thresholds are DIAGNOSTIC, not official Federal Reserve classifications.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from config.tickers import TICKERS

# ── Confirmed production keys ──
# Only keys whose Bloomberg field descriptions are documented in the project.
CONFIRMED_POLICY_KEYS = [
    "SOFR",              # SOFRRATE INDEX — Secured Overnight Financing Rate
    "EFFR",              # FEDL01 INDEX — Effective Federal Funds Rate
    "IORB",              # IRRBIOER INDEX — Interest on Reserve Balances
    "TGCR",              # TGCRRATE INDEX — Tri-Party General Collateral Rate
    "BGCR",              # USBGRATE INDEX — Broad General Collateral Rate
    "GCF",               # UREPGATO INDEX — GCF Repo Average Rate (OFR, daily, %)
    "TPR",               # UREPTATO INDEX — Tri-Party Repo Average Rate (OFR, daily, %)
    "FED_TARGET_LOWER",  # FDTRFTRL INDEX — Fed Funds Target Rate Lower Bound
    "FED_RESERVES",      # FARBRBFB INDEX — Reserve Balances (H.4.1, USD mn, weekly)
    "CENTRAL_BANK_LIQUIDITY_SWAPS",  # FARWCBLS INDEX — CB Liquidity Swaps (NOT repo/SRF)
]

# No longer any needs-confirmation keys — all four are now confirmed via Bloomberg DES
NEEDS_CONFIRMATION_KEYS: list[str] = []

# Keys eligible for spread computation (vs IORB) — all confirmed daily rates
SPREAD_KEYS = ["SOFR", "EFFR", "TGCR", "BGCR", "GCF", "TPR"]

# Stale threshold: exclude a spread from the score if its latest valid
# observation is more than this many business days behind the freshest spread.
STALE_THRESHOLD_BDAYS = 5

# Pressure thresholds (DIAGNOSTIC, not official Fed classifications)
# Boundaries: z<-1 Easy, -1<=z<=+1 Normal, +1<z<=+2 Tight, z>+2 Very tight
def classify_pressure_z(z: float) -> str:
    """Classify a z-score into a pressure status label.
    Uses closed boundaries at -1 and +1 (inclusive Normal)."""
    if pd.isna(z):
        return "Constant series"
    if z < -1:
        return "Easy"
    if z <= 1:
        return "Normal"
    if z <= 2:
        return "Tight"
    return "Very tight"


def _get_series(df: pd.DataFrame, key: str) -> pd.Series:
    """Get a series by ticker key. Returns empty Series if not found."""
    tick = TICKERS.get(key)
    if tick and tick in df.columns:
        return df[tick].dropna()
    return pd.Series(dtype=float)


def available_policy_inputs(df: pd.DataFrame) -> dict:
    """Return {key: {"available": bool, "ticker": str, "obs": int,
    "latest_date": date|None, "status": str}} for each policy key."""
    result = {}
    for key in CONFIRMED_POLICY_KEYS + NEEDS_CONFIRMATION_KEYS:
        tick = TICKERS.get(key, "NOT REGISTERED")
        s = _get_series(df, key)
        if len(s) > 0:
            result[key] = {
                "available": True, "ticker": tick, "obs": len(s),
                "latest_date": s.index[-1].date(),
                "status": "confirmed" if key in CONFIRMED_POLICY_KEYS else "needs_confirmation",
            }
        else:
            result[key] = {
                "available": False, "ticker": tick, "obs": 0,
                "latest_date": None,
                "status": "confirmed" if key in CONFIRMED_POLICY_KEYS else "needs_confirmation",
            }
    return result


def build_short_rate_snapshot(df: pd.DataFrame, asof=None,
                              lookback_days: int = 21) -> pd.DataFrame:
    """Latest level + 1M change for each confirmed short rate."""
    rows = []
    for key in CONFIRMED_POLICY_KEYS:
        s = _get_series(df, key)
        if len(s) < lookback_days + 1:
            continue
        if asof:
            s = s.loc[:pd.Timestamp(asof)]
        if len(s) < lookback_days + 1:
            continue
        now = float(s.iloc[-1])
        ago = float(s.iloc[-lookback_days - 1])
        chg_bp = 100 * (now - ago)
        label = key
        if key == "FED_TARGET_LOWER":
            label = "Fed target lower bound"
        idx_max = df.index.max()
        if pd.isna(idx_max):
            idx_max = s.index[-1]
        age = max(0, len(pd.bdate_range(s.index[-1], idx_max)) - 1)
        rows.append({
            "indicator": label, "key": key,
            "ticker": TICKERS.get(key, "?"),
            "latest_pct": now, "1m_change_bp": round(chg_bp, 1),
            "latest_valid_date": s.index[-1].date(),
            "age_bdays": age,
        })
    return pd.DataFrame(rows)


def build_policy_spreads(df: pd.DataFrame, asof=None) -> pd.DataFrame:
    """Compute confirmed spreads vs IORB in basis points."""
    iorb = _get_series(df, "IORB")
    if len(iorb) == 0:
        return pd.DataFrame()

    spreads = {}
    for key in SPREAD_KEYS:
        s = _get_series(df, key)
        if len(s) == 0:
            continue
        common = s.index.intersection(iorb.index)
        if len(common) < 10:
            continue
        spread_bp = 100 * (s.reindex(common) - iorb.reindex(common))
        if asof:
            spread_bp = spread_bp.loc[:pd.Timestamp(asof)]
        spreads[f"{key} − IORB"] = spread_bp
    return pd.DataFrame(spreads)


def build_funding_pressure_table(df: pd.DataFrame, asof=None,
                                 lookback_days: int = 252) -> pd.DataFrame:
    """Per-spread detail table with dates, z-scores, and inclusion status."""
    spreads_df = build_policy_spreads(df, asof)
    if spreads_df.empty:
        return pd.DataFrame()

    # Find the freshest observation date across all spreads
    latest_dates = {}
    for col in spreads_df.columns:
        s = spreads_df[col].dropna()
        if len(s):
            latest_dates[col] = s.index[-1]
    if not latest_dates:
        return pd.DataFrame()
    freshest = max(latest_dates.values())

    rows = []
    for col in spreads_df.columns:
        s = spreads_df[col].dropna()
        if len(s) < 21:
            continue
        now = float(s.iloc[-1])
        lvd = s.index[-1]
        age = len(pd.bdate_range(lvd, freshest)) - 1

        chg_1d = float(s.diff(1).iloc[-1]) if len(s) > 1 else np.nan
        chg_5d = float(s.diff(5).iloc[-1]) if len(s) > 5 else np.nan
        chg_21d = float(s.diff(21).iloc[-1]) if len(s) > 21 else np.nan

        tail = s.iloc[-lookback_days:] if len(s) >= lookback_days else s
        pctl = float((tail < now).sum() / len(tail) * 100)
        mu, sigma = float(tail.mean()), float(tail.std())

        if sigma > 1e-10:
            z = (now - mu) / sigma
        else:
            z = np.nan  # constant series — do NOT silently assign z=0

        # Determine status
        status = classify_pressure_z(z)

        # Inclusion logic
        stale = age > STALE_THRESHOLD_BDAYS
        included = not stale and pd.notna(z)
        if stale:
            exclusion = f"Stale ({age} bdays behind freshest)"
        elif pd.isna(z):
            exclusion = "Constant series (σ=0)"
        else:
            exclusion = ""

        rows.append({
            "Indicator": col,
            "Latest_bp": round(now, 1),
            "Latest_valid_date": lvd.date(),
            "Age_business_days": age,
            "Change_1D_bp": round(chg_1d, 1) if pd.notna(chg_1d) else np.nan,
            "Change_5D_bp": round(chg_5d, 1) if pd.notna(chg_5d) else np.nan,
            "Change_21D_bp": round(chg_21d, 1) if pd.notna(chg_21d) else np.nan,
            "Percentile_1Y": round(pctl, 0),
            "ZScore_1Y": round(z, 2) if pd.notna(z) else np.nan,
            "Status": status,
            "Included_in_score": included,
            "Exclusion_reason": exclusion,
        })
    return pd.DataFrame(rows)


def build_funding_pressure_score(df: pd.DataFrame, asof=None,
                                 lookback_days: int = 252) -> dict:
    """Aggregate pressure score from included confirmed spreads."""
    table = build_funding_pressure_table(df, asof, lookback_days)
    if table.empty:
        return {
            "score": np.nan, "status": "No data", "n_spreads": 0,
            "latest_date": None, "inputs": [], "missing": list(SPREAD_KEYS),
            "excluded_stale": [], "dates_aligned": True,
            "methodology": "No confirmed spread data available.",
        }

    included = table[table["Included_in_score"]]
    excluded = table[~table["Included_in_score"]]
    missing_keys = [k for k in SPREAD_KEYS if f"{k} − IORB" not in table["Indicator"].values]

    if included.empty:
        return {
            "score": np.nan, "status": "No includable spreads", "n_spreads": 0,
            "latest_date": None,
            "inputs": [], "missing": missing_keys,
            "excluded_stale": excluded["Indicator"].tolist(),
            "dates_aligned": True,
            "methodology": "All spreads excluded (stale or constant).",
        }

    z_vals = included["ZScore_1Y"].dropna().tolist()
    if not z_vals:
        return {
            "score": np.nan, "status": "No valid z-scores", "n_spreads": 0,
            "latest_date": None,
            "inputs": included["Indicator"].tolist(),
            "missing": missing_keys,
            "excluded_stale": excluded["Indicator"].tolist(),
            "dates_aligned": True,
            "methodology": "z-scores all NaN.",
        }

    avg_z = float(np.mean(z_vals))
    status = classify_pressure_z(avg_z)

    dates = included["Latest_valid_date"].unique()
    dates_aligned = len(dates) == 1
    latest_date = max(dates) if len(dates) else None

    return {
        "score": round(avg_z, 2),
        "status": status,
        "n_spreads": len(z_vals),
        "latest_date": latest_date,
        "inputs": included["Indicator"].tolist(),
        "missing": missing_keys,
        "excluded_stale": excluded[excluded["Exclusion_reason"].str.contains("Stale", na=False)]["Indicator"].tolist(),
        "dates_aligned": dates_aligned,
        "methodology": (
            f"Average 1Y z-score of {len(z_vals)} confirmed spreads vs IORB. "
            f"Thresholds: z<−1 Easy · ±1 Normal · +1–2 Tight · >+2 Very tight. "
            f"Diagnostic only — not official Fed classifications. "
            f"Stale threshold: {STALE_THRESHOLD_BDAYS} bdays."
        ),
    }


def build_policy_current_reading(df: pd.DataFrame, asof=None) -> dict:
    """Summary for the Current Reading box."""
    pressure = build_funding_pressure_score(df, asof)
    table = build_funding_pressure_table(df, asof)
    snap = build_short_rate_snapshot(df, asof)

    reading = {
        "pressure_score": pressure["score"],
        "pressure_status": pressure["status"],
        "n_spreads": pressure["n_spreads"],
        "latest_date": pressure["latest_date"],
        "dates_aligned": pressure["dates_aligned"],
        "inputs": pressure["inputs"],
        "missing": pressure["missing"],
        "excluded_stale": pressure["excluded_stale"],
        "methodology": pressure["methodology"],
    }

    # Tightest / easiest from included spreads
    if not table.empty:
        incl = table[table["Included_in_score"]]
        if not incl.empty:
            tightest_idx = incl["ZScore_1Y"].idxmax()
            easiest_idx = incl["ZScore_1Y"].idxmin()
            reading["tightest"] = {
                "indicator": incl.loc[tightest_idx, "Indicator"],
                "z": float(incl.loc[tightest_idx, "ZScore_1Y"]),
                "bp": float(incl.loc[tightest_idx, "Latest_bp"]),
            }
            reading["easiest"] = {
                "indicator": incl.loc[easiest_idx, "Indicator"],
                "z": float(incl.loc[easiest_idx, "ZScore_1Y"]),
                "bp": float(incl.loc[easiest_idx, "Latest_bp"]),
            }

    # Key spot rates
    if not snap.empty:
        for key in ["SOFR", "EFFR", "IORB"]:
            row = snap[snap["key"] == key]
            if not row.empty:
                reading[f"{key.lower()}_pct"] = row.iloc[0]["latest_pct"]

    return reading
