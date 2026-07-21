"""
charts/pages/regimes.py
=======================
Section 03 — Curve Regimes (Phase 2: LIVE).

Classifies curve moves into directional regimes across nominal, real, and
inflation spread pairs. Uses 10D window by default.
"""
from __future__ import annotations
import pandas as pd, numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from config.pages import get_page
from config.theme import section_color, BG, GRID, TEXT_DIM, DARK_LAYOUT
from config.tickers import TENOR_PAIRS
from charts.common import (
    render_page_header, render_top_tabs, render_kpi_strip,
    render_explanation_box, render_current_reading_box,
    render_model_note, render_section_footer,
)
from models.curve_regimes import (
    classify_pair_history, build_regime_matrix, dominant_regime,
    days_in_current_regime, REGIME_COLORS, REGIME_LABELS,
)
from ._context import PageContext


def _regime_ribbon(hist: pd.DataFrame, title: str, height: int = 200):
    """Spread line + regime colour ribbon."""
    h = hist.dropna(subset=["regime"])
    if h.empty:
        return None
    fig = go.Figure()
    # Spread line
    fig.add_trace(go.Scatter(x=h.index, y=h["spread"] * 100, mode="lines",
        line=dict(color="#fff", width=1.2), name="Spread (bp)", showlegend=False))
    # Regime ribbon at bottom
    for regime in REGIME_LABELS:
        mask = h["regime"] == regime
        if not mask.any():
            continue
        s = h.loc[mask]
        fig.add_trace(go.Scatter(x=s.index, y=[0]*len(s), mode="markers",
            marker=dict(color=REGIME_COLORS.get(regime, "#525252"), size=4, symbol="square"),
            name=regime, showlegend=False))
    fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(family="Inter, system-ui, sans-serif", size=10, color=TEXT_DIM),
        height=height, margin=dict(l=50, r=20, t=30, b=20),
        title=dict(text=title, font=dict(size=12, color="#aaa"), x=0),
        yaxis=dict(title="bp", gridcolor=GRID), xaxis=dict(showgrid=False))
    return fig


def render(ctx: PageContext) -> None:
    page = get_page("regimes")
    render_top_tabs(page["id"])
    from data.loader import latest_valid_date as _lvd
    from models.rate_decomposition import US_NOMINAL, US_BREAKEVEN
    _req = list(US_NOMINAL.values()) + list(US_BREAKEVEN.values())
    _ld = _lvd(ctx.df, _req) or ctx.df.index.max()
    latest = _ld.strftime("%b %d, %Y").upper()
    render_page_header(page, latest_date=latest, viewing="Data source: DATA.xlsx / Sheet1")

    render_explanation_box(
        "Curve regime classification",
        "Classifies each day's curve move into one of 7 regimes based on "
        "the direction of front and back yields and the spread change over "
        "a rolling window. Applied to <b>nominal, real, and inflation</b> "
        "curves across 6 tenor pairs.",
    )

    # Regime legend
    legend_bits = " &nbsp; ".join(
        f"<span style='display:inline-block;width:10px;height:10px;"
        f"background:{REGIME_COLORS[r]};vertical-align:middle;"
        f"margin-right:3px;border-radius:2px;'></span>"
        f"<span style='color:#aaa;font-size:10px;'>{r}</span>"
        for r in REGIME_LABELS
    )
    st.markdown(f"<div style='margin:0.4rem 0 0.8rem;line-height:2;'>{legend_bits}</div>",
                unsafe_allow_html=True)

    # A. KPI strip — 2s10s regimes
    kpi_cards = []
    for ctype in ["Nominal", "Real", "Inflation"]:
        h = classify_pair_history(ctx.df, ctype.lower(), ("2Y", "10Y"), 10)
        if h.empty or h["regime"].dropna().empty:
            kpi_cards.append({"label": f"{ctype} 2s10s", "value": "—"})
            continue
        regime = h["regime"].dropna().iloc[-1]
        days = days_in_current_regime(h["regime"])
        spread_now = h["spread"].dropna().iloc[-1] * 100 if h["spread"].dropna().shape[0] else np.nan
        kpi_cards.append({
            "label": f"{ctype} 2s10s",
            "value": regime,
            "sub": f"{days} days · {spread_now:+.0f} bp" if pd.notna(spread_now) else f"{days} days",
            "accent": REGIME_COLORS.get(regime, "#525252"),
        })
    # Add 2s10s level
    h_nom = classify_pair_history(ctx.df, "nominal", ("2Y", "10Y"), 10)
    if not h_nom.empty and h_nom["spread"].dropna().shape[0]:
        lvl = h_nom["spread"].dropna().iloc[-1] * 100
        kpi_cards.append({"label": "2s10s Level", "value": f"{lvl:+.0f} bp"})
    render_kpi_strip(kpi_cards)

    # B. 2s10s Regime History (6M lookback)
    st.markdown("<div style='margin:0.8rem 0 0.3rem;font-size:11px;color:#888;"
                "letter-spacing:0.1em;text-transform:uppercase;'>"
                "2s10s regime history (6 months)</div>", unsafe_allow_html=True)

    for ctype in ["Nominal", "Real", "Inflation"]:
        h = classify_pair_history(ctx.df, ctype.lower(), ("2Y", "10Y"), 10)
        if h.empty:
            continue
        h_tail = h.iloc[-126:]  # ~6 months
        fig = _regime_ribbon(h_tail, f"{ctype} 2s10s")
        if fig:
            st.plotly_chart(fig, use_container_width=True,
                            key=f"reg_{ctype.lower()}", config={"displayModeBar": False})

    # C. Regime Matrix
    st.markdown("<div style='margin:1rem 0 0.3rem;font-size:11px;color:#888;"
                "letter-spacing:0.1em;text-transform:uppercase;'>"
                "Regime matrix (latest)</div>", unsafe_allow_html=True)

    matrix = build_regime_matrix(ctx.df, window=10)
    if not matrix.empty:
        def _color_cell(val):
            c = REGIME_COLORS.get(val, "#525252")
            return f"background-color: {c}22; color: {c}; font-weight: 700;"
        styled = matrix.style.map(_color_cell)
        st.dataframe(styled, use_container_width=True, height=160)

    # D. Regime Landscape
    st.markdown("<div style='margin:1rem 0 0.3rem;font-size:11px;color:#888;"
                "letter-spacing:0.1em;text-transform:uppercase;'>"
                "Regime landscape</div>", unsafe_allow_html=True)
    if not matrix.empty:
        landscape_rows = []
        for ctype in matrix.index:
            d = dominant_regime(matrix.loc[ctype])
            landscape_rows.append({
                "Curve": ctype, "Dominant": d["regime"],
                "Count": d["count"], "Total": d["total"],
                "Divergent": d["divergent"],
            })
        st.dataframe(pd.DataFrame(landscape_rows), hide_index=True, use_container_width=True)

    # E. Current Reading
    readings = []
    for ctype in ["Nominal", "Real", "Inflation"]:
        h = classify_pair_history(ctx.df, ctype.lower(), ("2Y", "10Y"), 10)
        if not h.empty and h["regime"].dropna().shape[0]:
            r = h["regime"].dropna().iloc[-1]
            readings.append(f"{ctype} 2s10s: <b>{r}</b>")
    if not matrix.empty:
        d = dominant_regime(matrix.loc["Nominal"])
        readings.append(f"Nominal dominant: <b>{d['regime']}</b> ({d['count']}/{d['total']} pairs)")
        readings.append(f"Divergent pairs: <b>{d['divergent']}</b>")
    if readings:
        render_current_reading_box("Current reading", "<br>".join(readings))

    # F. Methodology
    render_model_note("Methodology",
        "Uses a <b>10-day regime window</b> and available 2Y / 5Y / 10Y / 30Y "
        "tenors (6 pairs). 1Y-based pairs are skipped until 1Y data is added. "
        "Neutral threshold: |spread change| < 1.5 bp.")

    render_section_footer(page)
