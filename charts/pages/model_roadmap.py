"""
charts/pages/model_roadmap.py
=============================
Section 08 — Model Roadmap / Content Gap.

Shows what content matches the reference PDF, what is missing, what data is
needed, and what should be built next. This is NOT about PDF export — it is
about building equivalent analytical depth inside the dashboard.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from config.pages import get_page
from config.model_roadmap import (
    ROADMAP, coverage_summary, by_status, do_not_fake_list, BUILD_PRIORITIES,
)
from charts.common import (
    render_page_header, render_top_tabs, render_kpi_strip,
    render_explanation_box, render_model_note,
    render_current_reading_list, render_section_footer,
)
from ._context import PageContext


STATUS_COLORS = {
    "Live": "#5fb04f", "Partial": "#d99830", "Experimental": "#b184ff",
    "Data Missing": "#d04848", "Not Started": "#666",
}


def _status_style(val):
    c = STATUS_COLORS.get(val, "#888")
    return f"color: {c}; font-weight: 700;"


def render(ctx: PageContext) -> None:
    page = get_page("model_roadmap")
    render_top_tabs(page["id"])

    from data.loader import latest_valid_date
    lvd = latest_valid_date(ctx.df)
    latest = lvd.strftime("%b %d, %Y").upper() if lvd else "—"
    render_page_header(page, latest_date=latest)

    render_explanation_box(
        "Content gap analysis",
        "The reference PDF is a <b>content and model benchmark</b>, not a "
        "file-format target. This page maps every section of the reference "
        "to our implementation status, shows what data is missing, and "
        "recommends what to build next. Models are never faked — if the "
        "required data is absent, the module stays on the roadmap until "
        "the data arrives.",
    )

    # KPI strip — coverage summary
    counts = coverage_summary()
    total = sum(counts.values())
    render_kpi_strip([
        {"label": "Live", "value": str(counts.get("Live", 0)),
         "sub": f"of {total} modules", "accent": "#5fb04f"},
        {"label": "Partial", "value": str(counts.get("Partial", 0)), "accent": "#d99830"},
        {"label": "Experimental", "value": str(counts.get("Experimental", 0)), "accent": "#b184ff"},
        {"label": "Data Missing", "value": str(counts.get("Data Missing", 0)), "accent": "#d04848"},
        {"label": "Not Started", "value": str(counts.get("Not Started", 0))},
    ])

    # ── A. What we already match ──
    st.markdown("<div style='margin:1rem 0 0.3rem;font-size:11px;color:#888;"
                "letter-spacing:0.1em;text-transform:uppercase;'>"
                "What we already match from the reference</div>",
                unsafe_allow_html=True)
    live_mods = by_status("Live") + by_status("Partial") + by_status("Experimental")
    if live_mods:
        df_live = pd.DataFrame([{
            "App section": m.get("app_section") or m.get("section", "—"),
            "Reference section": m.get("reference_section") or m.get("section", "—"),
            "Module": m["title"],
            "Status": m["current_status"],
            "Implemented in": m.get("implemented_in") or "—",
            "Notes": m.get("build_notes", ""),
        } for m in live_mods])
        st.dataframe(df_live.style.map(_status_style, subset=["Status"]),
                     hide_index=True, use_container_width=True)

    # ── B. What is still missing ──
    st.markdown("<div style='margin:1rem 0 0.3rem;font-size:11px;color:#888;"
                "letter-spacing:0.1em;text-transform:uppercase;'>"
                "What is still missing</div>", unsafe_allow_html=True)
    missing_mods = by_status("Data Missing") + by_status("Not Started")
    if missing_mods:
        df_missing = pd.DataFrame([{
            "App section": m.get("app_section") or "—",
            "Reference section": m.get("reference_section") or m.get("section", "—"),
            "Module": m["title"],
            "Required data": ", ".join(m.get("required_data", [])[:3]) + ("…" if len(m.get("required_data", [])) > 3 else ""),
            "Missing": ", ".join(m.get("missing_data", [])),
            "Priority": BUILD_PRIORITIES.get(m["recommended_priority"], "—"),
        } for m in missing_mods])
        st.dataframe(df_missing, hide_index=True, use_container_width=True)

    # ── C. Do not fake these models ──
    st.markdown("<div style='margin:1rem 0 0.3rem;font-size:11px;color:#888;"
                "letter-spacing:0.1em;text-transform:uppercase;'>"
                "Do not fake these models</div>", unsafe_allow_html=True)
    dnf = do_not_fake_list()
    if dnf:
        render_model_note(
            "Integrity constraint",
            "These modules require missing data, confirmed metadata, or an "
            "implemented and tested methodology. They must not be completed "
            "with fabricated inputs, undocumented proxies, or unsupported "
            "assumptions."
        )
        def _blocker_reason(m):
            dss = m.get("data_source_status", "")
            missing = m.get("missing_data", [])
            notes = m.get("build_notes", "")
            if missing:
                return f"Missing data: {', '.join(missing)}"
            if dss and dss.lower() != "available":
                return f"Data source status: {dss}"
            if notes:
                return notes
            return "Methodology or metadata pending"
        dnf_items = [(m["title"], _blocker_reason(m)) for m in dnf]
        render_current_reading_list(
            "Blocked pending data, metadata, or methodology", dnf_items)

    # ── D. Next recommended build ──
    st.markdown("<div style='margin:1rem 0 0.3rem;font-size:11px;color:#888;"
                "letter-spacing:0.1em;text-transform:uppercase;'>"
                "Recommended build order</div>", unsafe_allow_html=True)
    for pri in sorted(BUILD_PRIORITIES.keys()):
        if pri == 0:
            continue  # already built
        mods = [m for m in ROADMAP if m["recommended_priority"] == pri]
        if not mods:
            continue
        st.markdown(
            f"<div style='margin:0.4rem 0;font-size:12px;'>"
            f"<b style='color:#35bdf4;'>{BUILD_PRIORITIES[pri]}</b></div>",
            unsafe_allow_html=True)
        for m in mods:
            st.markdown(
                f"<div style='font-size:11px;color:#ccc;margin-left:16px;'>"
                f"• {m['title']} — <span style='color:#888;'>{m.get('build_notes','')}</span></div>",
                unsafe_allow_html=True)

    render_section_footer(page)
