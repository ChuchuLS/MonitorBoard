"""
charts/pages/decomposition.py
=============================
Section 02 — Rate Decomposition. SCAFFOLD page.

The true decomposition engine (nominal = real + inflation, identity form via
TIPS breakevens) is NOT yet built. This page explains the intended framework,
runs a data-availability check, and provides inflation-curve previews.

The within-rates PCA model that was briefly shown here has been moved to
Section 02b (Rates Complex PCA) where it is honestly labelled as experimental.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from config.pages import get_page
from config.tickers import TICKERS, INFL_BE_TENORS, INFL_ZCIS_TENORS

from charts.common import (
    render_page_header, render_top_tabs,
    render_explanation_box, render_model_note, render_missing_data_warning,
    render_section_footer,
)
from charts.rates import big_curve_panel
from data.loader import get_series

from ._context import PageContext

TENORS = ["2Y", "5Y", "10Y", "30Y"]


def _has_data(df, key):
    return key in TICKERS and len(get_series(df, key).dropna()) > 0


def render(ctx: PageContext) -> None:
    page = get_page("decomposition")

    render_top_tabs(page["id"])
    latest = ctx.df.index.max().strftime("%b %d, %Y").upper()
    render_page_header(page, latest_date=latest,
                       viewing="Data source: DATA.xlsx")

    render_explanation_box(
        "Intended framework",
        "Decompose nominal yield moves into a real-rate leg and an inflation "
        "leg. Two flavours: <b>identity form</b> (nominal ≡ real + breakeven, "
        "from TIPS) and <b>swap form</b> (nominal ≈ real + inflation swap, "
        "which carries a residual). Planned outputs: US Curve Complex, "
        "2Y / 10Y Rate Attribution, 2s10s Curve Decomposition.",
    )

    render_model_note(
        "Methodology note — identity vs residual",
        "Using <b>TIPS breakevens</b>, <code>nominal = real + inflation</code> "
        "is an exact identity. Using <b>inflation swaps (ZCIS)</b>, the identity "
        "does NOT hold exactly — a residual exists. This scaffold will not "
        "conflate the two. The within-rates <b>PCA model</b> is on the next "
        "page (02b · Rates Complex PCA) and is a separate, experimental analysis.",
    )

    # Data availability check
    st.markdown("<div style='margin:1.2rem 0 0.4rem;font-size:11px;color:#888;"
                "letter-spacing:0.1em;text-transform:uppercase;'>"
                "Data availability check</div>", unsafe_allow_html=True)
    rows = []
    for t in TENORS:
        nk, bk, zk = f"US_{t}", f"BE_{t}", f"ZCIS_{t}"
        nom_ok = _has_data(ctx.df, nk)
        be_ok = bk in TICKERS and _has_data(ctx.df, bk)
        zc_ok = zk in TICKERS and _has_data(ctx.df, zk)
        rows.append({"Tenor": t, "Nominal yield": "✓" if nom_ok else "—",
                      "TIPS breakeven": "✓" if be_ok else "—",
                      "Inflation swap (ZCIS)": "✓" if zc_ok else "—",
                      "Real yield (derived)": "✓" if nom_ok and (be_ok or zc_ok) else "—"})
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    render_missing_data_warning(
        required=["US nominal yields (2Y/5Y/10Y/30Y)",
                  "TIPS breakevens OR inflation swaps for the same tenors"],
        available=["US nominal yields 2Y/5Y/10Y/30Y",
                   "US TIPS breakevens 2Y/5Y/10Y/20Y/30Y",
                   "US ZC inflation swaps 1Y–30Y"],
        missing=["— all inputs present; the decomposition engine is the build-next item"],
        message="The identity-form decomposition is fully feasible on "
                "current data. The engine will be built in a future phase.",
    )

    # Inflation curve previews
    st.markdown("<div style='margin:1.3rem 0 0.4rem;font-size:11px;color:#888;"
                "letter-spacing:0.1em;text-transform:uppercase;'>"
                "Inflation-expectation curves (preview)</div>", unsafe_allow_html=True)
    anchor = ctx.dff.index.max() if len(ctx.dff) else ctx.df.index.max()
    tab_be, tab_zc = st.tabs(["TIPS breakeven curve", "USD ZC inflation swap curve"])
    with tab_be:
        st.plotly_chart(
            big_curve_panel(ctx.df, "US TIPS breakeven curve",
                            INFL_BE_TENORS, anchor, y_title="Breakeven (%)"),
            use_container_width=True, key="dec_be", config={"displayModeBar": False})
    with tab_zc:
        st.plotly_chart(
            big_curve_panel(ctx.df, "USD ZC inflation swap curve",
                            INFL_ZCIS_TENORS, anchor, y_title="Inflation swap (%)"),
            use_container_width=True, key="dec_zc", config={"displayModeBar": False})

    render_section_footer(page)
