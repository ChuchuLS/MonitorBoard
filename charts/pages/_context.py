"""
charts/pages/_context.py — shared context object for all page renderers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import pandas as pd


@dataclass
class PageContext:
    """Everything a page renderer needs from the app."""
    df: pd.DataFrame
    dff: pd.DataFrame
    start_date: pd.Timestamp
    end_date: pd.Timestamp

    index_result: object               # index.composite.IndexResult
    audit_bundle: dict

    # Lazy export: a callable that returns bytes only when invoked.
    # None if export is not available. The Liquidity page calls this
    # only when the user interacts with the export section.
    export_builder: Callable[[], bytes] | None = None
    export_name: str = "liquidity_index.xlsx"

    # Complete reference-style Board export. This is separate from the
    # Liquidity page's analytical Excel workbook above.
    pdf_export_builder: Callable[[], bytes] | None = None
    pdf_export_name: str = "rates_liquidity_board.pdf"

    extras: dict = field(default_factory=dict)
