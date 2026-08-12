"""Pure cross-currency basis snapshot helpers.

The module contains no Streamlit dependency. It reports each 3M and 12M
series on its own latest valid observation date and never fills missing data.
"""
from __future__ import annotations

import pandas as pd

from data.loader import get_series

XCCY_CURRENCIES = (("EUR", "EUR"), ("JPY", "JPY"),
                   ("AUD", "AUD"), ("GBP", "GBP"),
                   ("CAD", "CAD"))


def build_xccy_snapshot(dff: pd.DataFrame) -> pd.DataFrame:
    """Return latest 3M/12M XCCY basis observations without filling gaps."""
    rows: list[dict] = []
    for ccy, label in XCCY_CURRENCIES:
        s3 = get_series(dff, f"XCCY_{ccy}")
        s12 = get_series(dff, f"XCCY12_{ccy}")
        has3, has12 = bool(len(s3)), bool(len(s12))
        status = "Ready" if has3 and has12 else ("Partial" if has3 or has12 else "Missing data")
        rows.append({
            "Currency": label,
            "3M basis (bp)": float(s3.iloc[-1]) if has3 else None,
            "3M date": s3.index[-1].date() if has3 else None,
            "12M basis (bp)": float(s12.iloc[-1]) if has12 else None,
            "12M date": s12.index[-1].date() if has12 else None,
            "Status": status,
        })
    return pd.DataFrame(rows)
