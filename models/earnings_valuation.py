"""SPX FY1 Earnings & Valuation monitor.

The EPS source is confirmed by the user-provided Bloomberg Excel formula:

    BDH(<ticker>, "BEST_EPS", ..., "BEST_FPERIOD_OVERRIDE=1FY",
        "Per=W", "Dir=V", "Dt")

Therefore the model labels the series as weekly FY1 consensus EPS estimates.
It does not label the data blended-forward-12-month, trailing, or realised EPS.
All production calculations use exact common EPS/price dates; no forward-fill.
"""
from __future__ import annotations

import math
from typing import Iterable

import numpy as np
import pandas as pd

from models.scoring.engine import EQUITY_UNIVERSE

SPX_CODE = "ES1"
DEFAULT_HORIZONS = (1, 4, 13, 26)
DEFAULT_DECOMPOSITION_HORIZON = 4
DEFAULT_BETA_WINDOW = 26
DEFAULT_MIN_BETA_OBS = 20
DEFAULT_FLAT_THRESHOLD_PCT = 0.25

EPS_FIELD_METADATA = {
    "field": "BEST_EPS",
    "forecast_period_override": "1FY",
    "frequency": "weekly",
    "direction": "vertical",
    "date_output": True,
    "meaning": "FY1 consensus EPS estimate level",
    "evidence": "User-provided Bloomberg Excel formula screenshot, 2026-08-04",
    "formula": '@BDH(<ticker>,"BEST_EPS",TODAY()-730,TODAY(),'
               '"BEST_FPERIOD_OVERRIDE=1FY","Per=W","Dir=V","Dt")',
}

INDEX_META = {
    code: {"display_name": name, "region": region}
    for code, name, region in EQUITY_UNIVERSE
}


def _asof_timestamp(asof) -> pd.Timestamp | None:
    return pd.Timestamp(asof) if asof is not None else None


def _safe_float(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else np.nan
    except Exception:
        return np.nan


def build_equity_earnings_frame(data: dict, code: str = SPX_CODE, asof=None) -> pd.DataFrame:
    """Return exact-date-aligned price, FY1 EPS, and implied FY1 P/E."""
    eps = data.get("eps") if isinstance(data, dict) else None
    prices = data.get("prices") if isinstance(data, dict) else None
    if not isinstance(eps, pd.DataFrame) or not isinstance(prices, pd.DataFrame):
        return pd.DataFrame(columns=["price", "eps_fy1", "fy1_pe"])
    if code not in eps.columns or code not in prices.columns:
        return pd.DataFrame(columns=["price", "eps_fy1", "fy1_pe"])

    frame = pd.concat(
        [prices[code].rename("price"), eps[code].rename("eps_fy1")],
        axis=1,
        join="inner",
    ).dropna()
    cutoff = _asof_timestamp(asof)
    if cutoff is not None:
        frame = frame.loc[frame.index <= cutoff]
    frame = frame[(frame["price"] > 0) & (frame["eps_fy1"] > 0)].sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    if frame.empty:
        frame["fy1_pe"] = pd.Series(dtype=float)
        return frame
    frame["fy1_pe"] = frame["price"] / frame["eps_fy1"]
    return frame


def assess_earnings_readiness(
    data: dict,
    code: str = SPX_CODE,
    beta_window: int = DEFAULT_BETA_WINDOW,
    min_beta_obs: int = DEFAULT_MIN_BETA_OBS,
    asof=None,
) -> dict:
    eps = data.get("eps") if isinstance(data, dict) else pd.DataFrame()
    prices = data.get("prices") if isinstance(data, dict) else pd.DataFrame()
    missing = []
    if not isinstance(eps, pd.DataFrame) or code not in eps.columns:
        missing.append("FY1 EPS (BEST_EPS, 1FY)")
    if not isinstance(prices, pd.DataFrame) or code not in prices.columns:
        missing.append("Index price")
    frame = build_equity_earnings_frame(data, code=code, asof=asof)
    obs = len(frame)
    if missing or obs == 0:
        status = "Missing data"
    elif obs < 5:
        status = "Partial"
    else:
        status = "Ready"
    return {
        "code": code,
        "display_name": INDEX_META.get(code, {}).get("display_name", code),
        "status": status,
        "missing": missing,
        "aligned_observations": obs,
        "first_date": frame.index.min().date() if obs else None,
        "model_date": frame.index.max().date() if obs else None,
        "regression_ready": obs >= max(min_beta_obs + 1, beta_window + 1),
        "beta_window": beta_window,
    }


def calculate_horizon_decomposition(
    frame: pd.DataFrame,
    horizons: Iterable[int] = DEFAULT_HORIZONS,
) -> pd.DataFrame:
    """Exact additive log decomposition: Δlog P = Δlog EPS + Δlog(P/E)."""
    rows = []
    for horizon in horizons:
        h = int(horizon)
        row = {"horizon_weeks": h}
        if frame is None or len(frame) <= h:
            row.update({
                "start_date": None, "end_date": None,
                "price_return_pct": np.nan, "eps_growth_pct": np.nan,
                "valuation_change_pct": np.nan, "identity_residual_pct": np.nan,
                "status": "Partial",
            })
        else:
            start = frame.iloc[-h - 1]
            end = frame.iloc[-1]
            price_ret = 100.0 * np.log(end["price"] / start["price"])
            eps_growth = 100.0 * np.log(end["eps_fy1"] / start["eps_fy1"])
            valuation = 100.0 * np.log(end["fy1_pe"] / start["fy1_pe"])
            row.update({
                "start_date": frame.index[-h - 1].date(),
                "end_date": frame.index[-1].date(),
                "price_return_pct": float(price_ret),
                "eps_growth_pct": float(eps_growth),
                "valuation_change_pct": float(valuation),
                "identity_residual_pct": float(price_ret - eps_growth - valuation),
                "status": "Ready",
            })
        rows.append(row)
    return pd.DataFrame(rows)


def build_decomposition_history(frame: pd.DataFrame, horizon: int = 4) -> pd.DataFrame:
    if frame is None or len(frame) <= horizon:
        return pd.DataFrame(columns=[
            "price_return_pct", "eps_growth_pct", "valuation_change_pct",
            "identity_residual_pct",
        ])
    logs = np.log(frame[["price", "eps_fy1", "fy1_pe"]]) * 100.0
    hist = pd.DataFrame(index=frame.index)
    hist["price_return_pct"] = logs["price"].diff(horizon)
    hist["eps_growth_pct"] = logs["eps_fy1"].diff(horizon)
    hist["valuation_change_pct"] = logs["fy1_pe"].diff(horizon)
    hist["identity_residual_pct"] = (
        hist["price_return_pct"]
        - hist["eps_growth_pct"]
        - hist["valuation_change_pct"]
    )
    return hist.dropna(how="all")


def build_weekly_regression_history(
    frame: pd.DataFrame,
    beta_window: int = DEFAULT_BETA_WINDOW,
    min_beta_obs: int = DEFAULT_MIN_BETA_OBS,
    decomposition_horizon: int = DEFAULT_DECOMPOSITION_HORIZON,
) -> pd.DataFrame:
    """Rolling weekly OLS diagnostic; descriptive, not causal attribution."""
    columns = [
        "beta", "r_squared", "price_return_pct", "eps_growth_pct",
        "fitted_earnings_component_pct", "regression_residual_pct",
    ]
    if frame is None or len(frame) < max(min_beta_obs + 1, decomposition_horizon + 1):
        return pd.DataFrame(columns=columns)

    weekly = np.log(frame[["price", "eps_fy1"]]).diff() * 100.0
    x = weekly["eps_fy1"]
    y = weekly["price"]
    rolling_cov = y.rolling(beta_window, min_periods=min_beta_obs).cov(x)
    rolling_var = x.rolling(beta_window, min_periods=min_beta_obs).var(ddof=1)
    beta = rolling_cov / rolling_var.replace(0, np.nan)
    corr = y.rolling(beta_window, min_periods=min_beta_obs).corr(x)

    horizon_changes = build_decomposition_history(frame, horizon=decomposition_horizon)
    out = pd.DataFrame(index=frame.index)
    out["beta"] = beta
    out["r_squared"] = corr.pow(2)
    out["price_return_pct"] = horizon_changes["price_return_pct"]
    out["eps_growth_pct"] = horizon_changes["eps_growth_pct"]
    out["fitted_earnings_component_pct"] = out["beta"] * out["eps_growth_pct"]
    out["regression_residual_pct"] = (
        out["price_return_pct"] - out["fitted_earnings_component_pct"]
    )
    return out.replace([np.inf, -np.inf], np.nan).dropna(how="all")


def _percentile_rank(series: pd.Series, value: float) -> float:
    s = pd.to_numeric(series, errors="coerce").dropna()
    if not len(s) or pd.isna(value):
        return np.nan
    return float((s <= value).mean() * 100.0)


def build_earnings_valuation_snapshot(
    data: dict,
    code: str = SPX_CODE,
    horizons: Iterable[int] = DEFAULT_HORIZONS,
    decomposition_horizon: int = DEFAULT_DECOMPOSITION_HORIZON,
    beta_window: int = DEFAULT_BETA_WINDOW,
    min_beta_obs: int = DEFAULT_MIN_BETA_OBS,
    flat_threshold_pct: float = DEFAULT_FLAT_THRESHOLD_PCT,
    asof=None,
) -> dict:
    readiness = assess_earnings_readiness(
        data, code=code, beta_window=beta_window,
        min_beta_obs=min_beta_obs, asof=asof,
    )
    frame = build_equity_earnings_frame(data, code=code, asof=asof)
    result = dict(readiness)
    result.update({
        "field_metadata": dict(EPS_FIELD_METADATA),
        "frame": frame,
        "decomposition": pd.DataFrame(),
        "decomposition_history": pd.DataFrame(),
        "regression_history": pd.DataFrame(),
    })
    if frame.empty:
        return result

    latest = frame.iloc[-1]
    decomp = calculate_horizon_decomposition(frame, horizons=horizons)
    exact_hist = build_decomposition_history(frame, horizon=decomposition_horizon)
    reg_hist = build_weekly_regression_history(
        frame, beta_window=beta_window, min_beta_obs=min_beta_obs,
        decomposition_horizon=decomposition_horizon,
    )
    result["decomposition"] = decomp
    result["decomposition_history"] = exact_hist
    result["regression_history"] = reg_hist
    result.update({
        "price": float(latest["price"]),
        "eps_fy1": float(latest["eps_fy1"]),
        "fy1_pe": float(latest["fy1_pe"]),
        "pe_percentile_available_history": _percentile_rank(frame["fy1_pe"], latest["fy1_pe"]),
        "pe_percentile_observations": int(frame["fy1_pe"].notna().sum()),
        "decomposition_horizon": int(decomposition_horizon),
        "beta_window": int(beta_window),
    })

    selected = decomp.loc[decomp["horizon_weeks"] == int(decomposition_horizon)]
    if len(selected):
        row = selected.iloc[0].to_dict()
        result.update({f"current_{key}": value for key, value in row.items()})
        eps_move = _safe_float(row.get("eps_growth_pct"))
        val_move = _safe_float(row.get("valuation_change_pct"))
        if pd.isna(eps_move) or pd.isna(val_move):
            driver = "Inconclusive"
        elif abs(eps_move) < flat_threshold_pct and abs(val_move) < flat_threshold_pct:
            driver = "Inconclusive"
        elif abs(eps_move) > abs(val_move):
            driver = "FY1 earnings revisions"
        else:
            driver = "Valuation multiple"
        result["current_driver"] = driver
        if pd.isna(eps_move) or abs(eps_move) < flat_threshold_pct:
            result["eps_revision_direction"] = "Flat / inconclusive"
        else:
            result["eps_revision_direction"] = "Rising" if eps_move > 0 else "Falling"
        if pd.isna(val_move) or abs(val_move) < flat_threshold_pct:
            result["valuation_direction"] = "Flat / inconclusive"
        else:
            result["valuation_direction"] = "Expanding" if val_move > 0 else "Compressing"

    valid_reg = reg_hist.dropna(subset=["beta", "r_squared"])
    if len(valid_reg):
        last_reg = valid_reg.iloc[-1]
        result.update({
            "regression_date": valid_reg.index[-1].date(),
            "regression_beta": float(last_reg["beta"]),
            "regression_r_squared": float(last_reg["r_squared"]),
            "regression_fitted_earnings_pct": _safe_float(last_reg["fitted_earnings_component_pct"]),
            "regression_residual_pct": _safe_float(last_reg["regression_residual_pct"]),
            "regression_status": "Ready",
        })
    else:
        result.update({
            "regression_date": None,
            "regression_beta": np.nan,
            "regression_r_squared": np.nan,
            "regression_fitted_earnings_pct": np.nan,
            "regression_residual_pct": np.nan,
            "regression_status": "Partial",
        })
    return result


def build_global_earnings_overview(
    data: dict,
    horizon: int = 13,
    asof=None,
) -> pd.DataFrame:
    rows = []
    for code, meta in INDEX_META.items():
        frame = build_equity_earnings_frame(data, code=code, asof=asof)
        readiness = assess_earnings_readiness(data, code=code, asof=asof)
        row = {
            "code": code,
            "index": meta["display_name"],
            "region": meta["region"],
            "status": readiness["status"],
            "aligned_observations": readiness["aligned_observations"],
            "model_date": readiness["model_date"],
            "price": np.nan,
            "eps_fy1": np.nan,
            "fy1_pe": np.nan,
            f"price_return_{horizon}w_pct": np.nan,
            f"eps_growth_{horizon}w_pct": np.nan,
            f"valuation_change_{horizon}w_pct": np.nan,
        }
        if len(frame):
            row.update({
                "price": float(frame["price"].iloc[-1]),
                "eps_fy1": float(frame["eps_fy1"].iloc[-1]),
                "fy1_pe": float(frame["fy1_pe"].iloc[-1]),
            })
        dec = calculate_horizon_decomposition(frame, horizons=[horizon])
        if len(dec) and dec.iloc[0]["status"] == "Ready":
            d = dec.iloc[0]
            row.update({
                f"price_return_{horizon}w_pct": float(d["price_return_pct"]),
                f"eps_growth_{horizon}w_pct": float(d["eps_growth_pct"]),
                f"valuation_change_{horizon}w_pct": float(d["valuation_change_pct"]),
            })
        rows.append(row)
    return pd.DataFrame(rows)


def build_earnings_current_reading(data: dict, code: str = SPX_CODE, asof=None) -> dict:
    snap = build_earnings_valuation_snapshot(data, code=code, asof=asof)
    return {
        key: value for key, value in snap.items()
        if key not in {"frame", "decomposition", "decomposition_history", "regression_history"}
    }
