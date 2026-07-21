"""
charts/pages/contents.py
========================
The Contents landing page. Shows every section from the PAGES registry with a
short description and a status pill (Live / Partial / Scaffold / Requires data),
mirroring the front-matter contents page of an institutional research pack.
"""

from __future__ import annotations

import html as _html

import streamlit as st

from config.pages import PAGES, STATUS_LABELS, STATUS_COLORS
from config.theme import section_color

from ._context import PageContext


CONTENTS_PAGE_META = {
    "id": "contents",
    "section": "—",
    "title": "Contents",
    "color_key": "data_quality",
    "description": "Daily macro / liquidity research pack. Sections listed below "
                   "in reading order. Status marks which pages are fully live, "
                   "which are structural scaffolds, and which still require "
                   "additional Bloomberg data before they can be populated.",
    "builds_on": None,
    "next": "liquidity",
}


def render(ctx: PageContext) -> None:
    from charts.common import (
        render_page_header, render_top_tabs, render_section_footer
    )

    render_top_tabs("contents")
    latest = ctx.df.index.max().strftime("%b %d, %Y").upper()
    render_page_header(CONTENTS_PAGE_META, latest_date=latest)

    # Intro / how-to-read block
    st.markdown(
        f"""
        <div class="rp-box rp-box-explain">
          <div class="rp-box-label">About this pack</div>
          <div class="rp-box-body">
            The <b>Composite Liquidity Index</b> (Section 00) is the anchor
            model of the pack — a coverage-gated rolling z-score composite
            built on money-market funding, dollar funding, credit, central-bank
            reserves and market liquidity. Sections 01–07 are the surrounding
            research chapters. Each page carries its own accent colour so the
            sidebar, top-tabs and header stay in sync; the footer links tell
            you what a page <i>builds on</i> and where to go next.
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Contents list — one row per section
    rows_html = []
    for p in PAGES:
        color = section_color(p["color_key"])
        status = p["status"]
        status_label = STATUS_LABELS[status]
        status_color = STATUS_COLORS[status]
        title = _html.escape(p["title"])
        desc = _html.escape(p["description"])
        num = _html.escape(p["section"])
        rows_html.append(
            f"""
            <div style="display:grid;grid-template-columns:52px 1fr 140px;
                        gap:14px;padding:10px 12px;border:1px solid #1a1a1a;
                        border-left:3px solid {color};border-radius:4px;
                        margin-bottom:8px;background:#0d0d0d;align-items:baseline;">
              <div style="font-size:20px;font-weight:700;color:{color};
                          letter-spacing:0.04em;">{num}</div>
              <div>
                <div style="font-size:14px;font-weight:700;color:#fff;
                            letter-spacing:0.03em;">{title}</div>
                <div style="font-size:11.5px;color:#aaa;margin-top:3px;
                            line-height:1.5;">{desc}</div>
              </div>
              <div style="text-align:right;">
                <span style="display:inline-block;padding:3px 10px;
                             border:1px solid {status_color}55;
                             color:{status_color};border-radius:3px;
                             font-size:10px;letter-spacing:0.1em;
                             text-transform:uppercase;font-weight:700;">
                  {status_label}
                </span>
              </div>
            </div>
            """
        )
    st.markdown("".join(rows_html), unsafe_allow_html=True)

    # Small legend
    legend_bits = " &nbsp; ".join(
        f"<span style='color:{STATUS_COLORS[k]};'>■</span> "
        f"<span style='color:#aaa;font-size:11px;letter-spacing:0.06em;"
        f"text-transform:uppercase;'>{STATUS_LABELS[k]}</span>"
        for k in ["live", "partial", "scaffold", "experimental", "requires"]
    )
    st.markdown(
        f"<div style='margin-top:10px;font-size:11px;'>"
        f"<span style='color:#666;letter-spacing:0.1em;text-transform:uppercase;'>"
        f"Legend</span> &nbsp;{legend_bits}</div>",
        unsafe_allow_html=True,
    )

    render_section_footer(CONTENTS_PAGE_META)
