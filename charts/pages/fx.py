"""
charts/pages/fx.py
==================
Section 06 — FX (Phase 2: LIVE with fx-complex PCA).

Integrates the DXY / EM FX / USDJPY basis PCA from market-reading.
Falls back to XCCY basis preview if FICC columns are missing from DATA.xlsx.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config.pages import get_page
from config.theme import section_color, BG, GRID, TEXT_DIM, DARK_LAYOUT

from charts.common import (
    render_page_header, render_top_tabs, render_kpi_strip,
    render_explanation_box, render_missing_data_warning, render_section_footer,
)
from charts.funding import render_xccy
from data.external_loaders import load_ficc

from ._context import PageContext


def _build_fx_regime(prices: pd.DataFrame, window: int = 60):
    from models.fx_complex.analytics import (
        ASSETS, ASSET_LABELS, compute_returns, rolling_pairwise_corrs,
        rolling_pca_loadings,
    )
    from models.fx_complex.regime import (
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

    return {
        "loadings": loadings, "regime": regime, "persistence": persistence,
        "corrs": corrs, "runs": runs, "stats": stats, "info": info,
    }, []


def render(ctx: PageContext) -> None:
    page = get_page("fx")

    render_top_tabs(page["id"])

    ficc = load_ficc()
    if ficc is not None:
        latest = ficc.index.max().strftime("%b %d, %Y").upper()
        render_page_header(page, latest_date=latest,
                           viewing="Data source: DATA.xlsx")
    else:
        render_page_header(page, latest_date="—",
                           viewing="Required FICC columns not found in DATA.xlsx")

    render_explanation_box(
        "FX within-complex PCA",
        "A rolling PCA on <b>DXY / EM FX (FXJPEMCS) / USDJPY 12M xccy basis</b> "
        "extracts the dominant dollar theme. PC1 is anchored so a positive DXY "
        "loading = 'USD stronger'. The regime classification tells you whether "
        "the dollar move is broad-based or concentrated in EM vs G10, and "
        "whether it's accompanied by funding-market stress (basis widening).",
    )

    ficc = load_ficc()
    if ficc is None:
        render_missing_data_warning(
            required=["DATA.xlsx Sheet1 with DXY, FXJPEMCS, JYBSS12M"],
            missing=["FICC columns not found in DATA.xlsx"],
            message="The FX PCA model requires DXY, FXJPEMCS, JYBSS12M columns in DATA.xlsx.",
        )
    else:
        from models.fx_complex.analytics import ASSETS, ASSET_LABELS
        window = st.selectbox("PCA window (days)", [30, 60, 90], index=1,
                              key="fx_window")
        result, missing_cols = _build_fx_regime(ficc, window=window)
        if missing_cols:
            render_missing_data_warning(
                required=[ASSET_LABELS.get(a, a) for a in ASSETS],
                missing=[ASSET_LABELS.get(a, a) for a in missing_cols],
            )
        elif result is None:
            st.warning("Insufficient data for the selected window.")
        else:
            info = result["info"]
            from models.fx_complex.regime import regime_color as _rc
            regime_name = info.get("regime", "—")

            render_kpi_strip([
                {"label": "FX regime", "value": regime_name,
                 "sub": f"Since {info.get('since', '—')} · {info.get('days_in', 0)} days",
                 "accent": _rc(regime_name)},
                {"label": "DXY loading", "value": f"{info.get('dxy_load', 0):+.2f}"},
                {"label": "EM FX loading",
                 "value": f"{info.get('fxjpemcs_load', info.get('emfx_load', 0)):+.2f}"},
                {"label": "PC1 explained var", "value": f"{info.get('expvar', 0):.0%}"},
            ])

            # Regime timeline
            from models.fx_complex.regime import regime_color
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
            st.plotly_chart(fig, use_container_width=True, key="fx_timeline",
                            config={"displayModeBar": False})

            # Regime stats
            with st.expander("FX regime statistics", expanded=False):
                stats = result["stats"]
                disp = stats[["Regime", "Days", "Pct", "Runs", "AvgRun", "Active"]].copy()
                disp["Pct"] = disp["Pct"].round(1).astype(str) + "%"
                disp["AvgRun"] = disp["AvgRun"].round(1)
                st.dataframe(disp, hide_index=True, use_container_width=True)

    # XCCY basis preview
    st.markdown("<div style='margin:1.3rem 0 0.4rem;font-size:11px;color:#888;"
                "letter-spacing:0.1em;text-transform:uppercase;'>"
                "XCCY basis (from main dataset)</div>", unsafe_allow_html=True)
    render_xccy(ctx.dff)

    render_section_footer(page)
