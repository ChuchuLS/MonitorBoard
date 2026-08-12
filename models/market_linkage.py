"""PDF-aligned cross-asset linkage gauge.

The live model follows the reference chart pack's Market Linkage page:
SPX, UST 10Y and DXY are fully aligned first, daily moves are transformed on
identical intervals, and a rolling PCA reports the share of total standardized
variance explained by PC1.  A high reading means the three markets are moving
more like one macro trade; a low reading means they are trading more
independently.

This is a co-movement diagnostic.  It is not a regime label, causal
attribution, fair-value model, forecast or trading recommendation.
"""
from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd

MARKET_LINKAGE_CONFIG = {
    "SPX": {
        "label": "SPX",
        "ticker": "SPX INDEX",
        "transform": "log_return_pct",
        "move_unit": "%",
    },
    "USGG10YR": {
        "label": "UST 10Y",
        "ticker": "USGG10YR INDEX",
        "transform": "change_bp",
        "move_unit": "bp",
    },
    "DXY": {
        "label": "DXY",
        "ticker": "DXY CURNCY",
        "transform": "log_return_pct",
        "move_unit": "%",
    },
}
ASSETS = list(MARKET_LINKAGE_CONFIG)
DEFAULT_PCA_WINDOW = 63
DEFAULT_CORR_WINDOW = 20


def pair_key(a: str, b: str) -> str:
    return f"{a}_vs_{b}"


def pair_label(key: str) -> str:
    a, b = key.split("_vs_", 1)
    return f"{MARKET_LINKAGE_CONFIG[a]['label']} vs {MARKET_LINKAGE_CONFIG[b]['label']}"


def all_pair_keys() -> list[str]:
    return [pair_key(a, b) for a, b in combinations(ASSETS, 2)]


def _normalise_asof(asof) -> pd.Timestamp | None:
    return None if asof is None else pd.Timestamp(asof).normalize()


def build_market_linkage_levels(df: pd.DataFrame, asof=None) -> pd.DataFrame:
    """Return the three level series on one exact common calendar."""
    missing = [a for a in ASSETS if a not in df.columns]
    if missing:
        return pd.DataFrame(columns=ASSETS, dtype=float)
    out = df[ASSETS].copy()
    for c in ASSETS:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    cutoff = _normalise_asof(asof)
    if cutoff is not None:
        out = out.loc[out.index <= cutoff]
    return out.dropna(subset=ASSETS).sort_index()


def build_market_linkage_returns(df: pd.DataFrame, asof=None) -> pd.DataFrame:
    """Transform only after common-calendar alignment."""
    levels = build_market_linkage_levels(df, asof=asof)
    if levels.empty:
        return pd.DataFrame(columns=ASSETS, dtype=float)
    out = pd.DataFrame(index=levels.index)
    out["SPX"] = 100.0 * np.log(levels["SPX"]).diff()
    out["USGG10YR"] = 100.0 * levels["USGG10YR"].diff()
    out["DXY"] = 100.0 * np.log(levels["DXY"]).diff()
    return out.dropna(subset=ASSETS)


def assess_market_linkage_readiness(
    df: pd.DataFrame,
    corr_window: int = DEFAULT_CORR_WINDOW,
    pca_window: int = DEFAULT_PCA_WINDOW,
    asof=None,
) -> dict:
    missing = [a for a in ASSETS if a not in df.columns or pd.to_numeric(df[a], errors="coerce").dropna().empty]
    if missing:
        return {
            "status": "Missing data" if len(missing) == len(ASSETS) else "Partial",
            "missing": missing,
            "aligned_observations": 0,
            "common_first_date": None,
            "common_latest_date": None,
            "enough_history": False,
        }
    levels = build_market_linkage_levels(df, asof=asof)
    n = len(levels)
    enough = n >= max(int(corr_window), int(pca_window)) + 2
    return {
        "status": "Ready" if enough else "Partial",
        "missing": [],
        "aligned_observations": n,
        "common_first_date": levels.index.min().date() if n else None,
        "common_latest_date": levels.index.max().date() if n else None,
        "enough_history": enough,
    }


def build_rolling_pairwise_correlations(
    df: pd.DataFrame,
    window: int = DEFAULT_CORR_WINDOW,
    asof=None,
) -> pd.DataFrame:
    returns = build_market_linkage_returns(df, asof=asof)
    out = pd.DataFrame(index=returns.index)
    if len(returns) < int(window):
        return out
    for a, b in combinations(ASSETS, 2):
        out[pair_key(a, b)] = returns[a].rolling(int(window)).corr(returns[b])
    return out.dropna(how="all")


def build_correlation_matrix(df: pd.DataFrame, window: int = DEFAULT_CORR_WINDOW, asof=None) -> pd.DataFrame:
    returns = build_market_linkage_returns(df, asof=asof)
    if len(returns) < int(window):
        return pd.DataFrame()
    labels = {a: MARKET_LINKAGE_CONFIG[a]["label"] for a in ASSETS}
    return returns.tail(int(window)).corr().rename(index=labels, columns=labels)


def _pc1_explained(window_frame: pd.DataFrame) -> float:
    arr = window_frame.to_numpy(dtype=float)
    sd = np.nanstd(arr, axis=0, ddof=0)
    if np.any(~np.isfinite(sd)) or np.any(sd <= 0):
        return np.nan
    z = (arr - np.nanmean(arr, axis=0)) / sd
    corr = np.corrcoef(z, rowvar=False)
    if not np.isfinite(corr).all():
        return np.nan
    eigvals = np.linalg.eigvalsh(corr)
    total = eigvals.sum()
    return float(eigvals[-1] / total) if total > 0 else np.nan


def build_linkage_gauge_history(
    df: pd.DataFrame,
    window: int = DEFAULT_PCA_WINDOW,
    asof=None,
) -> pd.Series:
    """Rolling PC1 share of standardized three-asset daily-move variance."""
    returns = build_market_linkage_returns(df, asof=asof)
    w = int(window)
    if len(returns) < w:
        return pd.Series(dtype=float, name="pc1_explained_variance")
    vals = []
    idx = []
    for end in range(w, len(returns) + 1):
        block = returns.iloc[end - w:end]
        vals.append(_pc1_explained(block))
        idx.append(returns.index[end - 1])
    return pd.Series(vals, index=pd.DatetimeIndex(idx), name="pc1_explained_variance").dropna()


def build_integration_history(df: pd.DataFrame, window: int = DEFAULT_CORR_WINDOW, asof=None) -> pd.DataFrame:
    """Backward-compatible pairwise-correlation concentration diagnostics."""
    rolled = build_rolling_pairwise_correlations(df, window=window, asof=asof)
    if rolled.empty:
        return pd.DataFrame(columns=["mean_abs_corr", "mean_signed_corr", "max_abs_corr"])
    return pd.DataFrame({
        "mean_abs_corr": rolled.abs().mean(axis=1),
        "mean_signed_corr": rolled.mean(axis=1),
        "max_abs_corr": rolled.abs().max(axis=1),
    }, index=rolled.index)


def build_market_linkage_snapshot(
    df: pd.DataFrame,
    corr_window: int = DEFAULT_CORR_WINDOW,
    long_window: int = DEFAULT_PCA_WINDOW,
    asof=None,
) -> dict:
    readiness = assess_market_linkage_readiness(
        df, corr_window=corr_window, pca_window=long_window, asof=asof
    )
    levels = build_market_linkage_levels(df, asof=asof)
    returns = build_market_linkage_returns(df, asof=asof)
    gauge = build_linkage_gauge_history(df, window=long_window, asof=asof)
    corrs = build_rolling_pairwise_correlations(df, window=corr_window, asof=asof)
    matrix = build_correlation_matrix(df, window=corr_window, asof=asof)
    integration = build_integration_history(df, window=corr_window, asof=asof)

    latest_corrs = corrs.iloc[-1].dropna() if not corrs.empty else pd.Series(dtype=float)
    strongest_positive = strongest_negative = None
    if not latest_corrs.empty:
        pos = latest_corrs[latest_corrs >= 0]
        neg = latest_corrs[latest_corrs < 0]
        if not pos.empty:
            k = pos.idxmax(); strongest_positive = {"pair": k, "label": pair_label(k), "correlation": float(pos[k])}
        if not neg.empty:
            k = neg.idxmin(); strongest_negative = {"pair": k, "label": pair_label(k), "correlation": float(neg[k])}

    current_linkage = float(gauge.iloc[-1]) if not gauge.empty else None
    percentile = None
    if not gauge.empty:
        hist = gauge.tail(504)
        percentile = float(100.0 * (hist <= gauge.iloc[-1]).mean())

    return {
        **readiness,
        "model_date": levels.index[-1].date() if not levels.empty else None,
        "levels": levels,
        "returns": returns,
        "correlation_window": int(corr_window),
        "long_window": int(long_window),
        "linkage_history": gauge,
        "pc1_explained_variance": current_linkage,
        "linkage_percentile_2y": percentile,
        "correlation_history": corrs,
        "correlation_matrix": matrix,
        "integration_history": integration,
        "latest_correlations": latest_corrs.to_dict(),
        "strongest_positive": strongest_positive,
        "strongest_negative": strongest_negative,
        "mean_abs_correlation": float(latest_corrs.abs().mean()) if not latest_corrs.empty else None,
    }


def build_market_linkage_current_reading(
    df: pd.DataFrame,
    corr_window: int = DEFAULT_CORR_WINDOW,
    long_window: int = DEFAULT_PCA_WINDOW,
    asof=None,
) -> dict:
    snap = build_market_linkage_snapshot(
        df, corr_window=corr_window, long_window=long_window, asof=asof
    )
    if snap["status"] != "Ready":
        return {
            "status": snap["status"],
            "model_date": snap.get("model_date"),
            "missing": snap.get("missing", []),
            "summary": "Insufficient fully aligned SPX / UST 10Y / DXY history.",
        }
    linkage = snap.get("pc1_explained_variance")
    pct = snap.get("linkage_percentile_2y")
    return {
        **snap,
        "summary": (
            f"PC1 explains {linkage:.1%} of standardized SPX / UST 10Y / DXY "
            f"daily-move variance as of {snap['model_date']} (2Y percentile {pct:.0f}/100)."
        ),
    }
