"""
charts/pages/liquidity_overview.py
==================================
Section 00 — Liquidity Overview. Wraps the existing render_index_page /
render_summary_panel (untouched) inside the new PDF-style shell.

The Composite Liquidity Index computation is NOT modified in Phase 1. This
module only adds the header, KPI strip, explanation box and footer around it.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

from config.pages import get_page
from config.theme import section_color, REGIME_COLORS

from charts.common import (
    render_page_header, render_top_tabs, render_kpi_strip,
    render_explanation_box, render_section_footer,
)
from charts.liquidity import render_summary_panel, render_index_page

from ._context import PageContext


def render(ctx: PageContext) -> None:
    page = get_page("liquidity")
    color = section_color(page["color_key"])

    render_top_tabs(page["id"])
    latest = ctx.df.index.max().strftime("%b %d, %Y").upper()
    viewing = (f"{ctx.start_date.strftime('%b %Y').upper()} → "
               f"{ctx.end_date.strftime('%b %Y').upper()}")
    render_page_header(page, latest_date=latest, viewing=viewing)

    r = ctx.index_result
    regime = getattr(r, "latest_regime", "—")
    regime_color = REGIME_COLORS.get(regime, "#9aa0a6")

    def _fmt_change(v, unit="pts"):
        if v is None or pd.isna(v):
            return "—"
        return f"{v:+.1f} {unit}"

    changes = r.changes() if callable(getattr(r, "changes", None)) else {}
    kpi_cards = [
        {"label": "Composite Liquidity Index",
         "value": f"{r.latest:.1f}" if pd.notna(r.latest) else "—",
         "sub": f"50 = neutral · regime <b style='color:{regime_color}'>{regime}</b>",
         "accent": color},
        {"label": "1-week change",
         "value": _fmt_change(changes.get("1w")),
         "sub": "vs 5 business days ago"},
        {"label": "1-month change",
         "value": _fmt_change(changes.get("1m")),
         "sub": "vs 21 business days ago"},
        {"label": "3-month change",
         "value": _fmt_change(changes.get("3m")),
         "sub": "vs 63 business days ago"},
    ]
    render_kpi_strip(kpi_cards)

    render_explanation_box(
        "What this section shows",
        "A raw-indicator liquidity gauge, z-scored across five buckets "
        "(money-market funding, dollar funding, credit, central-bank reserves, "
        "market liquidity) and rescaled so <b>50 = neutral</b> and higher = "
        "looser. The panels below decompose today's reading into bucket and "
        "component contributions, benchmark it against Bloomberg FCI and the "
        "Chicago Fed NFCI, and expose the full methodology audit trail. "
        "The <b>Export to Excel</b> button ships a multi-sheet workbook of "
        "index, buckets, components, contributions, reconciliation, "
        "forward-fill audit and methodology parameters.",
    )

    # Build export bytes lazily — only if the user is on this page.
    export_bytes = ctx.export_builder() if ctx.export_builder else None

    # Delegate the actual heavy panel to the existing renderer — untouched.
    render_summary_panel(r)
    st.markdown("<div style='height:0.8rem;'></div>", unsafe_allow_html=True)
    render_index_page(
        ctx.df, ctx.dff, r, ctx.audit_bundle,
        export_bytes=export_bytes,
        export_name=ctx.export_name,
    )

    render_section_footer(page)
