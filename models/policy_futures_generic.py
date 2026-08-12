"""
models/policy_futures_generic.py
================================
Transparent monitor for the generic continuous policy-futures series already
present in DATA.xlsx.

The model intentionally does *not* infer contract months, expiry dates, FOMC
meeting outcomes, or meeting probabilities.  Generic Bloomberg tickers such as
FF1/SFR1/SER1 roll from one underlying contract to the next, so the rank is
reported as "front / second / third generic" rather than as a fixed expiry.

Quote conversion
----------------
All three supported families use an IMM-index-style quote, so the displayed
implied reference rate is simply::

    implied_rate_pct = 100.0 - futures_price

Contract-family interpretation is kept explicit:

* FF  — 30-Day Federal Funds futures; monthly average daily EFFR.
* SER — 1-Month SOFR futures; monthly average daily SOFR.
* SFR — 3-Month SOFR futures; compounded daily SOFR over a reference quarter.

Pure functions only — no Streamlit imports, no forward-fill, no interpolation,
and no zero substitution.
"""
from __future__ import annotations

from typing import Iterable

import numpy as np
import pandas as pd

from config.tickers import POLICY_FUTURES_CONFIG, TICKERS

GENERIC_RANKS: tuple[int, ...] = (1, 2, 3)
DEFAULT_HORIZONS: tuple[int, ...] = (1, 5, 20, 63)
DEFAULT_MIN_OBSERVATIONS = 64
DEFAULT_FLAT_THRESHOLD_BP = 5.0


def _normalise_asof(asof) -> pd.Timestamp | None:
    return None if asof is None else pd.Timestamp(asof)


def _family_code(family: str) -> str:
    code = str(family).upper().strip()
    if code not in POLICY_FUTURES_CONFIG:
        raise ValueError(
            f"Unsupported policy-futures family: {family}. "
            f"Expected one of {tuple(POLICY_FUTURES_CONFIG)}"
        )
    return code


def _family_tickers(family: str) -> dict[int, str]:
    code = _family_code(family)
    return {
        int(rank): str(ticker).upper().strip()
        for rank, ticker in POLICY_FUTURES_CONFIG[code]["generic_tickers"].items()
    }


def classify_generic_curve(
    front_to_third_bp: float | None,
    flat_threshold_bp: float = DEFAULT_FLAT_THRESHOLD_BP,
) -> str:
    """Classify the generic rank-1 to rank-3 implied-rate slope descriptively."""
    if front_to_third_bp is None or pd.isna(front_to_third_bp):
        return "Unavailable"
    if front_to_third_bp > flat_threshold_bp:
        return "Higher implied rates at rank 3"
    if front_to_third_bp < -flat_threshold_bp:
        return "Lower implied rates at rank 3"
    return "Flat / inconclusive"


def build_policy_futures_price_frame(
    df: pd.DataFrame,
    family: str,
    asof=None,
    require_all: bool = True,
) -> pd.DataFrame:
    """Return a common-calendar generic price frame with integer rank columns.

    When ``require_all`` is true, the frame is empty unless all three generic
    ranks exist and contain observations.  Missing observations are never
    forward-filled.
    """
    code = _family_code(family)
    mapping = _family_tickers(code)
    present: dict[int, str] = {}
    for rank, ticker in mapping.items():
        if ticker in df.columns and not pd.to_numeric(df[ticker], errors="coerce").dropna().empty:
            present[rank] = ticker

    if require_all and len(present) != len(GENERIC_RANKS):
        return pd.DataFrame(columns=list(GENERIC_RANKS), dtype=float)
    if not present:
        return pd.DataFrame(dtype=float)

    frame = pd.DataFrame(index=pd.DatetimeIndex(df.index))
    for rank in GENERIC_RANKS:
        ticker = present.get(rank)
        if ticker is not None:
            frame[rank] = pd.to_numeric(df[ticker], errors="coerce")

    asof_ts = _normalise_asof(asof)
    if asof_ts is not None:
        frame = frame.loc[:asof_ts]
    frame = frame.sort_index()
    frame = frame[~frame.index.duplicated(keep="last")]
    frame = frame.dropna(how="any")
    return frame


def build_policy_futures_implied_rate_frame(
    df: pd.DataFrame,
    family: str,
    asof=None,
    require_all: bool = True,
) -> pd.DataFrame:
    """Return implied reference rates (%) on one common generic calendar."""
    prices = build_policy_futures_price_frame(
        df, family, asof=asof, require_all=require_all
    )
    if prices.empty:
        return prices.copy()
    return 100.0 - prices


def assess_policy_futures_family(
    df: pd.DataFrame,
    family: str,
    min_observations: int = DEFAULT_MIN_OBSERVATIONS,
    asof=None,
) -> dict:
    """One consistent readiness assessment for a futures family."""
    code = _family_code(family)
    cfg = POLICY_FUTURES_CONFIG[code]
    mapping = _family_tickers(code)
    missing: list[str] = []
    for rank in GENERIC_RANKS:
        ticker = mapping[rank]
        if ticker not in df.columns or pd.to_numeric(df[ticker], errors="coerce").dropna().empty:
            missing.append(ticker)

    if len(missing) == len(GENERIC_RANKS):
        return {
            "family": code,
            "display_name": cfg["display_name"],
            "status": "Missing data",
            "missing": missing,
            "aligned_observations": 0,
            "common_first_date": None,
            "model_date": None,
            "enough_history": False,
        }
    if missing:
        return {
            "family": code,
            "display_name": cfg["display_name"],
            "status": "Partial",
            "missing": missing,
            "aligned_observations": 0,
            "common_first_date": None,
            "model_date": None,
            "enough_history": False,
        }

    rates = build_policy_futures_implied_rate_frame(df, code, asof=asof)
    enough = len(rates) >= int(min_observations)
    return {
        "family": code,
        "display_name": cfg["display_name"],
        "status": "Ready" if enough else "Partial",
        "missing": [],
        "aligned_observations": int(len(rates)),
        "common_first_date": rates.index.min().date() if len(rates) else None,
        "model_date": rates.index.max().date() if len(rates) else None,
        "enough_history": enough,
    }


def available_policy_futures_families(
    df: pd.DataFrame,
    min_observations: int = DEFAULT_MIN_OBSERVATIONS,
    asof=None,
) -> dict[str, dict]:
    return {
        family: assess_policy_futures_family(
            df, family, min_observations=min_observations, asof=asof
        )
        for family in POLICY_FUTURES_CONFIG
    }


def _horizon_change_bp(series: pd.Series, horizon: int) -> float | None:
    h = int(horizon)
    if h <= 0 or len(series) <= h:
        return None
    return float(100.0 * (series.iloc[-1] - series.iloc[-h - 1]))


def build_policy_futures_family_snapshot(
    df: pd.DataFrame,
    family: str,
    horizons: Iterable[int] = DEFAULT_HORIZONS,
    min_observations: int = DEFAULT_MIN_OBSERVATIONS,
    flat_threshold_bp: float = DEFAULT_FLAT_THRESHOLD_BP,
    asof=None,
) -> dict:
    """Latest generic strip, changes, slope and spot-reference comparison."""
    code = _family_code(family)
    cfg = POLICY_FUTURES_CONFIG[code]
    readiness = assess_policy_futures_family(
        df, code, min_observations=min_observations, asof=asof
    )
    result = {
        **readiness,
        "family_config": cfg,
        "strip_table": pd.DataFrame(),
        "price_history": pd.DataFrame(),
        "implied_rate_history": pd.DataFrame(),
        "slope_history_bp": pd.Series(dtype=float),
        "front_to_third_bp": None,
        "curve_shape": "Unavailable",
        "spot_reference_rate_pct": None,
        "spot_reference_date": None,
        "front_minus_spot_bp": None,
    }
    if readiness["status"] == "Missing data":
        return result

    prices = build_policy_futures_price_frame(df, code, asof=asof)
    rates = build_policy_futures_implied_rate_frame(df, code, asof=asof)
    if prices.empty or rates.empty:
        return result

    horizons = tuple(dict.fromkeys(int(h) for h in horizons if int(h) > 0))
    rows: list[dict] = []
    tickers = _family_tickers(code)
    for rank in GENERIC_RANKS:
        row = {
            "family": code,
            "family_name": cfg["display_name"],
            "rank": rank,
            "rank_label": {1: "Front generic", 2: "Second generic", 3: "Third generic"}[rank],
            "ticker": tickers[rank],
            "price": float(prices[rank].iloc[-1]),
            "implied_rate_pct": float(rates[rank].iloc[-1]),
            "relative_to_front_bp": float(100.0 * (rates[rank].iloc[-1] - rates[1].iloc[-1])),
            "model_date": rates.index[-1].date(),
        }
        for horizon in horizons:
            row[f"change_{horizon}d_bp"] = _horizon_change_bp(rates[rank], horizon)
        rows.append(row)

    slope = 100.0 * (rates[3] - rates[1])
    latest_slope = float(slope.iloc[-1])
    result.update({
        "strip_table": pd.DataFrame(rows),
        "price_history": prices,
        "implied_rate_history": rates,
        "slope_history_bp": slope,
        "front_to_third_bp": latest_slope,
        "curve_shape": classify_generic_curve(latest_slope, flat_threshold_bp),
    })

    # Compare the front generic with the corresponding current overnight rate
    # only on dates where both observations exist.  This is a descriptive gap,
    # not a meeting-path inference.
    spot_key = cfg.get("spot_reference_key")
    spot_ticker = TICKERS.get(spot_key) if spot_key else None
    if spot_ticker:
        spot_col = str(spot_ticker).upper().strip()
        if spot_col in df.columns:
            spot = pd.to_numeric(df[spot_col], errors="coerce").rename("spot")
            front = rates[1].rename("front")
            pair = pd.concat([front, spot], axis=1).dropna().sort_index()
            asof_ts = _normalise_asof(asof)
            if asof_ts is not None:
                pair = pair.loc[:asof_ts]
            if not pair.empty:
                result["spot_reference_rate_pct"] = float(pair["spot"].iloc[-1])
                result["spot_reference_date"] = pair.index[-1].date()
                result["front_minus_spot_bp"] = float(
                    100.0 * (pair["front"].iloc[-1] - pair["spot"].iloc[-1])
                )
    return result


def build_policy_futures_overview(
    df: pd.DataFrame,
    horizons: Iterable[int] = DEFAULT_HORIZONS,
    asof=None,
) -> pd.DataFrame:
    """Return one row per family/rank for a compact all-family overview."""
    rows: list[dict] = []
    for family in POLICY_FUTURES_CONFIG:
        snap = build_policy_futures_family_snapshot(
            df, family, horizons=horizons, asof=asof
        )
        table = snap.get("strip_table")
        if isinstance(table, pd.DataFrame) and not table.empty:
            for _, row in table.iterrows():
                rec = row.to_dict()
                rec.update({
                    "status": snap["status"],
                    "reference_rate": snap["family_config"]["reference_rate_label"],
                    "reference_period": snap["family_config"]["reference_period"],
                    "front_to_third_bp": snap["front_to_third_bp"],
                    "curve_shape": snap["curve_shape"],
                })
                rows.append(rec)
        else:
            rows.append({
                "family": family,
                "family_name": POLICY_FUTURES_CONFIG[family]["display_name"],
                "rank": None,
                "rank_label": None,
                "ticker": None,
                "price": None,
                "implied_rate_pct": None,
                "relative_to_front_bp": None,
                "model_date": snap.get("model_date"),
                "status": snap.get("status"),
                "reference_rate": POLICY_FUTURES_CONFIG[family]["reference_rate_label"],
                "reference_period": POLICY_FUTURES_CONFIG[family]["reference_period"],
                "front_to_third_bp": None,
                "curve_shape": "Unavailable",
            })
    return pd.DataFrame(rows)


def build_policy_futures_current_reading(
    df: pd.DataFrame,
    family: str,
    change_window: int = 20,
    asof=None,
) -> dict:
    """Structured, descriptive reading for one generic family."""
    code = _family_code(family)
    snap = build_policy_futures_family_snapshot(
        df, code, horizons=(1, 5, int(change_window), 63), asof=asof
    )
    reading = {
        "family": code,
        "display_name": POLICY_FUTURES_CONFIG[code]["display_name"],
        "status": snap.get("status"),
        "model_date": snap.get("model_date"),
        "front_implied_rate_pct": None,
        "third_implied_rate_pct": None,
        "front_change_bp": None,
        "front_to_third_bp": snap.get("front_to_third_bp"),
        "curve_shape": snap.get("curve_shape"),
        "front_minus_spot_bp": snap.get("front_minus_spot_bp"),
        "spot_reference_date": snap.get("spot_reference_date"),
        "summary": "Insufficient data.",
        "limitations": (
            "Generic ranks roll across underlying contracts and are not fixed expiries. "
            "This monitor does not infer FOMC outcomes, meeting probabilities, or an "
            "expiry-mapped forward curve."
        ),
    }
    table = snap.get("strip_table")
    if not isinstance(table, pd.DataFrame) or table.empty:
        return reading

    front = table.loc[table["rank"] == 1].iloc[0]
    third = table.loc[table["rank"] == 3].iloc[0]
    change_col = f"change_{int(change_window)}d_bp"
    reading.update({
        "front_implied_rate_pct": float(front["implied_rate_pct"]),
        "third_implied_rate_pct": float(third["implied_rate_pct"]),
        "front_change_bp": (
            None if pd.isna(front.get(change_col)) else float(front.get(change_col))
        ),
    })
    front_change_text = (
        "unavailable" if reading["front_change_bp"] is None
        else f"{reading['front_change_bp']:+.1f} bp over {int(change_window)} observations"
    )
    reading["summary"] = (
        f"{reading['display_name']} front generic implies "
        f"{reading['front_implied_rate_pct']:.3f}% as of {reading['model_date']}. "
        f"The third generic is {reading['front_to_third_bp']:+.1f} bp versus the front "
        f"({reading['curve_shape']}); the front implied rate changed {front_change_text}."
    )
    return reading
