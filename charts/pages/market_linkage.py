"""
charts/pages/market_linkage.py
==============================
Section 05b — Market Linkage & Correlations (PCA regime model).

This is the PCA-based 4-regime relative classification from market-reading,
EXPLICITLY labelled as experimental and distinct from the PDF-reference
8-regime directional timeline (Section 05). Uses DATA.xlsx / Sheet1 cross-asset columns.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config.pages import get_page
from config.theme import section_color, BG, GRID, TEXT_DIM, DARK_LAYOUT

from charts.common import (
    render_page_header, render_top_tabs, render_kpi_strip,
    render_explanation_box, render_model_note,
    render_missing_data_warning, render_section_footer,
)
from data.external_loaders import load_crossasset

from ._context import PageContext


def _build_regime(prices, pca_window=63, corr_window=20):
    from models.cross_asset.analytics import (
        compute_returns, rolling_pairwise_corrs, rolling_pca_loadings,
    )
    from models.cross_asset.regime import (
        classify_loadings_series, cosine_persistence,
        apply_persistence_filter, regime_runs, regime_stats,
        current_regime_info, BUCKET_COLOR,
    )
    from models.shared.data_utils import drop_all_zero_return_rows

    rets = compute_returns(prices)
    rets, _ = drop_all_zero_return_rows(rets)
    if len(rets) < pca_window + 10:
        return None

    corrs = rolling_pairwise_corrs(rets, window=corr_window)
    loadings = rolling_pca_loadings(rets, window=pca_window)
    raw_regime = classify_loadings_series(loadings)
    persistence = cosine_persistence(loadings)
    regime = apply_persistence_filter(raw_regime, persistence)
    runs = regime_runs(regime)
    stats = regime_stats(regime)
    info = current_regime_info(regime, loadings, persistence)

    return {
        "loadings": loadings, "regime": regime, "persistence": persistence,
        "corrs": corrs, "runs": runs, "stats": stats, "info": info,
    }


def render(ctx: PageContext) -> None:
    page = get_page("market_linkage")
    color = section_color(page["color_key"])

    render_top_tabs(page["id"])

    prices = load_crossasset()
    if prices is None or "SPX" not in prices.columns:
        render_page_header(page, latest_date="—")
        render_missing_data_warning(
            required=["DATA.xlsx Sheet1 with SPX, USGG10YR, DXY"],
            missing=["Required cross-asset columns not found in DATA.xlsx"],
        )
        render_section_footer(page)
        return

    # Clean prices to valid observations
    prices = prices[["SPX", "USGG10YR", "DXY"]].dropna()
    if len(prices) < 70:
        render_page_header(page, latest_date="—")
        st.warning("Insufficient data.")
        render_section_footer(page); return

    model_latest = prices.index.max().strftime("%b %d, %Y").upper()
    render_page_header(page, latest_date=model_latest,
                       viewing="Data source: DATA.xlsx / Sheet1 cross-asset columns")

    render_explanation_box(
        "PCA-based dominant-theme extraction",
        "A rolling PCA on <b>SPX / UST 10Y / DXY</b> daily returns. "
        "Default: <b>63-day PCA window</b> for regime classification, "
        "<b>20-day rolling window</b> for pairwise correlations. "
        "PC1 loadings classify each day into 4 relative regimes based on "
        "whether bonds and dollar move <i>with</i> or <i>against</i> equities. "
        "This is a <b>different model</b> from the 8-regime directional "
        "timeline on the previous page — it captures the strength and "
        "stability of co-movement, not just the signs.",
    )

    mc1, mc2 = st.columns(2)
    with mc1:
        pca_window = st.selectbox("PCA window (days)", [30, 42, 63, 90, 126],
                                  index=2, key="ml_pca_window")
    with mc2:
        corr_window = st.selectbox("Correlation window (days)", [10, 20, 30, 42, 63],
                                   index=1, key="ml_corr_window")

    result = _build_regime(prices, pca_window=pca_window, corr_window=corr_window)
    if result is None:
        st.warning("Insufficient data for the selected window.")
        render_section_footer(page)
        return

    info = result["info"]
    from models.cross_asset.regime import BUCKET_COLOR

    regime_name = info.get("regime", "—")
    regime_color = BUCKET_COLOR.get(regime_name, "#525252")
    render_kpi_strip([
        {"label": "PCA regime", "value": regime_name,
         "sub": f"Since {info.get('since', '—')} · {info.get('days_in', 0)} days",
         "accent": regime_color},
        {"label": "SPX loading", "value": f"{info.get('spx_load', 0):+.2f}"},
        {"label": "UST 10Y loading", "value": f"{info.get('ust_load', 0):+.2f}"},
        {"label": "DXY loading", "value": f"{info.get('dxy_load', 0):+.2f}"},
        {"label": "PC1 explained var", "value": f"{info.get('expvar', 0):.0%}"},
    ])

    # Regime timeline
    legend_bits = " &nbsp;&nbsp; ".join(
        f"<span style='display:inline-block;width:10px;height:10px;"
        f"background:{BUCKET_COLOR[r]};vertical-align:middle;"
        f"margin-right:4px;border-radius:2px;'></span>"
        f"<span style='color:#aaa;font-size:10px;'>{r}</span>"
        for r in ["Risk-on / Growth reflation", "Goldilocks / Duration-led risk-on",
                   "Inflation / Rates pressure", "Defensive / Dollar squeeze",
                   "Mixed", "Transitioning"]
    )
    st.markdown(f"<div style='margin:0.6rem 0 6px;'>{legend_bits}</div>",
                unsafe_allow_html=True)

    runs = result["runs"]
    fig = go.Figure()
    for _, row in runs.iterrows():
        c = BUCKET_COLOR.get(row["Regime"], "#525252")
        fig.add_trace(go.Scatter(
            x=[row["Start"], row["End"]], y=[0.5, 0.5],
            mode="lines", line=dict(color=c, width=28),
            hovertext=f"{row['Regime']}<br>{row['Duration']}d",
            hoverinfo="text", showlegend=False))
    fig.update_layout(**DARK_LAYOUT, height=100,
                      margin=dict(l=10, r=10, t=5, b=20),
                      yaxis=dict(visible=False, range=[0, 1]),
                      xaxis=dict(showgrid=False, tickfont=dict(size=10)))
    st.plotly_chart(fig, use_container_width=True, key="ml_timeline",
                    config={"displayModeBar": False})

    # Rolling correlations
    corrs = result["corrs"]
    PAIR_COLORS = {"SPX_vs_USGG10YR": "#ec4899", "SPX_vs_DXY": "#06b6d4",
                   "USGG10YR_vs_DXY": "#fb923c"}
    PAIR_LABELS = {"SPX_vs_USGG10YR": "SPX vs UST 10Y", "SPX_vs_DXY": "SPX vs DXY",
                   "USGG10YR_vs_DXY": "UST 10Y vs DXY"}
    fig_c = go.Figure()
    for col in corrs.columns:
        if col in PAIR_COLORS:
            fig_c.add_trace(go.Scatter(
                x=corrs.index, y=corrs[col], mode="lines",
                line=dict(color=PAIR_COLORS[col], width=1.2),
                name=PAIR_LABELS.get(col, col)))
    fig_c.add_hline(y=0, line=dict(color="#333", width=0.5, dash="dot"))
    fig_c.update_layout(
        height=300, template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(family="Inter, system-ui, sans-serif", size=10, color=TEXT_DIM),
        hovermode="x unified", showlegend=True,
        legend=dict(orientation="h", y=1.02, x=0, font=dict(size=10, color="#aaa")),
        margin=dict(l=50, r=20, t=40, b=25),
        yaxis=dict(title="Correlation", gridcolor=GRID, range=[-1, 1]),
        xaxis=dict(showgrid=False))
    st.plotly_chart(fig_c, use_container_width=True, key="ml_corrs",
                    config={"displayModeBar": False})

    with st.expander("PCA regime statistics", expanded=False):
        stats = result["stats"]
        disp = stats[["Regime", "Days", "Pct", "Runs", "AvgRun", "Active"]].copy()
        disp["Pct"] = disp["Pct"].round(1).astype(str) + "%"
        disp["AvgRun"] = disp["AvgRun"].round(1)
        st.dataframe(disp, hide_index=True, use_container_width=True)

    render_section_footer(page)
