"""
models/country_rate_boards.py
=============================
Transparent nominal sovereign-curve boards for the seven countries already
available in DATA.xlsx.

All production calculations first align 2Y / 5Y / 10Y / 30Y observations on
one common country calendar.  No forward-fill, interpolation, or independently
dated latest-value subtraction is used.

Pure functions only — no Streamlit imports.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from config.tickers import REGIME_COUNTRIES, TICKERS
from models.global_rates import COUNTRY_LABELS, STANDARD_TENORS, TENOR_NUMERIC

BOARD_HORIZONS: tuple[int, ...] = (1, 5, 20, 63)
BOARD_SLOPE_PAIRS: dict[str, tuple[str, str]] = {
    "2s5s": ("2Y", "5Y"),
    "2s10s": ("2Y", "10Y"),
    "2s30s": ("2Y", "30Y"),
    "5s10s": ("5Y", "10Y"),
    "5s30s": ("5Y", "30Y"),
    "10s30s": ("10Y", "30Y"),
}


def _normalise_asof(asof) -> pd.Timestamp | None:
    if asof is None:
        return None
    return pd.Timestamp(asof)


def _country_ticker(country: str, tenor: str) -> str | None:
    return TICKERS.get(f"{country}_{tenor}")


def _required_tickers(country: str) -> dict[str, str]:
    return {
        tenor: ticker
        for tenor in STANDARD_TENORS
        if (ticker := _country_ticker(country, tenor)) is not None
    }


def _percentile_rank(series: pd.Series, window: int = 252) -> float | None:
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return None
    tail = clean.iloc[-window:] if len(clean) > window else clean
    if len(tail) < 2:
        return None
    latest = float(tail.iloc[-1])
    return float(100.0 * (tail <= latest).sum() / len(tail))


def build_country_curve_frame(
    df: pd.DataFrame,
    country: str,
    asof=None,
    require_all: bool = True,
) -> pd.DataFrame:
    """Return a common-calendar 2Y/5Y/10Y/30Y curve frame for one country.

    Columns use tenor labels rather than Bloomberg strings.  When
    ``require_all`` is True, all four tenors must exist; otherwise available
    tenors are retained and aligned.
    """
    country = str(country).upper()
    if country not in REGIME_COUNTRIES:
        raise ValueError(f"Unsupported country: {country}")

    mapping = _required_tickers(country)
    missing = [
        tenor for tenor in STANDARD_TENORS
        if tenor not in mapping or mapping[tenor] not in df.columns
    ]
    if require_all and missing:
        return pd.DataFrame(columns=STANDARD_TENORS, dtype=float)

    present = {
        tenor: ticker for tenor, ticker in mapping.items()
        if ticker in df.columns
    }
    if not present:
        return pd.DataFrame(dtype=float)

    frame = pd.DataFrame(index=pd.DatetimeIndex(df.index))
    for tenor, ticker in present.items():
        frame[tenor] = pd.to_numeric(df[ticker], errors="coerce")

    asof_ts = _normalise_asof(asof)
    if asof_ts is not None:
        frame = frame.loc[:asof_ts]

    ordered = [tenor for tenor in STANDARD_TENORS if tenor in frame.columns]
    frame = frame[ordered].dropna(how="any").sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    return frame


def assess_country_board_readiness(
    df: pd.DataFrame,
    country: str,
    min_observations: int = 64,
    asof=None,
) -> dict:
    """Return one consistent readiness assessment for a country board."""
    country = str(country).upper()
    mapping = _required_tickers(country)
    missing_tenors: list[str] = []
    missing_tickers: list[str] = []
    for tenor in STANDARD_TENORS:
        ticker = mapping.get(tenor)
        if ticker is None or ticker not in df.columns:
            missing_tenors.append(tenor)
            missing_tickers.append(ticker or f"{country}_{tenor}")
        elif pd.to_numeric(df[ticker], errors="coerce").dropna().empty:
            missing_tenors.append(tenor)
            missing_tickers.append(ticker)

    if len(missing_tenors) == len(STANDARD_TENORS):
        return {
            "country": country,
            "label": COUNTRY_LABELS.get(country, country),
            "status": "Missing data",
            "missing_tenors": missing_tenors,
            "missing_tickers": missing_tickers,
            "aligned_observations": 0,
            "first_date": None,
            "model_date": None,
            "enough_history": False,
        }

    if missing_tenors:
        return {
            "country": country,
            "label": COUNTRY_LABELS.get(country, country),
            "status": "Partial",
            "missing_tenors": missing_tenors,
            "missing_tickers": missing_tickers,
            "aligned_observations": 0,
            "first_date": None,
            "model_date": None,
            "enough_history": False,
        }

    aligned = build_country_curve_frame(df, country, asof=asof, require_all=True)
    n_obs = len(aligned)
    enough = n_obs >= min_observations
    return {
        "country": country,
        "label": COUNTRY_LABELS.get(country, country),
        "status": "Ready" if enough else "Partial",
        "missing_tenors": [],
        "missing_tickers": [],
        "aligned_observations": n_obs,
        "first_date": aligned.index.min().date() if n_obs else None,
        "model_date": aligned.index.max().date() if n_obs else None,
        "enough_history": enough,
    }


def available_country_boards(
    df: pd.DataFrame,
    min_observations: int = 64,
    asof=None,
) -> dict[str, dict]:
    return {
        country: assess_country_board_readiness(
            df, country, min_observations=min_observations, asof=asof
        )
        for country in REGIME_COUNTRIES
    }


def build_country_yield_change_table(
    df: pd.DataFrame,
    country: str,
    horizons: Iterable[int] = BOARD_HORIZONS,
    percentile_window: int = 252,
    asof=None,
) -> pd.DataFrame:
    """Latest yield levels and common-calendar changes by tenor."""
    aligned = build_country_curve_frame(df, country, asof=asof, require_all=True)
    if aligned.empty:
        return pd.DataFrame()

    horizons = tuple(dict.fromkeys(int(h) for h in horizons if int(h) > 0))
    rows: list[dict] = []
    for tenor in STANDARD_TENORS:
        s = aligned[tenor]
        row = {
            "country": country,
            "label": COUNTRY_LABELS.get(country, country),
            "tenor": tenor,
            "tenor_num": TENOR_NUMERIC[tenor],
            "yield_pct": float(s.iloc[-1]),
            "percentile_1y_pct": _percentile_rank(s, percentile_window),
            "model_date": aligned.index[-1].date(),
        }
        for horizon in horizons:
            row[f"change_{horizon}d_bp"] = (
                float(100.0 * (s.iloc[-1] - s.iloc[-horizon - 1]))
                if len(s) > horizon else None
            )
        rows.append(row)
    return pd.DataFrame(rows).sort_values("tenor_num").reset_index(drop=True)


def build_country_slope_history(
    df: pd.DataFrame,
    country: str,
    asof=None,
) -> pd.DataFrame:
    """Return all six standard nominal curve slopes in basis points."""
    aligned = build_country_curve_frame(df, country, asof=asof, require_all=True)
    if aligned.empty:
        return pd.DataFrame()
    out = pd.DataFrame(index=aligned.index)
    for label, (front, back) in BOARD_SLOPE_PAIRS.items():
        out[label] = 100.0 * (aligned[back] - aligned[front])
    return out


def build_country_slope_table(
    df: pd.DataFrame,
    country: str,
    horizons: Iterable[int] = BOARD_HORIZONS,
    percentile_window: int = 252,
    asof=None,
) -> pd.DataFrame:
    slopes = build_country_slope_history(df, country, asof=asof)
    if slopes.empty:
        return pd.DataFrame()
    horizons = tuple(dict.fromkeys(int(h) for h in horizons if int(h) > 0))
    rows: list[dict] = []
    for label, (front, back) in BOARD_SLOPE_PAIRS.items():
        s = slopes[label]
        row = {
            "country": country,
            "label": COUNTRY_LABELS.get(country, country),
            "slope": label,
            "front": front,
            "back": back,
            "slope_bp": float(s.iloc[-1]),
            "inverted": bool(s.iloc[-1] < 0),
            "percentile_1y_pct": _percentile_rank(s, percentile_window),
            "model_date": slopes.index[-1].date(),
        }
        for horizon in horizons:
            row[f"change_{horizon}d_bp"] = (
                float(s.iloc[-1] - s.iloc[-horizon - 1])
                if len(s) > horizon else None
            )
        rows.append(row)
    return pd.DataFrame(rows)


def classify_country_curve_move(
    yield_table: pd.DataFrame,
    slope_table: pd.DataFrame,
    horizon: int = 20,
    threshold_bp: float = 5.0,
) -> dict:
    """Describe level and 2s10s-shape movement without a causal claim."""
    if yield_table.empty or slope_table.empty:
        return {
            "status": "Missing data",
            "level_direction": "Unavailable",
            "shape_direction": "Unavailable",
            "summary": "Insufficient common curve history.",
        }

    change_col = f"change_{int(horizon)}d_bp"
    by_tenor = yield_table.set_index("tenor")
    slope_rows = slope_table.set_index("slope")
    if change_col not in by_tenor.columns or change_col not in slope_rows.columns:
        return {
            "status": "Partial",
            "level_direction": "Unavailable",
            "shape_direction": "Unavailable",
            "summary": f"{horizon}D changes are unavailable.",
        }

    front_change = by_tenor.at["2Y", change_col]
    back_change = by_tenor.at["10Y", change_col]
    slope_change = slope_rows.at["2s10s", change_col]
    if any(pd.isna(v) for v in (front_change, back_change, slope_change)):
        return {
            "status": "Partial",
            "level_direction": "Unavailable",
            "shape_direction": "Unavailable",
            "summary": f"{horizon}D changes are unavailable.",
        }

    if front_change >= threshold_bp and back_change >= threshold_bp:
        level = "Bearish level move"
        level_text = "2Y and 10Y yields both rose"
    elif front_change <= -threshold_bp and back_change <= -threshold_bp:
        level = "Bullish level move"
        level_text = "2Y and 10Y yields both fell"
    else:
        level = "Mixed / limited level move"
        level_text = "2Y and 10Y did not move together beyond the threshold"

    if slope_change > threshold_bp:
        shape = "Steepening"
        shape_text = "2s10s steepened"
    elif slope_change < -threshold_bp:
        shape = "Flattening"
        shape_text = "2s10s flattened"
    else:
        shape = "Limited shape change"
        shape_text = "2s10s changed by less than the threshold"

    return {
        "status": "Ready",
        "level_direction": level,
        "shape_direction": shape,
        "front_change_bp": float(front_change),
        "back_change_bp": float(back_change),
        "slope_change_bp": float(slope_change),
        "threshold_bp": float(threshold_bp),
        "summary": (
            f"Over {horizon} common observations, {level_text}; {shape_text}."
        ),
    }


def build_country_board(
    df: pd.DataFrame,
    country: str,
    horizons: Iterable[int] = BOARD_HORIZONS,
    percentile_window: int = 252,
    move_horizon: int = 20,
    move_threshold_bp: float = 5.0,
    asof=None,
) -> dict:
    """Build the complete pure-model payload for one country page."""
    country = str(country).upper()
    horizons = tuple(dict.fromkeys(int(h) for h in horizons if int(h) > 0))
    min_obs = max(max(horizons, default=1), percentile_window // 4) + 1
    readiness = assess_country_board_readiness(
        df, country, min_observations=min_obs, asof=asof
    )
    payload = dict(readiness)
    payload.update({
        "horizons": horizons,
        "percentile_window": int(percentile_window),
        "move_horizon": int(move_horizon),
        "move_threshold_bp": float(move_threshold_bp),
    })
    if readiness["status"] == "Missing data":
        payload.update({
            "curve_frame": pd.DataFrame(),
            "yield_table": pd.DataFrame(),
            "slope_history": pd.DataFrame(),
            "slope_table": pd.DataFrame(),
            "move": classify_country_curve_move(pd.DataFrame(), pd.DataFrame()),
        })
        return payload

    aligned = build_country_curve_frame(df, country, asof=asof, require_all=True)
    if aligned.empty:
        payload["status"] = "Partial"
        payload.update({
            "curve_frame": aligned,
            "yield_table": pd.DataFrame(),
            "slope_history": pd.DataFrame(),
            "slope_table": pd.DataFrame(),
            "move": classify_country_curve_move(pd.DataFrame(), pd.DataFrame()),
        })
        return payload

    yield_table = build_country_yield_change_table(
        df, country, horizons=horizons, percentile_window=percentile_window, asof=asof
    )
    slope_history = build_country_slope_history(df, country, asof=asof)
    slope_table = build_country_slope_table(
        df, country, horizons=horizons, percentile_window=percentile_window, asof=asof
    )
    payload.update({
        "curve_frame": aligned,
        "yield_table": yield_table,
        "slope_history": slope_history,
        "slope_table": slope_table,
        "move": classify_country_curve_move(
            yield_table, slope_table, horizon=move_horizon,
            threshold_bp=move_threshold_bp,
        ),
    })
    return payload


def build_global_country_board_overview(
    df: pd.DataFrame,
    horizon: int = 20,
    asof=None,
) -> pd.DataFrame:
    """Cross-country overview on one shared 28-series observation calendar.

    This is intentionally stricter than individual country boards so the
    cross-country ranking does not compare different dates.
    """
    columns: dict[str, str] = {}
    for country in REGIME_COUNTRIES:
        for tenor in STANDARD_TENORS:
            ticker = _country_ticker(country, tenor)
            if ticker is None or ticker not in df.columns:
                return pd.DataFrame()
            columns[f"{country}_{tenor}"] = ticker

    frame = pd.DataFrame(index=pd.DatetimeIndex(df.index))
    for key, ticker in columns.items():
        frame[key] = pd.to_numeric(df[ticker], errors="coerce")
    asof_ts = _normalise_asof(asof)
    if asof_ts is not None:
        frame = frame.loc[:asof_ts]
    frame = frame.dropna(how="any").sort_index()
    if len(frame) <= horizon:
        return pd.DataFrame()

    rows: list[dict] = []
    for country in REGIME_COUNTRIES:
        y2 = frame[f"{country}_2Y"]
        y10 = frame[f"{country}_10Y"]
        y30 = frame[f"{country}_30Y"]
        current_2 = float(y2.iloc[-1])
        current_10 = float(y10.iloc[-1])
        current_30 = float(y30.iloc[-1])
        change_2 = float(100.0 * (y2.iloc[-1] - y2.iloc[-horizon - 1]))
        change_10 = float(100.0 * (y10.iloc[-1] - y10.iloc[-horizon - 1]))
        slope_now = float(100.0 * (current_10 - current_2))
        slope_then = float(100.0 * (y10.iloc[-horizon - 1] - y2.iloc[-horizon - 1]))
        rows.append({
            "country": country,
            "label": COUNTRY_LABELS.get(country, country),
            "model_date": frame.index[-1].date(),
            "aligned_observations": len(frame),
            "yield_2y_pct": current_2,
            "yield_10y_pct": current_10,
            "yield_30y_pct": current_30,
            f"change_{horizon}d_2y_bp": change_2,
            f"change_{horizon}d_10y_bp": change_10,
            "slope_2s10s_bp": slope_now,
            f"change_{horizon}d_2s10s_bp": slope_now - slope_then,
            "inverted": slope_now < 0,
            "status": "Ready",
        })
    return pd.DataFrame(rows)


def build_country_board_current_reading(
    df: pd.DataFrame,
    country: str,
    horizon: int = 20,
    asof=None,
) -> dict:
    board = build_country_board(
        df, country, horizons=(1, 5, horizon, 63), move_horizon=horizon, asof=asof
    )
    if board.get("status") != "Ready":
        return {
            "country": country,
            "label": COUNTRY_LABELS.get(country, country),
            "status": board.get("status", "Missing data"),
            "missing_tenors": board.get("missing_tenors", []),
            "model_date": board.get("model_date"),
        }

    yt = board["yield_table"].set_index("tenor")
    st = board["slope_table"].set_index("slope")
    return {
        "country": country,
        "label": COUNTRY_LABELS.get(country, country),
        "status": "Ready",
        "model_date": board["model_date"],
        "aligned_observations": board["aligned_observations"],
        "yield_10y_pct": float(yt.at["10Y", "yield_pct"]),
        f"change_{horizon}d_10y_bp": float(yt.at["10Y", f"change_{horizon}d_bp"]),
        "slope_2s10s_bp": float(st.at["2s10s", "slope_bp"]),
        f"change_{horizon}d_2s10s_bp": float(st.at["2s10s", f"change_{horizon}d_bp"]),
        "move": board["move"],
    }
