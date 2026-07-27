"""
models/curve_regimes.py
=======================
Classify curve moves into directional regimes (Bull/Bear × Steepener/Flattener,
Twist, Neutral) across nominal, real, and inflation spread pairs.

Pure functions — no Streamlit.
"""
from __future__ import annotations
import pandas as pd
import numpy as np
from models.rate_decomposition import available_us_tenors, _get_curves, US_NOMINAL, US_BREAKEVEN
from config.tickers import TENOR_PAIRS

REGIME_LABELS = [
    "Bull Steepener", "Bull Flattener",
    "Bear Steepener", "Bear Flattener",
    "Twist Steepener", "Twist Flattener",
    "Neutral",
]

REGIME_COLORS = {
    "Bull Steepener":  "#22c55e",
    "Bull Flattener":  "#06b6d4",
    "Bear Steepener":  "#ef4444",
    "Bear Flattener":  "#f97316",
    "Twist Steepener": "#eab308",
    "Twist Flattener": "#a855f7",
    "Neutral":         "#525252",
}


def classify_curve_regime(front_change_bp: float, back_change_bp: float,
                          spread_change_bp: float, neutral_bp: float = 1.5) -> str | float:
    if pd.isna(front_change_bp) or pd.isna(back_change_bp) or pd.isna(spread_change_bp):
        return np.nan  # missing data is NOT Neutral
    if abs(spread_change_bp) < neutral_bp:
        return "Neutral"

    front_down = front_change_bp < 0
    back_down = back_change_bp < 0
    widens = spread_change_bp > 0  # back - front increases

    if front_down and back_down:
        return "Bull Steepener" if widens else "Bull Flattener"
    elif not front_down and not back_down:
        return "Bear Steepener" if widens else "Bear Flattener"
    else:
        return "Twist Steepener" if widens else "Twist Flattener"


def classify_pair_history(df: pd.DataFrame, curve_type: str = "nominal",
                          pair: tuple = ("2Y", "10Y"), window: int = 10) -> pd.DataFrame:
    """Classify each day's regime for a given curve type and tenor pair.
    Uses valid observations only — NaN rows are excluded before diff."""
    tenors = available_us_tenors(df)
    front, back = pair
    if front not in tenors or back not in tenors:
        return pd.DataFrame()

    nominal, real, inflation = _get_curves(df, [front, back])
    curves = {"nominal": nominal, "real": real, "inflation": inflation}
    c = curves.get(curve_type)
    if c is None or c.empty:
        return pd.DataFrame()

    # Use only rows where both tenors have data
    c_pair = c[[front, back]].dropna()
    if len(c_pair) < window + 1:
        return pd.DataFrame()

    spread = c_pair[back] - c_pair[front]
    front_chg = 100 * c_pair[front].diff(window)
    back_chg = 100 * c_pair[back].diff(window)
    spread_chg = 100 * spread.diff(window)

    out = pd.DataFrame({
        "spread": spread, "front_change_bp": front_chg,
        "back_change_bp": back_chg, "spread_change_bp": spread_chg,
    }, index=c_pair.index)
    out["regime"] = out.apply(
        lambda r: classify_curve_regime(r["front_change_bp"], r["back_change_bp"],
                                        r["spread_change_bp"]),
        axis=1)
    return out


def build_regime_matrix(df: pd.DataFrame, window: int = 10) -> pd.DataFrame:
    """Build a matrix: rows = Nominal/Real/Inflation, cols = tenor pairs, cells = latest regime."""
    pairs = list(TENOR_PAIRS.keys())
    rows = {}
    for ctype in ["Nominal", "Real", "Inflation"]:
        row = {}
        for pair_name in pairs:
            front, back = TENOR_PAIRS[pair_name]
            hist = classify_pair_history(df, curve_type=ctype.lower(),
                                         pair=(front, back), window=window)
            if hist.empty or hist["regime"].dropna().empty:
                row[pair_name] = "—"
            else:
                row[pair_name] = hist["regime"].dropna().iloc[-1]
        rows[ctype] = row
    return pd.DataFrame(rows).T


def dominant_regime(row: pd.Series) -> dict:
    """Given a row of the regime matrix, find the dominant regime."""
    counts = row.value_counts()
    counts = counts[counts.index != "—"]
    if counts.empty:
        return {"regime": "—", "count": 0, "total": len(row), "divergent": len(row)}
    top = counts.index[0]
    return {
        "regime": top, "count": int(counts.iloc[0]),
        "total": len(row),
        "divergent": int((row != top).sum() - (row == "—").sum()),
    }


def days_in_current_regime(series: pd.Series) -> int:
    s = series.dropna()
    if s.empty:
        return 0
    current = s.iloc[-1]
    count = 0
    for v in s.iloc[::-1]:
        if v == current:
            count += 1
        else:
            break
    return count
