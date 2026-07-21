"""
charts/pages/regimes.py
=======================
Section 03 — Curve Regimes. Scaffold page in Phase 1.

Explains the six-regime classification (bull / bear × steepener / flattener /
twist), lists the tenor pairs actually buildable from the current data, and
notes explicitly that 1Y-based pairs are NOT built because the underlying
1Y series is not in the dataset. Surfaces the existing slope/regime panel as
a preview so the material is still one click away.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from config.pages import get_page
from config.theme import section_color, CURVE_REGIME_COLORS, CURVE_REGIME_LABELS
from config.tickers import TICKERS, TENOR_PAIRS, REGIME_COUNTRIES

from charts.common import (
    render_page_header, render_top_tabs,
    render_explanation_box, render_missing_data_warning, render_section_footer,
)
from charts.rates import classify_regime, big_regime_panel
from data.loader import get_series

from ._context import PageContext


def render(ctx: PageContext) -> None:
    page = get_page("regimes")

    render_top_tabs(page["id"])
    latest = ctx.df.index.max().strftime("%b %d, %Y").upper()
    render_page_header(page, latest_date=latest)

    render_explanation_box(
        "The classification",
        "Every curve day is one of six regimes, defined by the sign of the "
        "long-tenor move and the sign of the slope change. "
        "<b>Bull</b> means the long end rallied (yields fell); <b>bear</b> "
        "the long end sold off. <b>Steepener</b> means the curve got steeper; "
        "<b>flattener</b> means it flattened. <b>Twist</b> flags where both "
        "ends moved in opposite directions. The full research-pack build will "
        "output a regime × tenor-pair × country matrix; this scaffold uses "
        "whatever pairs the current dataset supports.",
    )

    # Regime chip legend (matches the existing colour system, unchanged).
    chips = " &nbsp;&nbsp; ".join(
        f"<span style='display:inline-block;width:11px;height:11px;"
        f"background:{CURVE_REGIME_COLORS[k]};vertical-align:middle;"
        f"margin-right:5px;'></span>"
        f"<span style='color:#bbb;font-size:10px;letter-spacing:0.05em;"
        f"text-transform:uppercase;'>{CURVE_REGIME_LABELS[k]}</span>"
        for k in ["bull_steepener", "bear_steepener", "steepener_twist",
                  "bull_flattener", "bear_flattener", "flattener_twist"]
    )
    st.markdown(f"<div style='padding:0.6rem 0 0.4rem;'>{chips}</div>",
                unsafe_allow_html=True)

    # -------- Tenor pair availability across countries --------
    st.markdown(
        "<div style='margin:0.6rem 0 0.4rem;font-size:11px;color:#888;"
        "letter-spacing:0.1em;text-transform:uppercase;'>"
        "Available tenor pairs by country</div>",
        unsafe_allow_html=True,
    )
    rows = []
    for country in REGIME_COUNTRIES:
        row: dict = {"Country": country}
        for pair_name, (a, b) in TENOR_PAIRS.items():
            ka, kb = f"{country}_{a}", f"{country}_{b}"
            ok = (ka in TICKERS and kb in TICKERS
                  and len(get_series(ctx.df, ka).dropna())
                  and len(get_series(ctx.df, kb).dropna()))
            row[pair_name] = "✓" if ok else "—"
        rows.append(row)
    st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    render_missing_data_warning(
        required=[
            "Nominal yields for at least two tenors per country",
            "1Y nominal yields (for full PDF-reference 10-pair matrix)",
        ],
        available=[
            "2Y / 5Y / 10Y / 30Y across US, DE, JP, UK, CA, AU",
            "Six spread pairs — 2s5s, 2s10s, 2s30s, 5s10s, 5s30s, 10s30s",
        ],
        missing=[
            "1Y nominal yields for every country",
            "1s2s, 1s5s, 1s10s, 1s30s, 1s5s pairs",
        ],
        message=(
            "The Capital Flows-style reference uses <b>ten</b> spread pairs "
            "including 1Y-based ones. This dashboard will build the "
            "<b>six 2Y-plus pairs</b> unless 1Y series are added to "
            "DATA.xlsx. No fake 1Y series will be synthesised."
        ),
    )

    # -------- Preview: existing regime panel --------
    st.markdown(
        "<div style='margin:1.3rem 0 0.4rem;font-size:11px;color:#888;"
        "letter-spacing:0.1em;text-transform:uppercase;'>"
        "Preview · single-pair regime panel (carried over)</div>",
        unsafe_allow_html=True,
    )
    st.caption(
        "The existing single-pair regime classifier remains available while "
        "the full multi-pair regime matrix is being built.")

    cols = st.columns([1, 1, 1, 3])
    with cols[0]:
        country = st.selectbox("COUNTRY", options=list(REGIME_COUNTRIES),
                               index=0, key="regimes_country")
    with cols[1]:
        pair = st.selectbox("TENOR PAIR", options=list(TENOR_PAIRS.keys()),
                            index=0, key="regimes_pair")
    with cols[2]:
        lb_choice = st.selectbox("LOOKBACK",
                                 options=["5d", "10d", "20d", "60d", "120d"],
                                 index=2, key="regimes_lookback")
    lookback = int(lb_choice.rstrip("d"))
    short_t, long_t = TENOR_PAIRS[pair]
    short = get_series(ctx.dff, f"{country}_{short_t}")
    long_ = get_series(ctx.dff, f"{country}_{long_t}")
    if len(short) == 0 or len(long_) == 0:
        st.warning(f"No data for {country} {short_t}/{long_t}. "
                   "Try a different pair or country.")
    else:
        slope, regime = classify_regime(short, long_, lookback)
        st.plotly_chart(
            big_regime_panel(slope, regime,
                             f"{country} {pair} (regime vs {lookback}d ago)"),
            use_container_width=True, key="regimes_slope",
            config={"displayModeBar": False})

    render_section_footer(page)
