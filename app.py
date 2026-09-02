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
from config.pages import (
    PAGES_BY_ID, SIDEBAR_NAV_GROUPS, sidebar_label,
)
from data.loader import (
    load_data, date_filter, latest_valid_date,
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


# Sidebar navigation state.  Buttons are used instead of a 19-option radio so
# the pages can be grouped without changing any internal page id or renderer.
_VALID_PAGE_IDS = {"contents", *PAGES_BY_ID.keys()}
if st.session_state.get("active_page") not in _VALID_PAGE_IDS:
    st.session_state["active_page"] = "contents"


def _activate_page(page_id: str) -> None:
    if page_id in _VALID_PAGE_IDS:
        st.session_state["active_page"] = page_id


def _render_sidebar_navigation() -> None:
    active_page = st.session_state["active_page"]
    st.markdown('<div class="sidebar-section-label">Navigation</div>',
                unsafe_allow_html=True)
    for group in SIDEBAR_NAV_GROUPS:
        expanded = active_page in group["page_ids"]
        with st.expander(group["label"], expanded=expanded):
            for page_id in group["page_ids"]:
                label = sidebar_label(page_id)
                if page_id == active_page:
                    page = PAGES_BY_ID.get(page_id)
                    accent = section_color(page["color_key"]) if page else "#5fb04f"
                    st.markdown(
                        f"""
                        <div class="sidebar-nav-active" style="--nav-accent:{accent};">
                          <span>{label}</span><small>Current</small>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                else:
                    st.button(
                        label,
                        key=f"sidebar_nav_{page_id}",
                        on_click=_activate_page,
                        args=(page_id,),
                        width="stretch",
                    )

with st.sidebar:
    st.markdown(
        f"""
        <div class="sidebar-brand">
          <div class="sidebar-brand-kicker">Daily Macro Research</div>
          <div class="sidebar-brand-title">Rates &amp; Liquidity</div>
          <div class="sidebar-brand-sub">Research Board</div>
        </div>
        """, unsafe_allow_html=True)

    _raw_date = df.index.max() if not df.empty else None
    _official_date = index_result.latest_date
    _raw_date_text = _raw_date.strftime("%b %d") if _raw_date is not None else "—"
    _official_date_text = (
        _official_date.strftime("%b %d") if _official_date is not None else "—"
    )
    _pending_text = "Complete"
    if (_raw_date is not None and _official_date is not None
            and _raw_date > _official_date
            and _raw_date in index_result.available_bucket_count.index):
        _pending_buckets = int(index_result.available_bucket_count.loc[_raw_date])
        _pending_components = int(index_result.available_component_count.loc[_raw_date])
        _normal_target = int(index_result.normal_component_target.loc[_raw_date])
        _pending_text = (
            f"{_pending_buckets}/5 buckets · "
            f"{_pending_components}/{_normal_target} live"
        )
    st.markdown(
        f"""
        <div class="sidebar-data-status">
          <div class="sidebar-status-row">
            <span>Raw data</span><strong>{_raw_date_text}</strong>
          </div>
          <div class="sidebar-status-row">
            <span>Official model</span><strong>{_official_date_text}</strong>
          </div>
          <div class="sidebar-status-row sidebar-status-pending">
            <span>Pending</span><strong>{_pending_text}</strong>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    _render_sidebar_navigation()

    st.markdown('<div class="sidebar-section-label sidebar-lookback-label">Lookback</div>',
                unsafe_allow_html=True)
    range_preset = st.selectbox(
        "Lookback window",
        ["6M", "1Y", "3Y", "5Y", "10Y", "Max", "Custom"],
        index=2,
        key="lookback_preset",
        label_visibility="collapsed",
    )
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
        st.markdown(
            f"""
            <div class="sidebar-liquidity-card" style="--regime-color:{reg_color};">
              <div>
                <span>Liquidity official</span>
                <strong>{index_result.latest:.1f}</strong>
              </div>
              <div class="sidebar-liquidity-meta">
                <strong>{reg}</strong>
                <span>{official_date:%b %d, %Y}</span>
              </div>
            </div>
            """, unsafe_allow_html=True)

    try:
        st.download_button(
            label="⬇  Export Board to PDF",
            data=lambda: _build_pdf_export(sig, _prod_date)[0],
            file_name=_pdf_export_name,
            mime="application/pdf",
            key="sidebar_export_board_pdf",
            width="stretch",
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

page_id = st.session_state["active_page"]
render_page(page_id, ctx)
