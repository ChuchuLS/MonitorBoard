"""
app.py — Rates & Liquidity Research Pack
========================================
Thin registry-driven router. Everything meaningful lives in submodules.

Phase 1.5: cleanup pass — honest page naming, lazy export, data-source-aware
date display.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import pandas as pd
import streamlit as st

from config.theme import REGIME_COLORS, TEXT_DIM, section_color, page_css
from config.pages import PAGES, PAGES_BY_ID, nav_label
from data.loader import (
    load_data, date_filter, data_source_label, latest_valid_date,
    source_signature,
)
from charts.pages import PageContext, render_page
from index.composite import compute_index
from index.methodology import (
    compute_legacy_index, reconciliation, methodology_audit,
    component_contribution_table, forward_fill_audit,
)
from index.export import build_index_workbook, export_filename

st.set_page_config(
    page_title="Rates & Liquidity Research Pack",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)


# Password gate
def _check_password() -> bool:
    try:
        expected = st.secrets.get("app_password")
    except Exception:
        expected = None
    if not expected:
        return True
    if st.session_state.get("password_correct"):
        return True
    st.markdown(
        """
        <div style="max-width:420px;margin:5rem auto 1rem;padding:2rem;
                    background:#0a0a0a;border:1px solid #1a1a1a;border-radius:6px;
                    font-family:Inter,system-ui,sans-serif;color:#fff;">
          <div style="font-size:18px;font-weight:700;letter-spacing:0.06em;
                      text-transform:uppercase;margin-bottom:6px;">
            Rates &amp; Liquidity Research Pack</div>
          <div style="font-size:11px;color:#888;letter-spacing:0.08em;
                      text-transform:uppercase;margin-bottom:1.5rem;">
            Authentication required</div>
        </div>
        """, unsafe_allow_html=True)
    pwd = st.text_input("Password", type="password", key="password_input",
                        label_visibility="collapsed", placeholder="Enter password")
    if pwd:
        if pwd == expected:
            st.session_state["password_correct"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")
    return False


if not _check_password():
    st.stop()

st.markdown(page_css(), unsafe_allow_html=True)
df = load_data()


# Production date — controls cache invalidation on date rollover
from data.date_integrity import current_production_date
_prod_date = current_production_date(timezone="Asia/Singapore").isoformat()


# Cached builders — keyed on DATA.xlsx content hash + production date
@st.cache_data(show_spinner="Building Composite Liquidity Index...")
def _build_index(source_hash: str, production_date: str):
    return compute_index(load_data())

@st.cache_data(show_spinner="Building methodology audit & reconciliation...")
def _build_audit(source_hash: str, production_date: str):
    df_local = load_data()
    cur = _build_index(source_hash, production_date)
    legacy = compute_legacy_index(df_local)
    return {
        "methodology": methodology_audit(cur, df_local, data_hash=source_hash),
        "reconciliation": reconciliation(cur, legacy, df_local),
        "components": component_contribution_table(cur, df_local),
        "ffill_audit": forward_fill_audit(cur, df_local),
    }

@st.cache_data(show_spinner="Preparing Excel export...")
def _build_export(source_hash: str, production_date: str) -> bytes:
    df_local = load_data()
    cur = _build_index(source_hash, production_date)
    return build_index_workbook(cur, _build_audit(source_hash, production_date), df_local)

@st.cache_data(show_spinner="Preparing Board PDF...")
def _build_pdf_export(source_hash: str, production_date: str) -> tuple[bytes, str]:
    """Build the complete linked research pack once per data vintage."""
    from scripts.export_research_pack_pdf import build_pdf
    df_local = load_data()
    return build_pdf(df_local, _build_index(source_hash, production_date))


sig = source_signature()
index_result = _build_index(sig, _prod_date)
audit_bundle = _build_audit(sig, _prod_date)
_latest_export_date = latest_valid_date(df)
_pdf_export_name = (
    f"rates_liquidity_board_{_latest_export_date:%Y%m%d}.pdf"
    if _latest_export_date is not None
    else "rates_liquidity_board_unknown.pdf"
)


# Sidebar
NAV_OPTIONS = ["Contents"] + [nav_label(p) for p in PAGES]
_LABEL_TO_ID = {"Contents": "contents"}
for p in PAGES:
    _LABEL_TO_ID[nav_label(p)] = p["id"]

with st.sidebar:
    st.markdown(
        """
        <div style="padding:0.5rem 0 0.25rem;">
          <div style="font-size:14px;font-weight:700;letter-spacing:0.08em;
                      color:#fff;text-transform:uppercase;">
            Rates &amp; Liquidity Pack</div>
          <div style="font-size:9px;color:#888;letter-spacing:0.12em;
                      text-transform:uppercase;margin-top:2px;">
            Daily macro / liquidity research shell</div>
        </div>
        """, unsafe_allow_html=True)
    st.caption(f"{df.index.min().date()} → {df.index.max().date()}  ·  "
               f"src: {data_source_label()}")
    st.divider()

    nav_choice = st.radio("SECTION", NAV_OPTIONS, index=0, key="nav_page")
    st.divider()

    range_preset = st.radio(
        "LOOKBACK", ["6M", "1Y", "3Y", "5Y", "10Y", "Max", "Custom"],
        index=2, key="lookback_preset")
    end_date = df.index.max()
    if range_preset == "6M":
        start_date = end_date - pd.DateOffset(months=6)
    elif range_preset == "1Y":
        start_date = end_date - pd.DateOffset(years=1)
    elif range_preset == "3Y":
        start_date = end_date - pd.DateOffset(years=3)
    elif range_preset == "5Y":
        start_date = end_date - pd.DateOffset(years=5)
    elif range_preset == "10Y":
        start_date = end_date - pd.DateOffset(years=10)
    elif range_preset == "Max":
        start_date = df.index.min()
    else:
        custom = st.date_input("Range",
                               value=(end_date - pd.DateOffset(years=3), end_date),
                               min_value=df.index.min().date(),
                               max_value=df.index.max().date())
        if isinstance(custom, tuple) and len(custom) == 2:
            start_date, end_date = pd.Timestamp(custom[0]), pd.Timestamp(custom[1])
        else:
            start_date = end_date - pd.DateOffset(years=3)

    if not pd.isna(index_result.latest):
        reg = index_result.latest_regime
        reg_color = REGIME_COLORS.get(reg, TEXT_DIM)
        official_date = index_result.latest_date
        st.divider()
        st.markdown(
            f"""
            <div style="font-size:10px;color:#888;letter-spacing:0.1em;
                        text-transform:uppercase;">Liquidity official</div>
            <div style="font-size:26px;font-weight:700;color:{reg_color};
                        line-height:1.1;">{index_result.latest:.1f}</div>
            <div style="font-size:11px;color:{reg_color};font-weight:700;
                        text-transform:uppercase;letter-spacing:0.06em;">{reg}</div>
            <div style="font-size:9px;color:#777;margin-top:3px;">
              AS OF {official_date.date() if official_date is not None else '—'}</div>
            """, unsafe_allow_html=True)
        if index_result.preliminary_date is not None:
            st.caption(
                f"Preliminary {index_result.preliminary_date.date()}: "
                f"{index_result.preliminary_latest:.1f} · excluded from headline"
            )

    st.divider()
    try:
        st.download_button(
            label="⬇  Export Board to PDF",
            data=lambda: _build_pdf_export(sig, _prod_date)[0],
            file_name=_pdf_export_name,
            mime="application/pdf",
            key="sidebar_export_board_pdf",
            use_container_width=True,
            help="Download the complete linked Board, not only the page currently open.",
        )
        st.caption("Complete linked pack · all registered Board pages")
    except Exception as exc:
        st.error(f"PDF export unavailable: {type(exc).__name__}")


# Build context — export is LAZY (callable, not pre-built bytes)
dff = date_filter(df, start_date, end_date)
ctx = PageContext(
    df=df, dff=dff, start_date=start_date, end_date=end_date,
    index_result=index_result, audit_bundle=audit_bundle,
    export_builder=lambda: _build_export(sig, _prod_date),
    export_name=export_filename(audit_bundle),
    pdf_export_builder=lambda: _build_pdf_export(sig, _prod_date)[0],
    pdf_export_name=_pdf_export_name,
)

page_id = _LABEL_TO_ID.get(nav_choice, "contents")
render_page(page_id, ctx)
