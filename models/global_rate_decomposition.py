"""
models/global_rate_decomposition.py
===================================
Exact-tenor nominal / real / inflation decomposition for the country rate
boards.

Only countries and tenors with both a confirmed nominal government-yield
series and a same-tenor inflation-linked government-yield series are used.
The inflation leg is the arithmetic difference ``nominal - real``. Inputs are
joined on their exact observation dates; no forward-fill, interpolation,
proxy market, or zero replacement is allowed.

Pure functions only - no Streamlit imports.
"""
from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from config.tickers import REAL_RATE_TENORS, TICKERS
from models.global_rates import COUNTRY_LABELS, STANDARD_TENORS


DECOMPOSITION_HORIZONS: tuple[int, ...] = (5, 20)


def _normalise_asof(asof) -> pd.Timestamp | None:
    return None if asof is None else pd.Timestamp(asof)


def _exact_tenor_pairs(country: str) -> dict[str, tuple[str, str]]:
    """Return confirmed same-tenor nominal/real Bloomberg columns."""
    country = str(country).upper()
    pairs: dict[str, tuple[str, str]] = {}
    for tenor, _, real_key in REAL_RATE_TENORS.get(country, []):
        if tenor not in STANDARD_TENORS:
            continue
        nominal = TICKERS.get(f"{country}_{tenor}")
        real = TICKERS.get(real_key)
        if nominal and real:
            pairs[tenor] = (nominal, real)
    return pairs


def global_decomposition_requirements(country: str) -> dict[str, tuple[str, str]]:
    """Public copy of the exact-tenor input registry for audit displays."""
    return dict(_exact_tenor_pairs(country))


def available_global_decomposition_tenors(
    df: pd.DataFrame,
    country: str,
    min_observations: int = 21,
    asof=None,
) -> list[str]:
    """Return exact tenors with enough common nominal/real observations."""
    available: list[str] = []
    for tenor, (nominal, real) in _exact_tenor_pairs(country).items():
        if nominal not in df.columns or real not in df.columns:
            continue
        frame = build_global_rate_frame(df, country, tenor, asof=asof)
        if len(frame) >= int(min_observations):
            available.append(tenor)
    return sorted(available, key=STANDARD_TENORS.index)


def build_global_rate_frame(
    df: pd.DataFrame,
    country: str,
    tenor: str,
    asof=None,
) -> pd.DataFrame:
    """Return exact-date nominal, real, and implied-inflation levels."""
    country = str(country).upper()
    tenor = str(tenor).upper()
    pair = _exact_tenor_pairs(country).get(tenor)
    if pair is None:
        return pd.DataFrame(columns=["nominal", "real", "inflation"], dtype=float)

    nominal, real = pair
    if nominal not in df.columns or real not in df.columns:
        return pd.DataFrame(columns=["nominal", "real", "inflation"], dtype=float)

    frame = pd.DataFrame(index=pd.DatetimeIndex(df.index))
    frame["nominal"] = pd.to_numeric(df[nominal], errors="coerce")
    frame["real"] = pd.to_numeric(df[real], errors="coerce")
    asof_ts = _normalise_asof(asof)
    if asof_ts is not None:
        frame = frame.loc[:asof_ts]
    frame = frame.dropna(how="any").sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    frame["inflation"] = frame["nominal"] - frame["real"]
    return frame


def build_global_decomposition_snapshot(
    df: pd.DataFrame,
    country: str,
    horizons: Iterable[int] = DECOMPOSITION_HORIZONS,
    asof=None,
) -> pd.DataFrame:
    """Latest levels and changes for every supported exact tenor."""
    horizons = tuple(dict.fromkeys(int(h) for h in horizons if int(h) > 0))
    rows: list[dict] = []
    tenors = available_global_decomposition_tenors(
        df,
        country,
        min_observations=max(horizons, default=1) + 1,
        asof=asof,
    )
    for tenor in tenors:
        frame = build_global_rate_frame(df, country, tenor, asof=asof)
        latest = frame.iloc[-1]
        row = {
            "country": str(country).upper(),
            "label": COUNTRY_LABELS.get(str(country).upper(), str(country).upper()),
            "tenor": tenor,
            "nominal_pct": float(latest["nominal"]),
            "real_pct": float(latest["real"]),
            "inflation_pct": float(latest["inflation"]),
            "model_date": frame.index[-1].date(),
            "aligned_observations": len(frame),
        }
        for horizon in horizons:
            ago = frame.iloc[-horizon - 1]
            row[f"nominal_change_{horizon}d_bp"] = float(
                100.0 * (latest["nominal"] - ago["nominal"])
            )
            row[f"real_change_{horizon}d_bp"] = float(
                100.0 * (latest["real"] - ago["real"])
            )
            row[f"inflation_change_{horizon}d_bp"] = float(
                100.0 * (latest["inflation"] - ago["inflation"])
            )
        rows.append(row)
    return pd.DataFrame(rows)


def rolling_global_rate_attribution(
    df: pd.DataFrame,
    country: str,
    tenor: str = "10Y",
    window: int = 10,
    asof=None,
) -> pd.DataFrame:
    """Rolling exact-tenor yield-change attribution in basis points."""
    frame = build_global_rate_frame(df, country, tenor, asof=asof)
    if len(frame) < int(window) + 1:
        return pd.DataFrame()

    out = pd.DataFrame(index=frame.index)
    out["nominal_change_bp"] = 100.0 * frame["nominal"].diff(window)
    out["real_contribution_bp"] = 100.0 * frame["real"].diff(window)
    out["inflation_contribution_bp"] = 100.0 * frame["inflation"].diff(window)
    out["residual_bp"] = (
        out["nominal_change_bp"]
        - out["real_contribution_bp"]
        - out["inflation_contribution_bp"]
    )
    return out


def global_decomposition_readiness(
    df: pd.DataFrame,
    countries: Iterable[str],
    min_observations: int = 21,
    asof=None,
) -> pd.DataFrame:
    """Country-level audit table for the real/inflation extension."""
    rows = []
    for country in countries:
        country = str(country).upper()
        configured = list(_exact_tenor_pairs(country))
        available = available_global_decomposition_tenors(
            df,
            country,
            min_observations=min_observations,
            asof=asof,
        )
        model_dates = []
        observations = []
        for tenor in available:
            frame = build_global_rate_frame(df, country, tenor, asof=asof)
            model_dates.append(frame.index[-1].date())
            observations.append(len(frame))
        if available:
            status = "Ready"
            note = "Exact-tenor nominal and real series"
        elif configured:
            status = "Missing data"
            note = "Configured exact-tenor inputs are empty or too short"
        else:
            status = "Unavailable"
            note = "No confirmed same-market real-yield series; no proxy used"
        rows.append({
            "country": country,
            "label": COUNTRY_LABELS.get(country, country),
            "status": status,
            "available_tenors": available,
            "configured_tenors": configured,
            "latest_model_date": max(model_dates) if model_dates else None,
            "minimum_aligned_observations": min(observations) if observations else 0,
            "note": note,
        })
    return pd.DataFrame(rows)
