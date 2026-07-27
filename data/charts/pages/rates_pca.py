"""
charts/pages/rates_pca.py
=========================
Section 02b — Rates Complex PCA (experimental).

Within-rates PCA on UST 10Y / 2s10s / 10Y breakeven / 10Y real yield / MOVE.
EXPLICITLY labelled as experimental — this is NOT the PDF-style nominal = real
+ inflation decomposition. Section 02 is now live with the breakeven identity model.
Uses DATA.xlsx / Sheet1 FICC columns.
"""

from __future__ import annotations

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
from data.external_loaders import load_ficc

from ._context import PageContext


def _build_rates_regime(prices, window=60):
    from models.rates_complex.analytics import (
        ASSETS, compute_returns, rolling_pairwise_corrs, rolling_pca_loadings,
        headline_vs_breadth,
    )
    from models.rates_complex.regime import (
        classify_loadings_series, cosine_persistence,
        apply_persistence_filter, regime_runs, regime_stats,
        current_regime_info,
    )
    from models.shared.data_utils import drop_all_zero_return_rows

    missing = [a for a in ASSETS if a not in prices.columns]
    if missing:
        return None, missing

    rets = compute_returns(prices)
    rets, _ = drop_all_zero_return_rows(rets)
    if len(rets) < window + 10:
        return None, []

    corrs = rolling_pairwise_corrs(rets, window=window)
    loadings = rolling_pca_loadings(rets, window=window)
    raw_regime = classify_loadings_series(loadings)
    persistence = cosine_persistence(loadings)
    regime = apply_persistence_filter(raw_regime, persistence)
    runs = regime_runs(regime)
    stats = regime_stats(regime)
    info = current_regime_info(regime, loadings, persistence)
    hvb = headline_vs_breadth(rets)

    return {
        "loadings": loadings, "regime": regime, "persistence": persistence,
        "corrs": corrs, "runs": runs, "stats": stats, "info": info, "hvb": hvb,
    }, []


def render(ctx: PageContext) -> None:
    page = get_page("rates_pca")

    render_top_tabs(page["id"])
    from charts.common import render_experimental_badge
    render_experimental_badge()

    ficc = load_ficc()
    if ficc is None:
        render_page_header(page, latest_date="—")
        render_missing_data_warning(
            required=["DATA.xlsx Sheet1 with FICC columns"],
            missing=["Required FICC columns not found in DATA.xlsx"],
        )
        render_section_footer(page)
        return

    data_latest = ficc.index.max().strftime("%b %d, %Y").upper()
    render_page_header(page, latest_date=data_latest,
                       viewing="Data source: DATA.xlsx / Sheet1 FICC columns")

    render_explanation_box(
        "Within-rates PCA",
        "A rolling PCA on 5 rates sub-components — <b>UST 10Y, 2s10s slope, "
        "10Y breakeven, 10Y real yield, MOVE vol</b>. PC1 loadings show "
        "which sub-component is leading the rates move. The headline-vs-breadth "
        "diagnostic tells you if the 10Y headline is confirmed by the rest.",
    )

    render_model_note(
        "This is NOT the rate decomposition",
        "The PDF-style rate decomposition (nominal = real + inflation, identity "
        "form) is Section 02. This page is a separate <b>experimental PCA regime "
        "model</b> — it measures co-movement structure, not additive "
        "nominal = real + inflation attribution.",
    )

    from models.rates_complex.analytics import ASSETS, ASSET_LABELS
    window = st.selectbox("PCA window (days)", [30, 60, 90], index=1, key="rpca_window")
    result, missing_cols = _build_rates_regime(ficc, window=window)

    if missing_cols:
        render_missing_data_warning(
            required=[ASSET_LABELS.get(a, a) for a in ASSETS],
            missing=[ASSET_LABELS.get(a, a) for a in missing_cols],
        )
    elif result is None:
        st.warning("Insufficient data.")
    else:
        info = result["info"]
        from models.rates_complex.regime import regime_color as _rc
        regime_name = info.get("regime", "—")

        render_kpi_strip([
            {"label": "Rates PCA regime", "value": regime_name,
             "sub": f"Since {info.get('since', '—')} · {info.get('days_in', 0)} days",
             "accent": _rc(regime_name)},
            {"label": "PC1 explained var", "value": f"{info.get('expvar', 0):.0%}"},
            {"label": "Persistence",
             "value": f"{info.get('persistence', 0):.2f}" if info.get('persistence') else "—"},
        ])

        # Regime timeline
        from models.rates_complex.regime import regime_color
        runs = result["runs"]
        fig = go.Figure()
        for _, row in runs.iterrows():
            c = regime_color(row["Regime"])
            fig.add_trace(go.Scatter(
                x=[row["Start"], row["End"]], y=[0.5, 0.5],
                mode="lines", line=dict(color=c, width=28),
                hovertext=f"{row['Regime']}<br>{row['Duration']}d",
                hoverinfo="text", showlegend=False))
        fig.update_layout(**DARK_LAYOUT, height=100,
                          margin=dict(l=10, r=10, t=5, b=20),
                          yaxis=dict(visible=False, range=[0, 1]),
                          xaxis=dict(showgrid=False, tickfont=dict(size=10)))
        st.plotly_chart(fig, use_container_width=True, key="rpca_timeline",
                        config={"displayModeBar": False})

        # Headline vs breadth
        hvb = result.get("hvb")
        if hvb is not None and len(hvb):
            fig_hvb = go.Figure()
            for col in hvb.columns:
                fig_hvb.add_trace(go.Scatter(
                    x=hvb.index, y=hvb[col], mode="lines", line=dict(width=1.2), name=col))
            fig_hvb.add_hline(y=0, line=dict(color="#333", width=0.5, dash="dot"))
            fig_hvb.update_layout(
                height=260, template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
                font=dict(family="Inter, system-ui, sans-serif", size=10, color=TEXT_DIM),
                hovermode="x unified", showlegend=True,
                legend=dict(orientation="h", y=1.02, x=0, font=dict(size=10, color="#aaa")),
                margin=dict(l=50, r=20, t=30, b=25),
                yaxis=dict(gridcolor=GRID), xaxis=dict(showgrid=False))
            st.plotly_chart(fig_hvb, use_container_width=True, key="rpca_hvb",
                            config={"displayModeBar": False})

        with st.expander("Rates PCA regime statistics", expanded=False):
            stats = result["stats"]
            disp = stats[["Regime", "Days", "Pct", "Runs", "AvgRun", "Active"]].copy()
            disp["Pct"] = disp["Pct"].round(1).astype(str) + "%"
            disp["AvgRun"] = disp["AvgRun"].round(1)
            st.dataframe(disp, hide_index=True, use_container_width=True)

    render_section_footer(page)
