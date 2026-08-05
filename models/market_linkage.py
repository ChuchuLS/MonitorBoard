"""Pure descriptive cross-asset linkage analytics.

The production universe is SPX, the US 10Y Treasury yield, DXY, Bloomberg
Commodity Index and US high-yield OAS.  All five level series are aligned on
one common observation calendar *before* daily transformations are calculated.

This module measures co-movement.  Correlation is not causal attribution, fair
value, forecasting or a trading recommendation.
"""
from __future__ import annotations

from itertools import combinations
from typing import Iterable

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
    "BCOM": {
        "label": "BCOM",
        "ticker": "BCOM INDEX",
        "transform": "log_return_pct",
        "move_unit": "%",
    },
    "LF98OAS": {
        "label": "US HY OAS",
        "ticker": "LF98OAS INDEX",
        "transform": "change_bp",
        "move_unit": "bp",
    },
}

ASSETS = list(MARKET_LINKAGE_CONFIG)
DEFAULT_HORIZONS = (1, 5, 20, 63)


def pair_key(a: str, b: str) -> str:
    return f"{a}_vs_{b}"


def pair_label(key: str) -> str:
    a, b = key.split("_vs_", 1)
    return f"{MARKET_LINKAGE_CONFIG[a]['label']} vs {MARKET_LINKAGE_CONFIG[b]['label']}"


def all_pair_keys() -> list[str]:
    return [pair_key(a, b) for a, b in combinations(ASSETS, 2)]


def _normalise_asof(asof) -> pd.Timestamp | None:
    if asof is None:
        return None
    ts = pd.Timestamp(asof)
    return ts.normalize()


def assess_market_linkage_readiness(
    df: pd.DataFrame,
    corr_window: int = 20,
    asof=None,
) -> dict:
    """Return field availability and common-calendar readiness."""
    missing = [a for a in ASSETS if a not in df.columns]
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
    enough = n >= corr_window + 1
    return {
        "status": "Ready" if enough else "Partial",
        "missing": [],
        "aligned_observations": n,
        "common_first_date": levels.index.min().date() if n else None,
        "common_latest_date": levels.index.max().date() if n else None,
        "enough_history": enough,
    }


def build_market_linkage_levels(df: pd.DataFrame, asof=None) -> pd.DataFrame:
    """Fully align the five raw level series on their common calendar."""
    if any(a not in df.columns for a in ASSETS):
        return pd.DataFrame(columns=ASSETS, dtype=float)
    levels = df[ASSETS].copy()
    for c in ASSETS:
        levels[c] = pd.to_numeric(levels[c], errors="coerce")
    cutoff = _normalise_asof(asof)
    if cutoff is not None:
        levels = levels.loc[levels.index <= cutoff]
    return levels.dropna(subset=ASSETS).sort_index()


def build_market_linkage_returns(df: pd.DataFrame, asof=None) -> pd.DataFrame:
    """Transform levels after full alignment, preserving identical intervals."""
    levels = build_market_linkage_levels(df, asof=asof)
    if levels.empty:
        return pd.DataFrame(columns=ASSETS, dtype=float)
    out = pd.DataFrame(index=levels.index)
    for asset, meta in MARKET_LINKAGE_CONFIG.items():
        if meta["transform"] == "log_return_pct":
            out[asset] = 100.0 * np.log(levels[asset]).diff()
        elif meta["transform"] == "change_bp":
            # UST yield and LF98OAS are stored in percentage points.
            out[asset] = 100.0 * levels[asset].diff()
        else:  # pragma: no cover - registry contract protects this branch
            raise ValueError(f"Unsupported transform for {asset}: {meta['transform']}")
    return out.dropna(subset=ASSETS)


def build_rolling_pairwise_correlations(
    df: pd.DataFrame,
    window: int = 20,
    asof=None,
) -> pd.DataFrame:
    """Rolling Pearson correlations for all ten unique asset pairs."""
    returns = build_market_linkage_returns(df, asof=asof)
    out = pd.DataFrame(index=returns.index)
    if len(returns) < window:
        return out
    for a, b in combinations(ASSETS, 2):
        out[pair_key(a, b)] = returns[a].rolling(window).corr(returns[b])
    return out.dropna(how="all")


def build_correlation_matrix(
    df: pd.DataFrame,
    window: int = 20,
    asof=None,
) -> pd.DataFrame:
    """Latest common-window correlation matrix with display labels."""
    returns = build_market_linkage_returns(df, asof=asof)
    if len(returns) < window:
        return pd.DataFrame()
    matrix = returns.tail(window).corr()
    labels = {a: MARKET_LINKAGE_CONFIG[a]["label"] for a in ASSETS}
    return matrix.rename(index=labels, columns=labels)


def build_integration_history(
    df: pd.DataFrame,
    window: int = 20,
    asof=None,
) -> pd.DataFrame:
    """Cross-asset correlation concentration over time.

    ``mean_abs_corr`` is the mean absolute value of the ten pairwise rolling
    correlations. ``max_abs_corr`` is the largest absolute pair correlation.
    These are descriptive co-movement measures, not systemic-risk scores.
    """
    rolled = build_rolling_pairwise_correlations(df, window=window, asof=asof)
    if rolled.empty:
        return pd.DataFrame(columns=["mean_abs_corr", "mean_signed_corr", "max_abs_corr"])
    return pd.DataFrame(
        {
            "mean_abs_corr": rolled.abs().mean(axis=1),
            "mean_signed_corr": rolled.mean(axis=1),
            "max_abs_corr": rolled.abs().max(axis=1),
        },
        index=rolled.index,
    )


def _horizon_moves(levels: pd.DataFrame, horizons: Iterable[int]) -> pd.DataFrame:
    rows = []
    if levels.empty:
        return pd.DataFrame()
    for asset, meta in MARKET_LINKAGE_CONFIG.items():
        row = {
            "asset": asset,
            "label": meta["label"],
            "ticker": meta["ticker"],
            "latest_level": float(levels[asset].iloc[-1]),
            "unit": meta["move_unit"],
            "latest_date": levels.index[-1].date(),
        }
        for h in horizons:
            value = np.nan
            if len(levels) > h:
                if meta["transform"] == "log_return_pct":
                    value = 100.0 * np.log(levels[asset].iloc[-1] / levels[asset].iloc[-1 - h])
                else:
                    value = 100.0 * (levels[asset].iloc[-1] - levels[asset].iloc[-1 - h])
            row[f"move_{h}"] = float(value) if pd.notna(value) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def build_market_linkage_snapshot(
    df: pd.DataFrame,
    corr_window: int = 20,
    long_window: int = 63,
    horizons: Iterable[int] = DEFAULT_HORIZONS,
    asof=None,
) -> dict:
    readiness = assess_market_linkage_readiness(df, corr_window=max(corr_window, long_window), asof=asof)
    levels = build_market_linkage_levels(df, asof=asof)
    returns = build_market_linkage_returns(df, asof=asof)
    moves = _horizon_moves(levels, horizons)
    corr_hist = build_rolling_pairwise_correlations(df, window=corr_window, asof=asof)
    integration = build_integration_history(df, window=corr_window, asof=asof)
    matrix = build_correlation_matrix(df, window=corr_window, asof=asof)

    latest_corrs = corr_hist.iloc[-1].dropna() if not corr_hist.empty else pd.Series(dtype=float)
    strongest_positive = None
    strongest_negative = None
    if not latest_corrs.empty:
        pos = latest_corrs[latest_corrs >= 0]
        neg = latest_corrs[latest_corrs < 0]
        if not pos.empty:
            k = pos.idxmax()
            strongest_positive = {"pair": k, "label": pair_label(k), "correlation": float(pos[k])}
        if not neg.empty:
            k = neg.idxmin()
            strongest_negative = {"pair": k, "label": pair_label(k), "correlation": float(neg[k])}

    previous_corrs = None
    corr_change = None
    if len(corr_hist) > corr_window:
        previous_corrs = corr_hist.iloc[-1 - corr_window]
        corr_change = latest_corrs.subtract(previous_corrs, fill_value=np.nan)

    return {
        **readiness,
        "model_date": levels.index[-1].date() if not levels.empty else None,
        "levels": levels,
        "returns": returns,
        "moves": moves,
        "correlation_window": corr_window,
        "long_window": long_window,
        "correlation_history": corr_hist,
        "correlation_matrix": matrix,
        "integration_history": integration,
        "latest_correlations": latest_corrs.to_dict(),
        "correlation_changes": corr_change.to_dict() if corr_change is not None else {},
        "strongest_positive": strongest_positive,
        "strongest_negative": strongest_negative,
        "mean_abs_correlation": (
            float(integration["mean_abs_corr"].iloc[-1]) if not integration.empty else None
        ),
        "max_abs_correlation": (
            float(integration["max_abs_corr"].iloc[-1]) if not integration.empty else None
        ),
    }


def build_market_linkage_current_reading(
    df: pd.DataFrame,
    corr_window: int = 20,
    long_window: int = 63,
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
            "summary": "Insufficient fully aligned history for the selected correlation window.",
        }
    pos = snap.get("strongest_positive")
    neg = snap.get("strongest_negative")
    pieces = [
        f"Mean absolute {corr_window}-observation pair correlation is "
        f"{snap['mean_abs_correlation']:.2f}."
    ]
    if pos:
        pieces.append(f"Strongest positive pair: {pos['label']} ({pos['correlation']:+.2f}).")
    if neg:
        pieces.append(f"Strongest negative pair: {neg['label']} ({neg['correlation']:+.2f}).")
    return {
        "status": "Ready",
        "model_date": snap["model_date"],
        "mean_abs_correlation": snap["mean_abs_correlation"],
        "strongest_positive": pos,
        "strongest_negative": neg,
        "summary": " ".join(pieces),
        "methodology_note": (
            "Correlations describe common movement over one fully aligned calendar. "
            "They do not establish causality, fair value or a forecast."
        ),
    }
