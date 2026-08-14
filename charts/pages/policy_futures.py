"""01b — fixed-contract Three-Month SOFR strip and calendar spreads."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from charts.common import (
    render_explanation_box, render_kpi_strip, render_missing_data_warning,
    render_model_note, render_page_header, render_section_footer, render_top_tabs,
)
from config.pages import get_page
from config.theme import BG, GRID, TEXT_DIM
from config.tickers import SOFR_CONTRACT_CONFIG
from data.policy_futures_loader import load_policy_futures
from models.policy_futures_strip import (
    build_sofr_strip_current_reading, build_sofr_strip_snapshot,
)
from ._context import PageContext


def _fmt(value, spec=".3f", suffix=""):
    return "—" if value is None or pd.isna(value) else f"{value:{spec}}{suffix}"


def _spread_card(label: str, value, sub: str) -> dict:
    return {"label": label, "value": _fmt(value, "+.1f", " bp"), "sub": sub or "—"}


def render(ctx: PageContext) -> None:
    page = get_page("policy_futures")
    render_top_tabs(page["id"])
    futures_df = load_policy_futures()
    snap = build_sofr_strip_snapshot(futures_df, ctx.df, horizons=(1, 5, 20))
    model_date = snap.get("model_date")
    render_page_header(
        page,
        latest_date=(model_date.strftime("%b %d, %Y").upper()
                     if hasattr(model_date, "strftime") else str(model_date or "—")),
        viewing="Eight fixed quarterly SFR contracts · SEP 26 to JUN 28",
    )
    render_explanation_box(
        "SOFR futures strip and calendar spreads",
        "This page follows the reference-pack structure using eight <b>actual quarterly "
        "Three-Month SOFR contracts</b> from the <b>Policy_Futures</b> worksheet. "
        "Each contract keeps its own Bloomberg Date column and prices are joined by "
        "the actual dates, never by row position. Implied rate = <b>100 − price</b>. "
        "The strip is contract-month specific, but it is still not a meeting-by-meeting "
        "FOMC probability model.",
    )

    if snap.get("status") != "Ready":
        render_missing_data_warning(
            required=list(SOFR_CONTRACT_CONFIG),
            missing=snap.get("missing", []),
            message=(f"Fixed SOFR strip status: {snap.get('status')}; common "
                     f"observations: {snap.get('aligned_observations', 0)}."),
        )
        render_section_footer(page)
        return

    terminal = snap["terminal"]
    render_kpi_strip([
        {"label": "Effective FFR", "value": _fmt(snap.get("effr_pct"), ".3f", "%"),
         "sub": f"Observed {snap.get('effr_date') or '—'}"},
        {"label": "SOFR spot", "value": _fmt(snap.get("sofr_pct"), ".3f", "%"),
         "sub": f"Observed {snap.get('sofr_date') or '—'}"},
        {"label": "Strip terminal", "value": _fmt(terminal.get("terminal_rate_pct"), ".3f", "%"),
         "sub": terminal.get("terminal_contract") or "—"},
        {"label": "EFFR to terminal", "value": _fmt(terminal.get("terminal_gap_bp"), "+.1f", " bp"),
         "sub": terminal.get("direction") or "—"},
    ])

    table = snap["strip_table"].copy()
    matrix = snap["calendar_spread_matrix"].copy()
    c1, c2 = st.columns([1.05, 0.95])
    with c1:
        st.markdown("#### SOFR futures strip")
        display = table[["contract_label", "implied_rate_pct", "change_1d_bp",
                         "change_5d_bp", "change_20d_bp"]].rename(columns={
            "contract_label": "Contract", "implied_rate_pct": "Implied rate (%)",
            "change_1d_bp": "1D change (bp)", "change_5d_bp": "5D change (bp)",
            "change_20d_bp": "1M change (bp)",
        })
        st.dataframe(display.style.format({
            "Implied rate (%)": "{:.3f}", "1D change (bp)": "{:+.1f}",
            "5D change (bp)": "{:+.1f}", "1M change (bp)": "{:+.1f}",
        }, na_rep="—"), hide_index=True, use_container_width=True)
        st.caption("1M change = 20 common trading observations; all contracts use the same exact dates.")

    with c2:
        st.markdown("#### Calendar spread matrix")
        st.dataframe(matrix.style.format({
            "3M": "{:+.1f}", "6M": "{:+.1f}", "12M": "{:+.1f}",
        }, na_rep="—"), hide_index=True, use_container_width=True)
        st.caption("Each cell = farther contract implied rate minus row-contract implied rate, in bp.")

    spreads = snap["terminal_spreads"]
    st.markdown("#### Standard STIR spreads")
    render_kpi_strip([
        _spread_card("Effective FFR to terminal", terminal.get("terminal_gap_bp"),
                     f"{snap.get('effr_pct'):.3f}% to {terminal.get('terminal_contract')}" if snap.get('effr_pct') is not None else "—"),
        _spread_card("Terminal to +3 months", spreads.get("terminal_to_3m_bp"),
                     f"{terminal.get('terminal_contract')} to {spreads.get('contract_3m') or '—'}"),
        _spread_card("Terminal to +6 months", spreads.get("terminal_to_6m_bp"),
                     f"{terminal.get('terminal_contract')} to {spreads.get('contract_6m') or '—'}"),
        _spread_card("Terminal to +12 months", spreads.get("terminal_to_12m_bp"),
                     f"{terminal.get('terminal_contract')} to {spreads.get('contract_12m') or '—'}"),
    ])

    st.markdown("#### SOFR strip curve — current vs 1 week / 1 month ago")
    comparison = snap["curve_comparison"]
    comparison_dates = snap["curve_comparison_dates"]
    fig = go.Figure()
    curve_styles = {
        "Current": dict(color="#f8fafc", width=2.4, dash="solid"),
        "1W ago": dict(color="#5fb04f", width=1.6, dash="dash"),
        "1M ago": dict(color="#b184ff", width=1.6, dash="dot"),
    }
    for label in ("1M ago", "1W ago", "Current"):
        values = comparison[label]
        curve_date = comparison_dates.get(label)
        is_current = label == "Current"
        fig.add_trace(go.Scatter(
            x=comparison.index,
            y=values,
            mode="lines+markers+text" if is_current else "lines+markers",
            text=[f"{v:.3f}%" for v in values] if is_current else None,
            textposition="top center",
            name=f"{label} · {curve_date or 'unavailable'}",
            line=curve_styles[label],
            marker=dict(size=8 if is_current else 6),
            customdata=[str(curve_date or "—")] * len(values),
            hovertemplate=(
                "%{x}<br>Curve date %{customdata}<br>"
                "Implied rate %{y:.4f}%<extra></extra>"
            ),
        ))
    fig.add_hline(y=snap.get("effr_pct"), line=dict(width=1, dash="dot", color="#888"),
                  annotation_text="EFFR" if snap.get("effr_pct") is not None else None)
    fig.update_layout(
        height=390, template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(size=10, color=TEXT_DIM), margin=dict(l=55, r=20, t=35, b=40),
        yaxis=dict(title="Implied Three-Month SOFR rate (%)", gridcolor=GRID),
        xaxis=dict(title="Contract month", showgrid=False), hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True, key="fixed_sofr_strip", config={"displayModeBar": False})
    st.caption(
        "1 week = 5 and 1 month = 20 common trading observations. Every curve uses "
        "one exact date shared by all eight contracts; no forward-fill or interpolation."
    )

    with st.expander("Fixed-contract price and rate history"):
        history = snap["implied_rate_history"].tail(504)
        hist_fig = go.Figure()
        for code in history.columns:
            hist_fig.add_trace(go.Scatter(
                x=history.index, y=history[code], mode="lines",
                name=SOFR_CONTRACT_CONFIG[code]["contract_label"], line=dict(width=1.2),
            ))
        hist_fig.update_layout(
            height=420, template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
            font=dict(size=10, color=TEXT_DIM), hovermode="x unified",
            margin=dict(l=55, r=20, t=25, b=35),
            yaxis=dict(title="Implied rate (%)", gridcolor=GRID),
            xaxis=dict(showgrid=False), legend=dict(orientation="h", y=1.12, x=0),
        )
        st.plotly_chart(hist_fig, use_container_width=True, key="fixed_sofr_history",
                        config={"displayModeBar": False})

    reading = build_sofr_strip_current_reading(futures_df, ctx.df)
    st.markdown("#### Current reading")
    st.info(reading["summary"])
    st.caption(reading["limitations"])

    render_model_note(
        "Methodology and maintenance",
        "The production strip uses SFRU6, SFRZ6, SFRH7, SFRM7, SFRU7, SFRZ7, "
        "SFRH8 and SFRM8 from DATA.xlsx / Policy_Futures. Each contract is aligned "
        "using its own BQL Date output. Calendar spreads use actual quarterly sequence "
        "distances. The terminal is the first peak or trough corresponding to the "
        "larger move from current EFFR. This fixed contract list must be rolled manually "
        "when contracts expire. Last-trade dates and meeting probabilities are not inferred.",
    )
    render_section_footer(page)
