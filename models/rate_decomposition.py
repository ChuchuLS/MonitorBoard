"""
models/rate_decomposition.py
============================
Decompose nominal yield moves into real-rate and inflation (breakeven)
components. Uses the identity: nominal ≡ real + breakeven, so the residual
is zero by construction.

Pure functions — no Streamlit. Reads a pandas DataFrame indexed by date
with Bloomberg-style column names from DATA.xlsx / Sheet1.
"""
from __future__ import annotations
import pandas as pd
import numpy as np

US_NOMINAL = {
    "2Y": "USGG2YR INDEX", "5Y": "USGG5YR INDEX",
    "10Y": "USGG10YR INDEX", "30Y": "USGG30YR INDEX",
}
US_BREAKEVEN = {
    "2Y": "USGGBE02 INDEX", "5Y": "USGGBE05 INDEX",
    "10Y": "USGGBE10 INDEX", "30Y": "USGGBE30 INDEX",
}
TENORS = ["2Y", "5Y", "10Y", "30Y"]


def _col(df: pd.DataFrame, bbg: str) -> pd.Series | None:
    if bbg in df.columns:
        return df[bbg]
    return None


def available_us_tenors(df: pd.DataFrame) -> list[str]:
    """Return tenors for which both nominal and breakeven columns exist and have data."""
    out = []
    for t in TENORS:
        n = _col(df, US_NOMINAL.get(t, ""))
        b = _col(df, US_BREAKEVEN.get(t, ""))
        if n is not None and b is not None and n.dropna().shape[0] > 0 and b.dropna().shape[0] > 0:
            out.append(t)
    return out


def _get_curves(df: pd.DataFrame, tenors: list[str] | None = None):
    """Return (nominal, real, inflation) DataFrames aligned by date."""
    tenors = tenors or available_us_tenors(df)
    nominal = pd.DataFrame({t: df[US_NOMINAL[t]] for t in tenors if US_NOMINAL[t] in df.columns})
    inflation = pd.DataFrame({t: df[US_BREAKEVEN[t]] for t in tenors if US_BREAKEVEN[t] in df.columns})
    real = nominal - inflation
    return nominal, real, inflation


def build_us_curve_snapshot(df: pd.DataFrame, asof=None, lookback_days: int = 21) -> pd.DataFrame:
    """Snapshot of the US curve: nominal / real / inflation levels + 1M changes.
    Uses valid observations per tenor — ignores empty/weekend rows."""
    tenors = available_us_tenors(df)
    if not tenors:
        return pd.DataFrame()
    nominal, real, inflation = _get_curves(df, tenors)

    rows = []
    for t in tenors:
        base = pd.DataFrame({
            "nominal": nominal[t], "real": real[t], "inflation": inflation[t],
        }).dropna()
        if len(base) < lookback_days + 1:
            continue
        if asof is not None:
            base = base.loc[:pd.Timestamp(asof)]
            if len(base) < lookback_days + 1:
                continue

        now = base.iloc[-1]
        ago = base.iloc[-lookback_days - 1]
        n_chg = 100 * (now["nominal"] - ago["nominal"])
        r_chg = 100 * (now["real"] - ago["real"])
        i_chg = 100 * (now["inflation"] - ago["inflation"])

        denom = abs(r_chg) + abs(i_chg)
        if denom > 0:
            driver = "Real" if abs(r_chg) >= abs(i_chg) else "Inflation"
            driver_share = abs(r_chg if driver == "Real" else i_chg) / denom
        else:
            driver, driver_share = "Neutral", 0.0

        rows.append({
            "tenor": t,
            "nominal": now["nominal"], "real": now["real"], "inflation": now["inflation"],
            "nominal_1m_change_bp": n_chg, "real_1m_change_bp": r_chg,
            "inflation_1m_change_bp": i_chg,
            "driver_1m": driver, "driver_share_1m": driver_share,
            "nominal_ago": ago["nominal"], "real_ago": ago["real"],
            "inflation_ago": ago["inflation"],
        })
    return pd.DataFrame(rows)


def rolling_rate_attribution(df: pd.DataFrame, tenor: str = "10Y",
                             window: int = 10) -> pd.DataFrame:
    """Rolling nominal/real/inflation attribution for a single tenor.
    Uses valid observations only — diff(window) counts real trading days."""
    if tenor not in available_us_tenors(df):
        return pd.DataFrame()
    nominal, real, inflation = _get_curves(df, [tenor])
    base = pd.DataFrame({
        "nominal": nominal[tenor], "real": real[tenor], "inflation": inflation[tenor],
    }).dropna()
    if len(base) < window + 1:
        return pd.DataFrame()
    out = pd.DataFrame(index=base.index)
    out["nominal_change_bp"] = 100 * base["nominal"].diff(window)
    out["real_contribution_bp"] = 100 * base["real"].diff(window)
    out["inflation_contribution_bp"] = 100 * base["inflation"].diff(window)
    out["residual_bp"] = out["nominal_change_bp"] - out["real_contribution_bp"] - out["inflation_contribution_bp"]
    return out


def rolling_curve_decomposition(df: pd.DataFrame, pair: tuple = ("2Y", "10Y"),
                                window: int = 10) -> pd.DataFrame:
    """Rolling spread decomposition: nominal / real / inflation legs.
    Uses valid observations only."""
    front, back = pair
    tenors = available_us_tenors(df)
    if front not in tenors or back not in tenors:
        return pd.DataFrame()
    nominal, real, inflation = _get_curves(df, [front, back])
    base = pd.DataFrame({
        "nominal_spread": nominal[back] - nominal[front],
        "real_spread": real[back] - real[front],
        "inflation_spread": inflation[back] - inflation[front],
    }).dropna()
    if len(base) < window + 1:
        return pd.DataFrame()
    out = base.copy()
    out["nominal_spread_change_bp"] = 100 * base["nominal_spread"].diff(window)
    out["real_leg_change_bp"] = 100 * base["real_spread"].diff(window)
    out["inflation_leg_change_bp"] = 100 * base["inflation_spread"].diff(window)
    out["residual_bp"] = out["nominal_spread_change_bp"] - out["real_leg_change_bp"] - out["inflation_leg_change_bp"]
    return out
