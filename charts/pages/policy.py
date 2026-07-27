"""
charts/pages/policy.py
======================
Section 01 — Policy & Short Rates. Wraps the existing money-market plumbing
renderer and states plainly what is NOT here (FOMC path, SOFR futures strip)
so the reader is never left guessing whether a chart is real or missing.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from config.pages import get_page
from config.theme import section_color
from config.tickers import TICKERS

from charts.common import (
    render_page_header, render_top_tabs, render_kpi_strip,
    render_explanation_box, render_missing_data_warning, render_section_footer,
)
from charts.funding import render_money_market
from data.loader import get_series

from ._context import PageContext


# Rate keys we'd like to summarise at the top of the page.
_KEY_RATES = [
    ("EFFR",  "Effective FFR"),
    ("SOFR",  "SOFR"),
    ("IORB",  "IORB"),
]


def _latest(dff: pd.DataFrame, key: str) -> float | None:
    s = get_series(dff, key).dropna()
    if not len(s):
        return None
    return float(s.iloc[-1])


def render(ctx: PageContext) -> None:
    page = get_page("policy")
    color = section_color(page["color_key"])

    render_top_tabs(page["id"])
    latest = ctx.df.index.max().strftime("%b %d, %Y").upper()
    viewing = (f"{ctx.start_date.strftime('%b %Y').upper()} → "
               f"{ctx.end_date.strftime('%b %Y').upper()}")
    render_page_header(page, latest_date=latest, viewing=viewing)

    # KPI strip — spot short rates on the latest day of the viewing window.
    def _pct(x): return "—" if x is None else f"{x:.3f}%"
    effr = _latest(ctx.dff, "EFFR")
    sofr = _latest(ctx.dff, "SOFR")
    iorb = _latest(ctx.dff, "IORB")
    sofr_iorb = None if (sofr is None or iorb is None) else (sofr - iorb) * 100
    effr_iorb = None if (effr is None or iorb is None) else (effr - iorb) * 100

    render_kpi_strip([
        {"label": "SOFR", "value": _pct(sofr),
         "sub": "Secured overnight financing rate", "accent": color},
        {"label": "EFFR", "value": _pct(effr),
         "sub": "Effective federal funds rate"},
        {"label": "IORB", "value": _pct(iorb),
         "sub": "Interest on reserve balances"},
        {"label": "SOFR − IORB",
         "value": "—" if sofr_iorb is None else f"{sofr_iorb:+.1f} bp",
         "sub": "Funding pressure vs Fed floor"},
        {"label": "EFFR − IORB",
         "value": "—" if effr_iorb is None else f"{effr_iorb:+.1f} bp",
         "sub": "Fed funds vs reserve rate"},
    ])

    render_explanation_box(
        "What this section shows",
        "The plumbing of the policy short rate — where cash actually trades "
        "relative to the Fed's floor. Rising <b>SOFR − IORB</b> or a positive "
        "<b>EFFR − IORB</b> both signal money-market funding pressure "
        "(reserves getting scarce, dealer balance sheets stretched, or "
        "quarter-end effects). Reserve balances and Fed repo / SRF-style "
        "usage give the balance-sheet backdrop when available. "
        "Unconfirmed RRP-related candidate series are excluded until confirmed.",
    )

    # Honest scope statement — no fake FOMC path or SOFR futures strip.
    have_effr = "EFFR" in TICKERS and _latest(ctx.dff, "EFFR") is not None
    have_sofr = "SOFR" in TICKERS and _latest(ctx.dff, "SOFR") is not None
    have_iorb = "IORB" in TICKERS and _latest(ctx.dff, "IORB") is not None
    have_reserves = _latest(ctx.dff, "FED_RESERVES") is not None
    have_repo = _latest(ctx.dff, "FED_REPO") is not None

    available = []
    if have_sofr: available.append("SOFR")
    if have_effr: available.append("EFFR")
    if have_iorb: available.append("IORB")
    if have_reserves: available.append("Fed reserves (weekly)")
    if have_repo: available.append("Fed repo / SRF usage (weekly)")

    render_missing_data_warning(
        required=[
            "Fed funds futures (meeting-dated)",
            "SOFR futures (contract-level)",
            "FOMC meeting calendar",
        ],
        available=available,
        missing=[
            "Fed funds futures",
            "SOFR futures strip",
            "Meeting-dated FOMC probabilities",
        ],
        message=(
            "<b>FOMC path and SOFR futures strip are intentionally not shown.</b> "
            "Both require meeting-dated futures contract data that is not in "
            "the current dataset. This page uses spot short-rate and funding "
            "indicators only — no fabricated probabilities, no synthetic strips."
        ),
    )

    # Existing money-market rendering uses confirmed SOFR/EFFR/IORB/repo-rate series only. RRP candidates are excluded until confirmed.
    st.markdown("<div style='height:0.8rem;'></div>", unsafe_allow_html=True)
    render_money_market(ctx.dff)

    render_section_footer(page)
