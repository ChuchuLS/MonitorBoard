"""Calendar-integrity audits for merged market-data groups.

Pure functions only. These audits never shift, fill, or relabel observations.
They report the dates that actually exist in DATA.xlsx.
"""
from __future__ import annotations

from collections import OrderedDict
import numpy as np
import pandas as pd

from config.tickers import SPX_SECTOR_CONFIG

WEEKDAY_NAMES = [
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"
]
EXPECTED_BUSINESS_WEEKDAYS = {0, 1, 2, 3, 4}


def _resolve_columns(df: pd.DataFrame, tickers) -> list[str]:
    lookup = {str(c).upper().strip(): c for c in df.columns}
    return [lookup[t.upper().strip()] for t in tickers if t.upper().strip() in lookup]



def audit_series_calendar(
    series: pd.Series,
    expected_weekdays=EXPECTED_BUSINESS_WEEKDAYS,
    allow_weekends: bool = False,
) -> dict:
    """Audit a single series without changing its dates or values."""
    frame = pd.DataFrame({"series": pd.to_numeric(series, errors="coerce")})
    result = audit_ticker_group_calendar(
        frame, ["series"], getattr(series, "name", None) or "series",
        expected_weekdays=expected_weekdays,
    )
    if allow_weekends and result["unexpected_weekdays"]:
        result["status"] = "Ready"
    return result

def audit_ticker_group_calendar(
    df: pd.DataFrame,
    tickers,
    group_name: str,
    expected_weekdays=EXPECTED_BUSINESS_WEEKDAYS,
) -> dict:
    """Audit dates where any requested ticker has a valid observation."""
    cols = _resolve_columns(df, tickers)
    if not cols:
        return {
            "group": group_name,
            "requested_tickers": list(tickers),
            "available_tickers": [],
            "missing_tickers": list(tickers),
            "first_date": None,
            "latest_date": None,
            "observation_count": 0,
            "weekday_counts": {name: 0 for name in WEEKDAY_NAMES},
            "weekend_observation_count": 0,
            "unexpected_weekdays": [],
            "status": "Missing data",
        }
    valid = df[cols].notna().any(axis=1)
    dates = pd.DatetimeIndex(df.index[valid])
    counts = dates.day_name().value_counts().reindex(WEEKDAY_NAMES, fill_value=0)
    observed_weekdays = set(dates.weekday)
    unexpected = sorted(observed_weekdays - set(expected_weekdays))
    missing_tickers = [t for t in tickers if t.upper().strip() not in {str(c).upper().strip() for c in df.columns}]
    status = "Ready"
    if unexpected:
        status = "Needs date verification"
    elif missing_tickers:
        status = "Partial"
    return {
        "group": group_name,
        "requested_tickers": list(tickers),
        "available_tickers": cols,
        "missing_tickers": missing_tickers,
        "first_date": dates.min().date() if len(dates) else None,
        "latest_date": dates.max().date() if len(dates) else None,
        "observation_count": int(len(dates)),
        "weekday_counts": {name: int(counts[name]) for name in WEEKDAY_NAMES},
        "weekend_observation_count": int(counts["Saturday"] + counts["Sunday"]),
        "unexpected_weekdays": [WEEKDAY_NAMES[i] for i in unexpected],
        "status": status,
    }


def audit_sector_calendar(df: pd.DataFrame) -> dict:
    return audit_ticker_group_calendar(
        df,
        [cfg["ticker"] for cfg in SPX_SECTOR_CONFIG.values()],
        "S&P 500 sector indices",
    )


def audit_parent_sector_return_range(df: pd.DataFrame, horizons=(1, 5, 20, 63), asof=None) -> pd.DataFrame:
    """Necessary parent/sector range check using identical timestamps.

    For a float-weighted parent index composed of the sectors, the parent return
    should lie within the minimum and maximum sector returns over an identical
    interval. A failure is an investigation flag, not proof of a specific fix.
    """
    from models.sector_rotation import build_sector_relative_frame

    aligned = build_sector_relative_frame(df, asof=asof)
    if aligned.empty or "spx" not in aligned.columns:
        return pd.DataFrame()
    rows = []
    for horizon in horizons:
        if len(aligned) <= horizon:
            continue
        start = aligned.iloc[-horizon - 1]
        end = aligned.iloc[-1]
        arithmetic = 100 * (end / start - 1)
        sectors = arithmetic.drop(labels=["spx"], errors="ignore").dropna()
        if sectors.empty or pd.isna(arithmetic.get("spx")):
            continue
        spx_ret = float(arithmetic["spx"])
        minimum = float(sectors.min())
        maximum = float(sectors.max())
        rows.append({
            "horizon": int(horizon),
            "start_date": aligned.index[-horizon - 1].date(),
            "end_date": aligned.index[-1].date(),
            "spx_return_pct": spx_ret,
            "min_sector_return_pct": minimum,
            "max_sector_return_pct": maximum,
            "sectors_above_spx": int((sectors > spx_ret).sum()),
            "sectors_below_spx": int((sectors < spx_ret).sum()),
            "sector_count": int(len(sectors)),
            "range_test_passed": bool(minimum - 1e-12 <= spx_ret <= maximum + 1e-12),
        })
    return pd.DataFrame(rows)
