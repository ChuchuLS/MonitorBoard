"""Loader for the fixed-contract SOFR futures sheet in DATA.xlsx.

The ``Policy_Futures`` worksheet stores each Bloomberg BQL result as an
independent Date + Price pair.  This loader preserves those individual source
calendars, joins by the actual Date values, and never aligns by row position.
"""
from __future__ import annotations

from functools import lru_cache

import pandas as pd

from data.date_integrity import current_production_date
from data.loader import EXCEL_PATH, source_signature

try:
    import streamlit as st
    _HAS_ST = True
except Exception:  # pragma: no cover
    _HAS_ST = False


def _coerce_excel_dates(values: pd.Series) -> pd.Series:
    """Convert Excel datetimes or serial-day values without guessing shifts."""
    if pd.api.types.is_datetime64_any_dtype(values):
        return pd.to_datetime(values, errors="coerce")
    out = pd.Series(pd.NaT, index=values.index, dtype="datetime64[ns]")
    # Handle actual datetime objects before numeric coercion; pandas represents
    # datetimes internally as integers, which must never be mistaken for Excel days.
    datetime_mask = values.map(lambda v: isinstance(v, (pd.Timestamp, __import__('datetime').datetime, __import__('datetime').date)))
    if datetime_mask.any():
        out.loc[datetime_mask] = pd.to_datetime(values.loc[datetime_mask], errors="coerce")
    remaining = ~datetime_mask
    numeric = pd.to_numeric(values.loc[remaining], errors="coerce")
    num_mask = numeric.notna()
    if num_mask.any():
        out.loc[numeric.index[num_mask]] = pd.to_datetime(
            numeric.loc[num_mask], unit="D", origin="1899-12-30", errors="coerce"
        )
    text_idx = numeric.index[~num_mask]
    if len(text_idx):
        out.loc[text_idx] = pd.to_datetime(values.loc[text_idx], errors="coerce")
    return out


def _read_policy_futures_sheet() -> pd.DataFrame:
    raw = pd.read_excel(EXCEL_PATH, sheet_name="Policy_Futures", header=None)
    if raw.empty or raw.shape[1] < 2:
        return pd.DataFrame()

    series_list: list[pd.Series] = []
    # Each pair is [Date column, Price column], with the ticker in row 1 of the
    # price column.  Retain each pair's own Date output and join on Date.
    for date_col in range(0, raw.shape[1] - 1, 2):
        price_col = date_col + 1
        ticker = raw.iloc[0, price_col]
        if pd.isna(ticker):
            continue
        ticker = str(ticker).upper().strip()
        dates = _coerce_excel_dates(raw.iloc[1:, date_col])
        prices = pd.to_numeric(raw.iloc[1:, price_col], errors="coerce")
        s = pd.Series(prices.to_numpy(), index=pd.DatetimeIndex(dates), name=ticker)
        s = s[s.index.notna()].dropna().sort_index()
        s = s[~s.index.duplicated(keep="last")]
        if not s.empty:
            series_list.append(s)

    if not series_list:
        return pd.DataFrame()
    out = pd.concat(series_list, axis=1).sort_index()
    out.columns = [str(c).upper().strip() for c in out.columns]
    return out


if _HAS_ST:
    @st.cache_data(show_spinner=False)
    def _load_policy_futures_cached(
        source_hash: str,
        production_date: str,
        include_future: bool,
    ) -> pd.DataFrame:
        frame = _read_policy_futures_sheet()
        if not include_future and not frame.empty:
            cutoff = pd.Timestamp(production_date)
            frame = frame.loc[frame.index <= cutoff]
        return frame
else:  # pragma: no cover
    @lru_cache(maxsize=8)
    def _load_policy_futures_cached(
        source_hash: str,
        production_date: str,
        include_future: bool,
    ) -> pd.DataFrame:
        frame = _read_policy_futures_sheet()
        if not include_future and not frame.empty:
            cutoff = pd.Timestamp(production_date)
            frame = frame.loc[frame.index <= cutoff]
        return frame


def load_policy_futures(
    include_future: bool = False,
    current_date=None,
) -> pd.DataFrame:
    """Load fixed SFR contracts, filtered to the Singapore production date."""
    production_date = current_production_date(current_date=current_date).isoformat()
    return _load_policy_futures_cached(
        source_signature(), production_date, bool(include_future)
    ).copy()
