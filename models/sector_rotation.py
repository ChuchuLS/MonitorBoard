"""
models/sector_rotation.py — Phase 8.1
=====================================
SPX Sector Rotation & Breadth Monitor. Pure model — no Streamlit imports.

DESCRIPTIVE ONLY. Not attribution, not causal, not a forecast.
Uses the 11 canonical S&P 500 sector indices (S5xxx). ETF proxies are
excluded from production. Sector weights are context only; weight changes
must not be described as investor flows.

Two model calendars are maintained:
- sector_only_date: latest date common to the available sector indices
- relative_model_date: latest date common to the available sectors and SPX

A production status is Ready only when all 11 sectors and SPX are available.
If one or more inputs are missing, the model remains transparent and returns
Partial output using only genuinely available sectors; it never substitutes an
ETF proxy or zero.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from config.tickers import SPX_SECTOR_CONFIG, TICKERS

SPX_BENCHMARK_TICKER = "SPX INDEX"
DEFAULT_HORIZONS = (1, 5, 20, 63)
DEFAULT_FLAT_THRESHOLD_PCT = 0.25
WEIGHT_SUM_TOLERANCE = 0.15


def _resolve_col(df: pd.DataFrame, ticker: str):
    """Case-insensitive column lookup. Returns the actual column or None."""
    target = ticker.upper().strip()
    for col in df.columns:
        if str(col).upper().strip() == target:
            return col
    return None


def _sector_series(df: pd.DataFrame, sector_key: str):
    cfg = SPX_SECTOR_CONFIG[sector_key]
    col = _resolve_col(df, cfg["ticker"])
    if col is None:
        return None
    series = pd.to_numeric(df[col], errors="coerce").dropna()
    return series if len(series) else None


def _spx_series(df: pd.DataFrame):
    col = _resolve_col(df, SPX_BENCHMARK_TICKER)
    if col is None:
        return None
    series = pd.to_numeric(df[col], errors="coerce").dropna()
    return series if len(series) else None


def build_spx_dispersion_index(df: pd.DataFrame, asof=None) -> pd.Series:
    """Return the optional Cboe S&P 500 Dispersion Index (DSPX).

    DSPX is a separate, forward-looking implied-dispersion index.  It is never
    replaced by the realised cross-sector dispersion calculated by this model,
    and the realised series is never relabelled as DSPX.  Missing source data
    therefore returns an empty series.
    """
    ticker = TICKERS.get("DSPX", "DSPX INDEX")
    col = _resolve_col(df, ticker)
    if col is None:
        return pd.Series(dtype=float, name="dspx")
    series = pd.to_numeric(df[col], errors="coerce").dropna().sort_index()
    if asof is not None:
        series = series.loc[series.index <= pd.Timestamp(asof)]
    series = series[~series.index.duplicated(keep="last")]
    series.name = "dspx"
    return series


def _available_sector_series(df: pd.DataFrame, asof=None) -> dict[str, pd.Series]:
    output: dict[str, pd.Series] = {}
    for key in SPX_SECTOR_CONFIG:
        series = _sector_series(df, key)
        if series is None:
            continue
        if asof is not None:
            series = series.loc[:pd.Timestamp(asof)]
        if len(series):
            output[key] = series
    return output


def build_sector_price_frame(df: pd.DataFrame, asof=None) -> pd.DataFrame:
    """Common-calendar frame of every available S5 sector series.

    The frame may contain fewer than 11 sectors when source inputs are missing.
    This allows a Partial audit with an honest denominator. It never inserts a
    proxy or zero. The snapshot status determines whether the frame is Ready.
    """
    available = _available_sector_series(df, asof=asof)
    if not available:
        return pd.DataFrame()
    return pd.DataFrame(available).dropna()


def build_sector_relative_frame(df: pd.DataFrame, asof=None) -> pd.DataFrame:
    """Common-calendar frame of available sectors plus SPX."""
    sector_frame = build_sector_price_frame(df, asof=asof)
    spx = _spx_series(df)
    if sector_frame.empty or spx is None:
        return pd.DataFrame()
    if asof is not None:
        spx = spx.loc[:pd.Timestamp(asof)]
    combined = sector_frame.copy()
    combined["spx"] = spx
    return combined.dropna()


def calculate_sector_returns(
    sector_frame: pd.DataFrame,
    horizons=DEFAULT_HORIZONS,
) -> pd.DataFrame:
    """Log returns in percent for every frame column at the latest date."""
    if sector_frame.empty:
        return pd.DataFrame()
    rows = []
    for col in sector_frame.columns:
        prices = pd.to_numeric(sector_frame[col], errors="coerce")
        row = {"column": col}
        for horizon in horizons:
            key = f"ret_{horizon}d_pct"
            if len(prices) > horizon and prices.iloc[-1] > 0 and prices.iloc[-horizon - 1] > 0:
                row[key] = float(100 * np.log(prices.iloc[-1] / prices.iloc[-horizon - 1]))
            else:
                row[key] = np.nan
        rows.append(row)
    return pd.DataFrame(rows).set_index("column")


def _classify_quadrant(short, long_, threshold):
    if pd.isna(short) or pd.isna(long_):
        return "—"
    if abs(short) < threshold or abs(long_) < threshold:
        return "Neutral / inconclusive"
    if short > threshold and long_ > threshold:
        return "Leader"
    if short > threshold and long_ < -threshold:
        return "Improving"
    if short < -threshold and long_ > threshold:
        return "Weakening"
    if short < -threshold and long_ < -threshold:
        return "Laggard"
    return "Neutral / inconclusive"


def build_sector_weight_snapshot(weights_df: pd.DataFrame, asof=None) -> pd.DataFrame:
    """One row per sector with latest weight and 1/3/12-period changes."""
    if weights_df is None or weights_df.empty:
        return pd.DataFrame()
    frame = weights_df.copy()
    if asof is not None:
        frame = frame.loc[:pd.Timestamp(asof)]
    if frame.empty:
        return pd.DataFrame()

    rows = []
    for key, cfg in SPX_SECTOR_CONFIG.items():
        wcol = cfg["weight_column"]
        base = {
            "sector": key,
            "display_name": cfg["display_name"],
            "weight_column": wcol,
            "latest_weight": np.nan,
            "weight_date": None,
            "chg_1p_pp": np.nan,
            "chg_3p_pp": np.nan,
            "chg_12p_pp": np.nan,
        }
        if wcol not in frame.columns:
            rows.append(base)
            continue
        series = pd.to_numeric(frame[wcol], errors="coerce").dropna()
        if series.empty:
            rows.append(base)
            continue

        def _change(periods: int):
            return float(series.iloc[-1] - series.iloc[-periods - 1]) if len(series) > periods else np.nan

        base.update({
            "latest_weight": float(series.iloc[-1]),
            "weight_date": series.index[-1].date(),
            "chg_1p_pp": _change(1),
            "chg_3p_pp": _change(3),
            "chg_12p_pp": _change(12),
        })
        rows.append(base)
    return pd.DataFrame(rows).set_index("sector")


def _weight_context(weights_df: pd.DataFrame | None, asof=None) -> dict:
    result = {
        "weight_date": None,
        "previous_weight_date": None,
        "weight_sum_pct": np.nan,
        "top_three_weight_share_pct": np.nan,
        "valid_weight_count": 0,
        "weight_snapshot": pd.DataFrame(),
    }
    if weights_df is None or weights_df.empty:
        return result
    frame = weights_df.copy()
    if asof is not None:
        frame = frame.loc[:pd.Timestamp(asof)]
    if frame.empty:
        return result
    snapshot = build_sector_weight_snapshot(frame, asof=None)
    valid = snapshot["latest_weight"].dropna() if not snapshot.empty else pd.Series(dtype=float)
    result.update({
        "weight_date": frame.index[-1].date(),
        "previous_weight_date": frame.index[-2].date() if len(frame) > 1 else None,
        "weight_sum_pct": float(valid.sum()) if len(valid) else np.nan,
        "top_three_weight_share_pct": float(valid.nlargest(3).sum()) if len(valid) else np.nan,
        "valid_weight_count": int(valid.count()),
        "weight_snapshot": snapshot,
    })
    return result


def build_sector_snapshot(
    df: pd.DataFrame,
    weights_df=None,
    horizons=DEFAULT_HORIZONS,
    short_window: int = 20,
    long_window: int = 63,
    flat_threshold_pct: float = DEFAULT_FLAT_THRESHOLD_PCT,
    asof=None,
) -> dict:
    """Return a traceable sector snapshot with Ready/Partial/Missing status."""
    available_keys = list(_available_sector_series(df, asof=asof))
    missing_sectors = [
        cfg["ticker"] for key, cfg in SPX_SECTOR_CONFIG.items()
        if key not in available_keys
    ]
    spx_available = _spx_series(df) is not None
    missing = list(missing_sectors)
    if not spx_available:
        missing.append(SPX_BENCHMARK_TICKER)

    sector_frame = build_sector_price_frame(df, asof=asof)
    relative_frame = build_sector_relative_frame(df, asof=asof)
    if sector_frame.empty:
        return {
            "status": "Missing data",
            "missing": missing,
            "sector_only_date": None,
            "relative_model_date": None,
            "weight_date": None,
            "previous_weight_date": None,
            "weight_sum_pct": np.nan,
            "top_three_weight_share_pct": np.nan,
            "valid_weight_count": 0,
            "sector_only_obs": 0,
            "relative_obs": 0,
            "available_sector_count": 0,
            "configured_sector_count": len(SPX_SECTOR_CONFIG),
            "per_sector": [],
            "sector_frame": sector_frame,
            "relative_frame": relative_frame,
        }

    required_history = max([*horizons, short_window, long_window]) + 1
    enough_history = len(relative_frame) >= required_history
    status = (
        "Ready"
        if len(available_keys) == len(SPX_SECTOR_CONFIG)
        and spx_available
        and not relative_frame.empty
        and enough_history
        else "Partial"
    )
    sector_only_date = sector_frame.index[-1].date()
    relative_model_date = relative_frame.index[-1].date() if not relative_frame.empty else None

    abs_rets = calculate_sector_returns(sector_frame, horizons)
    rel_rets = calculate_sector_returns(relative_frame, horizons) if not relative_frame.empty else pd.DataFrame()
    weight_ctx = _weight_context(weights_df, asof=relative_model_date or sector_only_date)
    weight_snap = weight_ctx.pop("weight_snapshot")

    per_sector = []
    for key, cfg in SPX_SECTOR_CONFIG.items():
        present = key in sector_frame.columns
        row = {
            "sector": key,
            "display_name": cfg["display_name"],
            "ticker": cfg["ticker"],
            "weight_column": cfg["weight_column"],
            "latest_level": float(sector_frame[key].iloc[-1]) if present else np.nan,
        }
        for horizon in horizons:
            row[f"ret_{horizon}d_pct"] = (
                abs_rets.loc[key, f"ret_{horizon}d_pct"]
                if present and key in abs_rets.index else np.nan
            )
            rel_value = np.nan
            if not rel_rets.empty and key in rel_rets.index and "spx" in rel_rets.index:
                sector_ret = rel_rets.loc[key, f"ret_{horizon}d_pct"]
                spx_ret = rel_rets.loc["spx", f"ret_{horizon}d_pct"]
                if pd.notna(sector_ret) and pd.notna(spx_ret):
                    rel_value = float(sector_ret - spx_ret)
            row[f"rel_ret_{horizon}d_pct"] = rel_value

        if not weight_snap.empty and key in weight_snap.index:
            for field in ("latest_weight", "chg_1p_pp", "chg_3p_pp", "chg_12p_pp"):
                source_field = field
                target_field = "weight_pct" if field == "latest_weight" else field
                row[target_field] = weight_snap.loc[key, source_field]
        else:
            row.update({
                "weight_pct": np.nan,
                "chg_1p_pp": np.nan,
                "chg_3p_pp": np.nan,
                "chg_12p_pp": np.nan,
            })

        short = row.get(f"rel_ret_{short_window}d_pct", np.nan)
        long_ = row.get(f"rel_ret_{long_window}d_pct", np.nan)
        row["quadrant"] = _classify_quadrant(short, long_, flat_threshold_pct)
        if not present:
            row["status"] = "Missing data"
        elif relative_frame.empty or key not in relative_frame.columns:
            row["status"] = "Partial"
        else:
            row["status"] = "Ready"
        per_sector.append(row)

    return {
        "status": status,
        "missing": missing,
        "sector_only_date": sector_only_date,
        "relative_model_date": relative_model_date,
        "sector_only_obs": int(len(sector_frame)),
        "relative_obs": int(len(relative_frame)),
        "enough_history": bool(enough_history),
        "required_history": int(required_history),
        "available_sector_count": int(len(available_keys)),
        "configured_sector_count": int(len(SPX_SECTOR_CONFIG)),
        "flat_threshold_pct": flat_threshold_pct,
        "short_window": short_window,
        "long_window": long_window,
        "per_sector": per_sector,
        "sector_frame": sector_frame,
        "relative_frame": relative_frame,
        **weight_ctx,
    }


def build_sector_breadth_history(df: pd.DataFrame, horizon: int = 20, asof=None) -> pd.DataFrame:
    """Positive breadth, SPX-outperformance breadth and one dispersion series.

    The denominator is the actual number of available aligned sectors. A
    separate relative-dispersion line is intentionally not returned because
    subtracting the same SPX return from every sector leaves cross-sectional
    standard deviation unchanged.
    """
    aligned = build_sector_relative_frame(df, asof=asof)
    if aligned.empty or "spx" not in aligned or len(aligned) <= horizon:
        return pd.DataFrame()
    returns = np.log(aligned) - np.log(aligned).shift(horizon)
    returns = returns.dropna()
    if returns.empty:
        return pd.DataFrame()
    sector_keys = [key for key in SPX_SECTOR_CONFIG if key in returns.columns]
    if not sector_keys:
        return pd.DataFrame()
    sector_returns = returns[sector_keys]
    spx_returns = returns["spx"]
    denominator = sector_returns.notna().sum(axis=1)
    positive_count = (sector_returns > 0).sum(axis=1)
    outperf_count = sector_returns.gt(spx_returns, axis=0).sum(axis=1)
    return pd.DataFrame({
        "positive_count": positive_count,
        "denominator": denominator,
        "positive_breadth_pct": 100 * positive_count / denominator.replace(0, np.nan),
        "relative_outperf_count": outperf_count,
        "relative_breadth_pct": 100 * outperf_count / denominator.replace(0, np.nan),
        "dispersion_pct": 100 * sector_returns.std(axis=1, ddof=0),
    }).dropna(how="all")


def build_reference_breadth_dispersion_history(
    df: pd.DataFrame,
    ma_window: int = 50,
    return_window: int = 21,
    asof=None,
) -> pd.DataFrame:
    """Reference-pack breadth and dispersion definitions.

    The Capital Flows reference pack defines sector breadth as the share of
    the 11 S&P 500 sector indices above their own 50-session moving average,
    and dispersion as the cross-sectional population standard deviation of
    trailing 21-session sector *simple* returns.  This function reproduces
    those definitions on the common S5-sector observation calendar.

    Missing sectors are not replaced with ETF proxies or zeros.  The breadth
    denominator is therefore the actual number of sectors with a valid price
    and moving average on each date.
    """
    if ma_window < 2 or return_window < 1:
        raise ValueError("ma_window must be >= 2 and return_window must be >= 1")
    prices = build_sector_price_frame(df, asof=asof)
    if prices.empty or len(prices) <= max(ma_window, return_window):
        return pd.DataFrame()

    moving_average = prices.rolling(ma_window, min_periods=ma_window).mean()
    valid_breadth = prices.notna() & moving_average.notna()
    above_ma = prices.gt(moving_average) & valid_breadth
    denominator = valid_breadth.sum(axis=1)
    above_count = above_ma.sum(axis=1)

    simple_returns_pct = 100 * (prices / prices.shift(return_window) - 1)
    valid_return_count = simple_returns_pct.notna().sum(axis=1)
    dispersion_pct = simple_returns_pct.std(axis=1, ddof=0)

    result = pd.DataFrame({
        "above_ma_count": above_count,
        "breadth_denominator": denominator,
        "above_ma_breadth_pct": (
            100 * above_count / denominator.replace(0, np.nan)
        ),
        "dispersion_valid_count": valid_return_count,
        "return_dispersion_pct": dispersion_pct,
    })
    return result.loc[
        (result["breadth_denominator"] > 0)
        | (result["dispersion_valid_count"] > 0)
    ].dropna(how="all")


def available_sector_inputs(df: pd.DataFrame, weights_df=None) -> dict:
    """Report raw and common-calendar input availability."""
    sectors = {}
    for key, cfg in SPX_SECTOR_CONFIG.items():
        series = _sector_series(df, key)
        sectors[key] = {
            "ticker": cfg["ticker"],
            "available": series is not None,
            "first_date": series.index[0].date() if series is not None else None,
            "latest_date": series.index[-1].date() if series is not None else None,
            "n_obs": int(len(series)) if series is not None else 0,
        }
    sector_frame = build_sector_price_frame(df)
    relative_frame = build_sector_relative_frame(df)
    spx = _spx_series(df)
    missing_weight_cols = []
    if weights_df is not None and not weights_df.empty:
        missing_weight_cols = [
            cfg["weight_column"] for cfg in SPX_SECTOR_CONFIG.values()
            if cfg["weight_column"] not in weights_df.columns
        ]
    available_count = sum(info["available"] for info in sectors.values())
    status = "Ready" if available_count == len(SPX_SECTOR_CONFIG) and spx is not None else ("Partial" if available_count else "Missing data")
    return {
        "sectors": sectors,
        "available_sector_count": int(available_count),
        "configured_sector_count": int(len(SPX_SECTOR_CONFIG)),
        "spx_available": spx is not None,
        "spx_latest": spx.index[-1].date() if spx is not None else None,
        "sector_common_first": sector_frame.index[0].date() if not sector_frame.empty else None,
        "sector_common_latest": sector_frame.index[-1].date() if not sector_frame.empty else None,
        "sector_common_obs": int(len(sector_frame)),
        "relative_common_first": relative_frame.index[0].date() if not relative_frame.empty else None,
        "relative_common_latest": relative_frame.index[-1].date() if not relative_frame.empty else None,
        "relative_common_obs": int(len(relative_frame)),
        "weight_available": weights_df is not None and not weights_df.empty,
        "missing_weight_columns": missing_weight_cols,
        "status": status,
    }


def build_sector_current_reading(
    df: pd.DataFrame,
    weights_df=None,
    short_window: int = 20,
    long_window: int = 63,
    asof=None,
) -> dict:
    """Descriptive current reading. No causal, flow or forecast language."""
    snapshot = build_sector_snapshot(
        df,
        weights_df,
        short_window=short_window,
        long_window=long_window,
        asof=asof,
    )
    if snapshot["status"] == "Missing data":
        return snapshot

    valid = [
        row for row in snapshot["per_sector"]
        if pd.notna(row.get(f"rel_ret_{short_window}d_pct"))
    ]

    def _rank(field: str, reverse=True):
        values = [
            (row["display_name"], row[field]) for row in valid
            if pd.notna(row.get(field))
        ]
        return sorted(values, key=lambda item: item[1], reverse=reverse)

    top_abs = _rank(f"ret_{short_window}d_pct")[:3]
    top_rel = _rank(f"rel_ret_{short_window}d_pct")[:3]
    lowest_rel = _rank(f"rel_ret_{short_window}d_pct", reverse=False)[:3]

    relative_frame = snapshot["relative_frame"]
    positive = outperf = denominator = 0
    dispersion = np.nan
    if not relative_frame.empty and len(relative_frame) > short_window:
        latest_return = np.log(relative_frame).iloc[-1] - np.log(relative_frame).iloc[-short_window - 1]
        sector_keys = [key for key in SPX_SECTOR_CONFIG if key in latest_return.index]
        sector_returns = latest_return[sector_keys]
        spx_return = latest_return["spx"]
        denominator = int(sector_returns.notna().sum())
        positive = int((sector_returns > 0).sum())
        outperf = int((sector_returns > spx_return).sum())
        dispersion = float(100 * sector_returns.std(ddof=0))

    quadrant_counts = {}
    for row in snapshot["per_sector"]:
        quadrant = row["quadrant"]
        quadrant_counts[quadrant] = quadrant_counts.get(quadrant, 0) + 1

    return {
        **snapshot,
        "top_abs": top_abs,
        "top_rel": top_rel,
        "bottom_rel": lowest_rel,
        "positive_count": positive,
        "positive_denom": denominator,
        "positive_breadth_pct": 100 * positive / denominator if denominator else np.nan,
        "outperf_count": outperf,
        "relative_breadth_pct": 100 * outperf / denominator if denominator else np.nan,
        "dispersion_pct": dispersion,
        "quadrant_counts": quadrant_counts,
    }
