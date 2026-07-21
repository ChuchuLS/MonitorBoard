"""
charts/pages/decomposition.py
=============================
Section 02 — Rate Decomposition (Phase 2: LIVE).

Decomposes US nominal yield moves into real-rate and inflation (breakeven)
components using the identity: nominal ≡ real + breakeven. Residual is zero
by construction.
"""
from __future__ import annotations
import pandas as pd, numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from config.pages import get_page
from config.theme import section_color, BG, GRID, TEXT_DIM, DARK_LAYOUT, ACCENT_GREEN, ACCENT_CYAN, ACCENT_AMBER
from charts.common import (
    render_page_header, render_top_tabs, render_kpi_strip,
    render_explanation_box, render_current_reading_box,
    render_model_note, render_missing_data_warning, render_section_footer,
)
from models.rate_decomposition import (
    available_us_tenors, build_us_curve_snapshot,
    rolling_rate_attribution, rolling_curve_decomposition,
)
from ._context import PageContext

COLOR_NOM = "#ffffff"
COLOR_REAL = "#06b6d4"
COLOR_INFL = "#f97316"


def render(ctx: PageContext) -> None:
    page = get_page("decomposition")
    render_top_tabs(page["id"])
    from data.loader import latest_valid_date as _lvd
    from models.rate_decomposition import US_NOMINAL, US_BREAKEVEN
    _req = list(US_NOMINAL.values()) + list(US_BREAKEVEN.values())
    _ld = _lvd(ctx.df, _req) or ctx.df.index.max()
    latest = _ld.strftime("%b %d, %Y").upper()
    render_page_header(page, latest_date=latest, viewing="Data source: DATA.xlsx / Sheet1")

    tenors = available_us_tenors(ctx.df)
    if not tenors:
        render_missing_data_warning(
            required=["USGG2YR/5YR/10YR/30YR INDEX", "USGGBE02/05/10/30 INDEX"],
            missing=["Required nominal or breakeven columns not found"],
        )
        render_section_footer(page); return

    snap = build_us_curve_snapshot(ctx.df)
    if snap.empty:
        st.warning("Insufficient data for curve snapshot."); render_section_footer(page); return

    # A. KPI strip
    row10 = snap[snap["tenor"] == "10Y"]
    if not row10.empty:
        r = row10.iloc[0]
        render_kpi_strip([
            {"label": "10Y Nominal", "value": f"{r['nominal']:.2f}%",
             "sub": f"1M: {r['nominal_1m_change_bp']:+.0f} bp" if pd.notna(r['nominal_1m_change_bp']) else ""},
            {"label": "10Y Real", "value": f"{r['real']:.2f}%", "accent": COLOR_REAL,
             "sub": f"1M: {r['real_1m_change_bp']:+.0f} bp" if pd.notna(r['real_1m_change_bp']) else ""},
            {"label": "10Y Inflation", "value": f"{r['inflation']:.2f}%", "accent": COLOR_INFL,
             "sub": f"1M: {r['inflation_1m_change_bp']:+.0f} bp" if pd.notna(r['inflation_1m_change_bp']) else ""},
            {"label": "10Y 1M Driver", "value": r["driver_1m"],
             "sub": f"{r['driver_share_1m']:.0%} share" if pd.notna(r['driver_share_1m']) else ""},
        ])

    render_explanation_box(
        "Rate decomposition",
        "Splits nominal yield moves into a <b>real-rate</b> leg and an "
        "<b>inflation (breakeven)</b> leg using the identity: "
        "nominal ≡ real + breakeven. The residual is zero by construction.",
    )

    # B. US Curve Complex — three curve charts
    st.markdown("<div style='margin:0.8rem 0 0.3rem;font-size:11px;color:#888;"
                "letter-spacing:0.1em;text-transform:uppercase;'>"
                "US curve complex — today vs 1 month ago</div>", unsafe_allow_html=True)

    fig = make_subplots(rows=1, cols=3, subplot_titles=["Nominal", "Real", "Inflation"],
                        horizontal_spacing=0.06)
    x_tenors = snap["tenor"].tolist()
    for i, (curve, color, col) in enumerate([
        ("nominal", COLOR_NOM, 1), ("real", COLOR_REAL, 2), ("inflation", COLOR_INFL, 3)
    ]):
        fig.add_trace(go.Scatter(x=x_tenors, y=snap[curve], mode="lines+markers",
            line=dict(color=color, width=2), marker=dict(size=6),
            name=f"{curve.title()} today", showlegend=(i==0)), row=1, col=col)
        fig.add_trace(go.Scatter(x=x_tenors, y=snap[f"{curve}_ago"], mode="lines+markers",
            line=dict(color=color, width=1, dash="dot"), marker=dict(size=4),
            name=f"{curve.title()} 1M ago", showlegend=(i==0)), row=1, col=col)
    fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(family="Inter, system-ui, sans-serif", size=10, color=TEXT_DIM),
        height=320, margin=dict(l=50, r=20, t=40, b=30), showlegend=True,
        legend=dict(orientation="h", y=-0.15, font=dict(size=10, color="#aaa")))
    for c in range(1, 4):
        fig.update_yaxes(gridcolor=GRID, ticksuffix="%", row=1, col=c)
        fig.update_xaxes(showgrid=False, row=1, col=c)
    st.plotly_chart(fig, use_container_width=True, key="dec_curves", config={"displayModeBar": False})

    # C. Rolling attribution
    st.markdown("<div style='margin:1rem 0 0.3rem;font-size:11px;color:#888;"
                "letter-spacing:0.1em;text-transform:uppercase;'>"
                "Rolling rate attribution</div>", unsafe_allow_html=True)
    ac1, ac2 = st.columns(2)
    with ac1:
        sel_tenor = st.selectbox("Tenor", tenors, index=tenors.index("10Y") if "10Y" in tenors else 0, key="dec_tenor")
    with ac2:
        sel_window = st.selectbox("Window", [10, 20], format_func=lambda x: f"{x}D", key="dec_win")

    att = rolling_rate_attribution(ctx.df, tenor=sel_tenor, window=sel_window)
    if not att.dropna().empty:
        att_plot = att.dropna().iloc[-252:]  # 1Y lookback
        fig_att = go.Figure()
        fig_att.add_trace(go.Bar(x=att_plot.index, y=att_plot["real_contribution_bp"],
            name="Real", marker_color=COLOR_REAL))
        fig_att.add_trace(go.Bar(x=att_plot.index, y=att_plot["inflation_contribution_bp"],
            name="Inflation", marker_color=COLOR_INFL))
        fig_att.add_trace(go.Scatter(x=att_plot.index, y=att_plot["nominal_change_bp"],
            mode="lines", name=f"Nominal {sel_window}D Δ", line=dict(color=COLOR_NOM, width=1.5)))
        fig_att.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
            font=dict(family="Inter, system-ui, sans-serif", size=10, color=TEXT_DIM),
            height=340, barmode="relative", showlegend=True,
            legend=dict(orientation="h", y=1.02, x=0, font=dict(size=10, color="#aaa")),
            margin=dict(l=50, r=20, t=30, b=25),
            yaxis=dict(title="bp", gridcolor=GRID), xaxis=dict(showgrid=False))
        st.plotly_chart(fig_att, use_container_width=True, key="dec_att", config={"displayModeBar": False})

    # D. 2s10s Curve Decomposition
    st.markdown("<div style='margin:1rem 0 0.3rem;font-size:11px;color:#888;"
                "letter-spacing:0.1em;text-transform:uppercase;'>"
                "2s10s curve decomposition</div>", unsafe_allow_html=True)
    cd = rolling_curve_decomposition(ctx.df, ("2Y", "10Y"), sel_window)
    if not cd.dropna().empty:
        cd_plot = cd.dropna().iloc[-252:]
        fig_cd = go.Figure()
        fig_cd.add_trace(go.Bar(x=cd_plot.index, y=cd_plot["real_leg_change_bp"],
            name="Real leg", marker_color=COLOR_REAL))
        fig_cd.add_trace(go.Bar(x=cd_plot.index, y=cd_plot["inflation_leg_change_bp"],
            name="Inflation leg", marker_color=COLOR_INFL))
        fig_cd.add_trace(go.Scatter(x=cd_plot.index, y=cd_plot["nominal_spread_change_bp"],
            mode="lines", name=f"2s10s {sel_window}D Δ", line=dict(color=COLOR_NOM, width=1.5)))
        fig_cd.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
            font=dict(family="Inter, system-ui, sans-serif", size=10, color=TEXT_DIM),
            height=300, barmode="relative", showlegend=True,
            legend=dict(orientation="h", y=1.02, x=0, font=dict(size=10, color="#aaa")),
            margin=dict(l=50, r=20, t=30, b=25),
            yaxis=dict(title="bp", gridcolor=GRID), xaxis=dict(showgrid=False))
        st.plotly_chart(fig_cd, use_container_width=True, key="dec_cd", config={"displayModeBar": False})

    # E. Current Reading
    if not row10.empty:
        r = row10.iloc[0]
        render_current_reading_box("Current reading — 10Y (1 month)",
            f"Nominal: <b>{r['nominal_1m_change_bp']:+.0f} bp</b><br>"
            f"Real contribution: <b>{r['real_1m_change_bp']:+.0f} bp</b><br>"
            f"Inflation contribution: <b>{r['inflation_1m_change_bp']:+.0f} bp</b><br>"
            f"Dominant driver: <b>{r['driver_1m']}</b> ({r['driver_share_1m']:.0%} share)<br>"
            f"Identity residual: <b>zero</b> (breakeven mode)"
            if pd.notna(r['nominal_1m_change_bp']) else "Insufficient data")

    # F. Methodology
    render_model_note("Methodology",
        "This page uses <b>breakeven inflation</b> as the inflation leg, so "
        "<code>nominal = real + inflation</code> is an identity by construction. "
        "The residual is exactly zero. If inflation swaps are used in a future "
        "version, a residual must be shown.")

    render_section_footer(page)
