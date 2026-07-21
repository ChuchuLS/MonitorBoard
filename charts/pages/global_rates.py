"""
charts/pages/global_rates.py
============================
Section 04 — Global Rates. Scaffold page in Phase 1.

Enumerates the countries with complete curve coverage in the current dataset
and lists the intended models. No cross-country model is fabricated: countries
without complete 2Y/5Y/10Y/30Y data are excluded honestly rather than filled
with proxies.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from config.pages import get_page
from config.tickers import TICKERS, REGIME_COUNTRIES

from charts.common import (
    render_page_header, render_top_tabs,
    render_explanation_box, render_missing_data_warning, render_section_footer,
)
from data.loader import get_series

from ._context import PageContext


ALL_G10 = ["US", "DE", "JP", "UK", "CA", "AU", "CH", "FR", "IT", "NZ"]
STANDARD_TENORS = ["2Y", "5Y", "10Y", "30Y"]


def render(ctx: PageContext) -> None:
    page = get_page("global_rates")

    render_top_tabs(page["id"])
    latest = ctx.df.index.max().strftime("%b %d, %Y").upper()
    render_page_header(page, latest_date=latest)

    render_explanation_box(
        "Intended models",
        "Three global-rates outputs are planned: <b>Global 10Y overlay</b> "
        "(all covered countries on one chart to spot dislocations), "
        "<b>Global yield-curve snapshot</b> (front-end vs long-end today), "
        "and <b>2s10s slope ranking</b> across countries. All three are built "
        "on the countries with complete curve data — no partial coverage is "
        "filled with proxies.",
    )

    # -------- Country coverage table --------
    st.markdown(
        "<div style='margin:0.8rem 0 0.4rem;font-size:11px;color:#888;"
        "letter-spacing:0.1em;text-transform:uppercase;'>"
        "Country coverage on the current dataset</div>",
        unsafe_allow_html=True,
    )
    rows = []
    for c in ALL_G10:
        row = {"Country": c}
        n_covered = 0
        for t in STANDARD_TENORS:
            key = f"{c}_{t}"
            ok = key in TICKERS and len(get_series(ctx.df, key).dropna()) > 0
            row[t] = "✓" if ok else "—"
            if ok:
                n_covered += 1
        row["Complete curve"] = "✓" if n_covered == len(STANDARD_TENORS) else "—"
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    complete = [c for c in ALL_G10 if all(
        f"{c}_{t}" in TICKERS
        and len(get_series(ctx.df, f"{c}_{t}").dropna()) > 0
        for t in STANDARD_TENORS
    )]
    incomplete = [c for c in ALL_G10 if c not in complete]

    render_missing_data_warning(
        required=[f"{c} 2Y/5Y/10Y/30Y" for c in ALL_G10],
        available=[f"{c} full curve" for c in complete],
        missing=[f"{c} full curve" for c in incomplete],
        message=(
            "The intended country set covers all G10. Countries without "
            "complete <b>2Y/5Y/10Y/30Y</b> nominal yield coverage will be "
            "omitted from the global overlays until the missing tenors "
            "are added to DATA.xlsx."
        ),
    )

    render_section_footer(page)
