"""
data/date_integrity.py
======================
Production-date integrity: split market data into eligible and future rows.
Future rows are preserved but excluded from production analytics.
"""
from __future__ import annotations
import datetime
import pandas as pd


def current_production_date(current_date=None,
                            timezone: str = "Asia/Singapore") -> datetime.date:
    """Return the current production date in the requested timezone.

    If current_date is supplied, normalize it to datetime.date.
    Otherwise use the timezone-aware local date.
    """
    if current_date is not None:
        if isinstance(current_date, datetime.datetime):
            return current_date.date()
        if isinstance(current_date, datetime.date):
            return current_date
        return pd.Timestamp(current_date).date()
    try:
        from zoneinfo import ZoneInfo
        return datetime.datetime.now(ZoneInfo(timezone)).date()
    except Exception:
        return datetime.date.today()


def split_market_data_by_asof(df: pd.DataFrame, current_date=None,
                               timezone: str = "Asia/Singapore") -> dict:
    """Split a DatetimeIndex DataFrame into eligible and future rows.

    Returns dict with eligible frame, future frame, and metadata.
    Future rows are NOT deleted — they are preserved for audit.
    """
    cd = current_production_date(current_date, timezone)

    eligible_mask = df.index.date <= cd
    eligible = df[eligible_mask]
    future = df[~eligible_mask]

    future_detail = {}
    for d in future.index:
        dd = d.date()
        n = int(future.loc[d].notna().sum())
        future_detail[str(dd)] = n

    return {
        "eligible": eligible,
        "future": future,
        "production_asof": eligible.index.max().date() if len(eligible) else None,
        "current_date": cd,
        "future_dates": sorted(future_detail.keys()),
        "future_row_count": len(future),
        "future_non_null_by_date": future_detail,
    }
