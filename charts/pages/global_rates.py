"""
charts/pages/global_rates.py
============================
Section 04 — Global Rates (Phase 2: LIVE).

Cross-country yield curve analytics: normalized 10Y overlay, curve snapshots,
2s10s slope ranking, data availability.
"""
from __future__ import annotations
import pandas as pd, numpy as np
import plotly.graph_objects as go
import streamlit as st
from config.pages import get_page
from config.theme import section_color, BG, GRID, TEXT_DIM, DARK_LAYOUT
from charts.common import (
    render_page_header, render_top_tabs, render_kpi_strip,
    render_explanation_box, render_current_reading_box,
    render_model_note, render_section_footer,
)
from models.global_rates import (
    available_country_curves, build_10y_overlay, build_curve_snapshots,
    build_slope_ranking, country_1m_changes, COUNTRY_LABELS, STANDARD_TENORS,
)
from ._context import PageContext

COUNTRY_COLORS = {
    "US": "#ffffff", "DE": "#06b6d4", "JP": "#ef4444",
    "UK": "#22c55e", "CA": "#f97316", "AU": "#a855f7",
}


def render(ctx: PageContext) -> None:
    page = get_page("global_rates")
    render_top_tabs(page["id"])
    from data.loader import latest_valid_date as _lvd
    _ld = _lvd(ctx.df) or ctx.df.index.max()
    latest = _ld.strftime("%b %d, %Y").upper()
    render_page_header(page, latest_date=latest, viewing="Data source: DATA.xlsx / Sheet1")

    countries = available_country_curves(ctx.df)
    if not countries:
        from charts.common import render_data_source_note
        render_data_source_note("DATA.xlsx / Sheet1", latest)
        st.warning("No country curve data found."); render_section_footer(page); return

    changes = country_1m_changes(ctx.df)
    slopes = build_slope_ranking(ctx.df)

    # A. KPI strip
    us_10y = "—"
    if "US" in countries and "10Y" in countries["US"]:
        from config.tickers import TICKERS
        s = ctx.df.get(TICKERS.get("US_10Y", ""), pd.Series(dtype=float)).dropna()
        if len(s): us_10y = f"{s.iloc[-1]:.2f}%"

    top_riser = f"{changes.iloc[0]['label']} ({changes.iloc[0]['change_1m_bp']:+.0f} bp)" if not changes.empty else "—"
    top_faller = f"{changes.iloc[-1]['label']} ({changes.iloc[-1]['change_1m_bp']:+.0f} bp)" if not changes.empty else "—"
    steepest = f"{slopes.iloc[0]['label']} ({slopes.iloc[0]['slope_bp']:+.0f} bp)" if not slopes.empty else "—"

    render_kpi_strip([
        {"label": "US 10Y", "value": us_10y},
        {"label": "Top 1M riser", "value": top_riser, "accent": "#ef4444"},
        {"label": "Top 1M faller", "value": top_faller, "accent": "#22c55e"},
        {"label": "Steepest 2s10s", "value": steepest},
    ])

    render_explanation_box(
        "Global rates overview",
        "Cross-country yield curve comparison for available G6 markets. "
        "The 10Y overlay normalizes each country's yield to its own 1-year "
        "min/max for visual comparison (not a shared y-axis). Slope ranking "
        "sorts by 2s10s steepness.",
    )

    # B. Global 10Y Yield Overlay
    st.markdown("<div style='margin:0.8rem 0 0.3rem;font-size:11px;color:#888;"
                "letter-spacing:0.1em;text-transform:uppercase;'>"
                "Global 10Y yield overlay (normalized to 1Y min/max)</div>",
                unsafe_allow_html=True)

    overlay = build_10y_overlay(ctx.df)
    if not overlay.dropna(how="all").empty:
        fig_ov = go.Figure()
        for c in overlay.columns:
            fig_ov.add_trace(go.Scatter(
                x=overlay.index, y=overlay[c], mode="lines",
                line=dict(color=COUNTRY_COLORS.get(c, "#888"), width=1.4),
                name=COUNTRY_LABELS.get(c, c)))
        fig_ov.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
            font=dict(family="Inter, system-ui, sans-serif", size=10, color=TEXT_DIM),
            height=360, showlegend=True,
            legend=dict(orientation="h", y=1.02, x=0, font=dict(size=10, color="#aaa")),
            margin=dict(l=50, r=20, t=30, b=25),
            yaxis=dict(title="Normalized (0=1Y low, 1=1Y high)", gridcolor=GRID, range=[-0.05, 1.05]),
            xaxis=dict(showgrid=False))
        st.plotly_chart(fig_ov, use_container_width=True, key="gr_overlay", config={"displayModeBar": False})

        # Side table
        if not changes.empty:
            st.dataframe(changes[["label", "yield_10y", "change_1m_bp"]].rename(
                columns={"label": "Country", "yield_10y": "10Y (%)", "change_1m_bp": "1M Δ (bp)"}),
                hide_index=True, use_container_width=True)

    # C. Global Yield Curves
    st.markdown("<div style='margin:1rem 0 0.3rem;font-size:11px;color:#888;"
                "letter-spacing:0.1em;text-transform:uppercase;'>"
                "Global yield curves (latest)</div>", unsafe_allow_html=True)

    snapshots = build_curve_snapshots(ctx.df)
    if not snapshots.empty:
        fig_cs = go.Figure()
        for c in snapshots["country"].unique():
            sub = snapshots[snapshots["country"] == c].sort_values("tenor_num")
            fig_cs.add_trace(go.Scatter(
                x=sub["tenor"], y=sub["yield"], mode="lines+markers",
                line=dict(color=COUNTRY_COLORS.get(c, "#888"), width=1.6),
                marker=dict(size=5),
                name=COUNTRY_LABELS.get(c, c)))
        fig_cs.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
            font=dict(family="Inter, system-ui, sans-serif", size=10, color=TEXT_DIM),
            height=360, showlegend=True,
            legend=dict(orientation="h", y=1.02, x=0, font=dict(size=10, color="#aaa")),
            margin=dict(l=50, r=20, t=30, b=25),
            yaxis=dict(title="Yield (%)", gridcolor=GRID, ticksuffix="%"),
            xaxis=dict(showgrid=False))
        st.plotly_chart(fig_cs, use_container_width=True, key="gr_curves", config={"displayModeBar": False})

    # D. 2s10s Slope Ranking
    st.markdown("<div style='margin:1rem 0 0.3rem;font-size:11px;color:#888;"
                "letter-spacing:0.1em;text-transform:uppercase;'>"
                "2s10s slope ranking</div>", unsafe_allow_html=True)
    if not slopes.empty:
        fig_sl = go.Figure()
        colors = [COUNTRY_COLORS.get(c, "#888") for c in slopes["country"]]
        fig_sl.add_trace(go.Bar(
            y=slopes["label"], x=slopes["slope_bp"], orientation="h",
            marker_color=colors, text=slopes["slope_bp"].apply(lambda x: f"{x:+.0f}"),
            textposition="outside", textfont=dict(size=10, color="#aaa")))
        fig_sl.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
            font=dict(family="Inter, system-ui, sans-serif", size=10, color=TEXT_DIM),
            height=250, margin=dict(l=120, r=60, t=10, b=20),
            xaxis=dict(title="2s10s slope (bp)", gridcolor=GRID, zeroline=True,
                       zerolinecolor="#444"),
            yaxis=dict(showgrid=False, autorange="reversed"))
        st.plotly_chart(fig_sl, use_container_width=True, key="gr_slopes", config={"displayModeBar": False})

    # E. Current Reading
    readings = []
    if not changes.empty:
        readings.append(f"Top 1M 10Y riser: <b>{changes.iloc[0]['label']}</b> ({changes.iloc[0]['change_1m_bp']:+.0f} bp)")
        readings.append(f"Top 1M 10Y faller: <b>{changes.iloc[-1]['label']}</b> ({changes.iloc[-1]['change_1m_bp']:+.0f} bp)")
    if not slopes.empty:
        readings.append(f"Steepest curve: <b>{slopes.iloc[0]['label']}</b> ({slopes.iloc[0]['slope_bp']:+.0f} bp)")
        readings.append(f"Flattest curve: <b>{slopes.iloc[-1]['label']}</b> ({slopes.iloc[-1]['slope_bp']:+.0f} bp)")
        n_inv = int(slopes["inverted"].sum())
        readings.append(f"Inverted curves: <b>{n_inv}</b> of {len(slopes)}")
        us_row = slopes[slopes["country"] == "US"]
        if not us_row.empty:
            peer_median = slopes[slopes["country"] != "US"]["slope_bp"].median()
            us_slope = float(us_row.iloc[0]["slope_bp"])
            readings.append(f"US 2s10s vs peer median: <b>{us_slope:+.0f}</b> vs <b>{peer_median:+.0f}</b> bp")
    if readings:
        render_current_reading_box("Current reading", "<br>".join(readings))

    # F. Data Availability
    with st.expander("Data availability", expanded=False):
        avail_rows = []
        from config.tickers import REGIME_COUNTRIES
        for c in REGIME_COUNTRIES:
            tenors = countries.get(c, [])
            missing = [t for t in STANDARD_TENORS if t not in tenors]
            avail_rows.append({
                "Country": COUNTRY_LABELS.get(c, c),
                "Available": ", ".join(tenors) if tenors else "—",
                "Missing": ", ".join(missing) if missing else "—",
                "In overlay": "✓" if "10Y" in tenors else "✗",
                "In curves": "✓" if len(tenors) >= 2 else "✗",
            })
        st.dataframe(pd.DataFrame(avail_rows), hide_index=True, use_container_width=True)

    from charts.common import render_data_source_note
    render_data_source_note("DATA.xlsx / Sheet1", latest)
    render_section_footer(page)
