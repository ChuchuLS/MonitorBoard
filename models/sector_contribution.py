"""
models/sector_contribution.py — Phase 8.2
==========================================
Transparent SPX Sector Contribution Estimate. Pure model — no Streamlit.

This is an approximation, not official index attribution.

Method:
- align the 11 canonical S&P 500 sector indices and SPX on one calendar;
- use simple arithmetic returns over the same start/end timestamps;
- select the latest periodic sector-weight row available on or before the
  return-window start date;
- estimate each sector contribution as start-period weight × sector return;
- disclose the residual: actual SPX return − sum(estimated contributions).

Weights are not normalised, forward-filled, or replaced with zero. ETF proxies
are excluded. The residual must remain visible because periodic weights and
simple weighted returns are not divisor-consistent official attribution.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from config.tickers import SPX_SECTOR_CONFIG
from models.sector_rotation import (
    SPX_BENCHMARK_TICKER,
    WEIGHT_SUM_TOLERANCE,
    build_sector_relative_frame,
)

DEFAULT_CONTRIBUTION_HORIZONS = (1, 5, 20, 63)
MAX_WEIGHT_AGE_DAYS = 45  # project diagnostic rule for periodic monthly weights


@dataclass(frozen=True)
class WeightSelection:
    row: pd.Series | None
    date: pd.Timestamp | None
    age_days: int | None
    weight_sum_pct: float
    valid_count: int
    missing_columns: tuple[str, ...]


def _empty_result(horizon: int, status: str, missing: list[str] | None = None) -> dict:
    return {
        "status": status,
        "horizon": int(horizon),
        "missing": list(missing or []),
        "start_date": None,
        "end_date": None,
        "weight_date": None,
        "weight_age_days": None,
        "weight_sum_pct": np.nan,
        "valid_weight_count": 0,
        "actual_spx_return_pct": np.nan,
        "estimated_spx_return_pct": np.nan,
        "residual_pp": np.nan,
        "positive_contribution_pp": np.nan,
        "negative_contribution_pp": np.nan,
        "per_sector": [],
        "aligned_observations": 0,
        "method": "start-period periodic weight × sector simple return",
    }


def select_start_weight(
    weights_df: pd.DataFrame | None,
    start_date,
) -> WeightSelection:
    """Select the latest complete periodic weight row at or before start_date.

    The row is returned exactly as supplied. No normalisation or filling occurs.
    """
    required_cols = tuple(cfg["weight_column"] for cfg in SPX_SECTOR_CONFIG.values())
    if weights_df is None or weights_df.empty or start_date is None:
        return WeightSelection(None, None, None, np.nan, 0, required_cols)

    frame = weights_df.copy()
    frame.index = pd.to_datetime(frame.index, errors="coerce")
    frame = frame.loc[frame.index.notna()].sort_index()
    eligible = frame.loc[:pd.Timestamp(start_date)]
    if eligible.empty:
        return WeightSelection(None, None, None, np.nan, 0, required_cols)

    weight_date = pd.Timestamp(eligible.index[-1])
    raw_row = eligible.iloc[-1]
    missing = tuple(col for col in required_cols if col not in eligible.columns)
    numeric = pd.Series(
        {col: pd.to_numeric(raw_row.get(col), errors="coerce") for col in required_cols},
        dtype=float,
    )
    missing = tuple(sorted(set(missing) | {col for col in required_cols if pd.isna(numeric[col])}))
    valid = numeric.dropna()
    weight_sum = float(valid.sum()) if len(valid) else np.nan
    age_days = int((pd.Timestamp(start_date).normalize() - weight_date.normalize()).days)
    return WeightSelection(
        row=numeric,
        date=weight_date,
        age_days=age_days,
        weight_sum_pct=weight_sum,
        valid_count=int(valid.count()),
        missing_columns=missing,
    )


def build_sector_contribution_estimate(
    df: pd.DataFrame,
    weights_df: pd.DataFrame | None,
    horizon: int = 20,
    asof=None,
    weight_sum_tolerance: float = WEIGHT_SUM_TOLERANCE,
    max_weight_age_days: int = MAX_WEIGHT_AGE_DAYS,
) -> dict:
    """Build one horizon estimate with explicit residual reconciliation.

    Returns are simple arithmetic percentage returns. Contribution units are
    percentage points of estimated SPX return.
    """
    horizon = int(horizon)
    if horizon <= 0:
        raise ValueError("horizon must be a positive observation count")

    aligned = build_sector_relative_frame(df, asof=asof)
    required_sector_keys = list(SPX_SECTOR_CONFIG)
    missing_price_keys = [key for key in required_sector_keys if key not in aligned.columns]
    if aligned.empty or "spx" not in aligned.columns:
        missing = [SPX_SECTOR_CONFIG[k]["ticker"] for k in missing_price_keys]
        if "spx" not in aligned.columns:
            missing.append(SPX_BENCHMARK_TICKER)
        return _empty_result(horizon, "Missing data", missing)
    if len(aligned) <= horizon:
        out = _empty_result(horizon, "Partial", ["Insufficient common price history"])
        out["aligned_observations"] = int(len(aligned))
        return out

    start_ts = pd.Timestamp(aligned.index[-horizon - 1])
    end_ts = pd.Timestamp(aligned.index[-1])
    start_prices = pd.to_numeric(aligned.iloc[-horizon - 1], errors="coerce")
    end_prices = pd.to_numeric(aligned.iloc[-1], errors="coerce")
    simple_returns = 100.0 * (end_prices / start_prices - 1.0)

    weight_sel = select_start_weight(weights_df, start_ts)
    missing = [SPX_SECTOR_CONFIG[k]["ticker"] for k in missing_price_keys]
    missing.extend(weight_sel.missing_columns)

    all_prices_ready = not missing_price_keys and all(
        pd.notna(simple_returns.get(key)) for key in required_sector_keys + ["spx"]
    )
    weights_ready = (
        weight_sel.row is not None
        and weight_sel.valid_count == len(required_sector_keys)
        and not weight_sel.missing_columns
        and pd.notna(weight_sel.weight_sum_pct)
    )
    weight_sum_ok = bool(
        weights_ready
        and abs(weight_sel.weight_sum_pct - 100.0) <= float(weight_sum_tolerance)
    )
    weight_age_ok = bool(
        weight_sel.age_days is not None
        and weight_sel.age_days >= 0
        and weight_sel.age_days <= int(max_weight_age_days)
    )

    per_sector: list[dict] = []
    contributions: list[float] = []
    for key, cfg in SPX_SECTOR_CONFIG.items():
        sector_ret = float(simple_returns[key]) if key in simple_returns and pd.notna(simple_returns[key]) else np.nan
        weight = (
            float(weight_sel.row[cfg["weight_column"]])
            if weight_sel.row is not None
            and cfg["weight_column"] in weight_sel.row.index
            and pd.notna(weight_sel.row[cfg["weight_column"]])
            else np.nan
        )
        contribution = (
            weight / 100.0 * sector_ret
            if pd.notna(weight) and pd.notna(sector_ret)
            else np.nan
        )
        if pd.notna(contribution):
            contributions.append(float(contribution))
        per_sector.append({
            "sector": key,
            "display_name": cfg["display_name"],
            "ticker": cfg["ticker"],
            "weight_column": cfg["weight_column"],
            "start_weight_pct": weight,
            "sector_return_pct": sector_ret,
            "estimated_contribution_pp": contribution,
            "weight_date": weight_sel.date.date() if weight_sel.date is not None else None,
            "start_date": start_ts.date(),
            "end_date": end_ts.date(),
            "status": "Ready" if pd.notna(weight) and pd.notna(sector_ret) else "Missing data",
        })

    complete_estimate = all_prices_ready and weights_ready and len(contributions) == len(required_sector_keys)
    estimated = float(np.sum(contributions)) if complete_estimate else np.nan
    actual = float(simple_returns["spx"]) if pd.notna(simple_returns.get("spx")) else np.nan
    residual = float(actual - estimated) if pd.notna(actual) and pd.notna(estimated) else np.nan
    positive = float(sum(v for v in contributions if v > 0)) if complete_estimate else np.nan
    negative = float(sum(v for v in contributions if v < 0)) if complete_estimate else np.nan

    if not all_prices_ready or not weights_ready:
        status = "Partial" if len(aligned) else "Missing data"
    elif not weight_sum_ok or not weight_age_ok:
        status = "Partial"
    else:
        status = "Ready"

    warnings: list[str] = []
    if not weight_sum_ok and pd.notna(weight_sel.weight_sum_pct):
        warnings.append(
            f"Start-weight sum {weight_sel.weight_sum_pct:.2f}% is outside "
            f"the ±{weight_sum_tolerance:.2f}pp audit tolerance."
        )
    if weight_sel.date is None:
        warnings.append("No periodic sector-weight row exists on or before the return start date.")
    elif not weight_age_ok:
        warnings.append(
            f"Start weight is {weight_sel.age_days} calendar days old; project "
            f"diagnostic limit is {max_weight_age_days} days."
        )
    if missing:
        warnings.append("Missing inputs: " + ", ".join(sorted(set(missing))))

    ranked = sorted(
        [row for row in per_sector if pd.notna(row["estimated_contribution_pp"])],
        key=lambda row: row["estimated_contribution_pp"],
        reverse=True,
    )
    rank_lookup = {row["sector"]: idx + 1 for idx, row in enumerate(ranked)}
    for row in per_sector:
        row["contribution_rank"] = rank_lookup.get(row["sector"])

    return {
        "status": status,
        "horizon": horizon,
        "missing": sorted(set(missing)),
        "warnings": warnings,
        "start_date": start_ts.date(),
        "end_date": end_ts.date(),
        "weight_date": weight_sel.date.date() if weight_sel.date is not None else None,
        "weight_age_days": weight_sel.age_days,
        "weight_sum_pct": weight_sel.weight_sum_pct,
        "weight_sum_ok": weight_sum_ok,
        "weight_age_ok": weight_age_ok,
        "valid_weight_count": weight_sel.valid_count,
        "actual_spx_return_pct": actual,
        "estimated_spx_return_pct": estimated,
        "residual_pp": residual,
        "positive_contribution_pp": positive,
        "negative_contribution_pp": negative,
        "per_sector": per_sector,
        "aligned_observations": int(len(aligned)),
        "method": "start-period periodic weight × sector simple return",
        "return_type": "simple arithmetic percentage return",
        "weight_normalised": False,
        "official_attribution": False,
    }


def build_sector_contribution_summary(
    df: pd.DataFrame,
    weights_df: pd.DataFrame | None,
    horizons: Iterable[int] = DEFAULT_CONTRIBUTION_HORIZONS,
    asof=None,
) -> pd.DataFrame:
    """One reconciliation row per horizon."""
    rows = []
    for horizon in horizons:
        result = build_sector_contribution_estimate(
            df, weights_df, horizon=int(horizon), asof=asof
        )
        rows.append({
            "horizon": int(horizon),
            "start_date": result["start_date"],
            "end_date": result["end_date"],
            "weight_date": result["weight_date"],
            "weight_age_days": result["weight_age_days"],
            "weight_sum_pct": result["weight_sum_pct"],
            "actual_spx_return_pct": result["actual_spx_return_pct"],
            "estimated_spx_return_pct": result["estimated_spx_return_pct"],
            "residual_pp": result["residual_pp"],
            "status": result["status"],
        })
    return pd.DataFrame(rows)


def build_sector_contribution_history(
    df: pd.DataFrame,
    weights_df: pd.DataFrame | None,
    horizon: int = 20,
    asof=None,
) -> pd.DataFrame:
    """Rolling actual/estimated SPX return and residual history.

    Each end date uses the latest periodic weight row available on or before
    that window's start timestamp. No weight is normalised or forward-filled.
    """
    horizon = int(horizon)
    aligned = build_sector_relative_frame(df, asof=asof)
    if aligned.empty or len(aligned) <= horizon or weights_df is None or weights_df.empty:
        return pd.DataFrame()

    rows = []
    for end_pos in range(horizon, len(aligned)):
        start_pos = end_pos - horizon
        start_ts = pd.Timestamp(aligned.index[start_pos])
        end_ts = pd.Timestamp(aligned.index[end_pos])
        weight_sel = select_start_weight(weights_df, start_ts)
        if (
            weight_sel.row is None
            or weight_sel.valid_count != len(SPX_SECTOR_CONFIG)
            or weight_sel.missing_columns
        ):
            continue
        start_prices = pd.to_numeric(aligned.iloc[start_pos], errors="coerce")
        end_prices = pd.to_numeric(aligned.iloc[end_pos], errors="coerce")
        rets = 100.0 * (end_prices / start_prices - 1.0)
        if any(pd.isna(rets.get(key)) for key in list(SPX_SECTOR_CONFIG) + ["spx"]):
            continue
        contributions = []
        for key, cfg in SPX_SECTOR_CONFIG.items():
            weight = float(weight_sel.row[cfg["weight_column"]])
            contributions.append(weight / 100.0 * float(rets[key]))
        estimated = float(sum(contributions))
        actual = float(rets["spx"])
        rows.append({
            "end_date": end_ts,
            "start_date": start_ts,
            "weight_date": weight_sel.date,
            "weight_age_days": weight_sel.age_days,
            "weight_sum_pct": weight_sel.weight_sum_pct,
            "actual_spx_return_pct": actual,
            "estimated_spx_return_pct": estimated,
            "residual_pp": actual - estimated,
        })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).set_index("end_date").sort_index()


def build_sector_contribution_current_reading(
    df: pd.DataFrame,
    weights_df: pd.DataFrame | None,
    horizon: int = 20,
    asof=None,
) -> dict:
    """Concise source-supported reading for the selected estimate window."""
    result = build_sector_contribution_estimate(
        df, weights_df, horizon=horizon, asof=asof
    )
    ready_rows = [
        row for row in result.get("per_sector", [])
        if pd.notna(row.get("estimated_contribution_pp"))
    ]
    positive = sorted(
        [row for row in ready_rows if row["estimated_contribution_pp"] > 0],
        key=lambda row: row["estimated_contribution_pp"],
        reverse=True,
    )
    negative = sorted(
        [row for row in ready_rows if row["estimated_contribution_pp"] < 0],
        key=lambda row: row["estimated_contribution_pp"],
    )
    result["top_positive"] = positive[:3]
    result["top_negative"] = negative[:3]
    return result
