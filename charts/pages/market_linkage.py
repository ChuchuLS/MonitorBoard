"""Section 05b — live descriptive cross-asset linkage monitor."""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from charts.common import (
    render_explanation_box,
    render_kpi_strip,
    render_missing_data_warning,
    render_page_header,
    render_section_footer,
    render_top_tabs,
)
from config.pages import get_page
from config.theme import BG, GRID, TEXT_DIM, DARK_LAYOUT
from data.external_loaders import load_ficc
from models.market_linkage import (
    MARKET_LINKAGE_CONFIG,
    all_pair_keys,
    build_market_linkage_current_reading,
    build_market_linkage_snapshot,
    pair_label,
)
from ._context import PageContext


def _fmt(value, spec: str = ".2f", suffix: str = "") -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:{spec}}{suffix}"


def render(ctx: PageContext) -> None:
    page = get_page("market_linkage")
    render_top_tabs(page["id"])

    ficc = load_ficc()
    required = list(MARKET_LINKAGE_CONFIG)
    missing = required if ficc is None else [c for c in required if c not in ficc.columns]
    if ficc is None or missing:
        render_page_header(page, latest_date="—")
        render_missing_data_warning(
            required=[m["ticker"] for m in MARKET_LINKAGE_CONFIG.values()],
            missing=missing,
        )
        render_section_footer(page)
        return

    c1, c2 = st.columns(2)
    with c1:
        corr_window = st.selectbox(
            "Correlation window (common observations)", [10, 20, 30, 42, 63],
            index=1, key="linkage_corr_window",
        )
    with c2:
        history_window = st.selectbox(
            "History shown", [126, 252, 504, 756], index=1,
            key="linkage_history_window",
        )

    snap = build_market_linkage_snapshot(
        ficc, corr_window=int(corr_window), long_window=63
    )
    model_date = snap.get("model_date")
    render_page_header(
        page,
        latest_date=model_date.strftime("%b %d, %Y").upper() if model_date else "—",
        viewing="DATA.xlsx / Sheet1 · five-asset fully aligned calendar",
    )

    render_explanation_box(
        "Five-asset co-movement monitor",
        "Tracks <b>SPX, UST 10Y yield, DXY, BCOM and US high-yield OAS</b>. "
        "Price indices use log returns; the yield and spread use basis-point "
        "changes. All five level series are aligned first, so every pairwise "
        "correlation covers identical timestamps. Correlation is descriptive: "
        "it is not causal attribution, fair value or a forecast.",
    )

    if snap["status"] != "Ready":
        st.warning(
            f"Status: {snap['status']}. Fully aligned observations: "
            f"{snap.get('aligned_observations', 0)}; required for selected window: "
            f"{max(int(corr_window), 63) + 1}."
        )
        render_section_footer(page)
        return

    pos = snap.get("strongest_positive") or {}
    neg = snap.get("strongest_negative") or {}
    render_kpi_strip([
        {
            "label": "Mean |correlation|",
            "value": _fmt(snap.get("mean_abs_correlation")),
            "sub": f"{corr_window}-observation · 10 pairs",
        },
        {
            "label": "Strongest positive",
            "value": _fmt(pos.get("correlation"), "+.2f"),
            "sub": pos.get("label", "—"),
        },
        {
            "label": "Strongest negative",
            "value": _fmt(neg.get("correlation"), "+.2f"),
            "sub": neg.get("label", "—"),
        },
        {
            "label": "Common observations",
            "value": f"{snap['aligned_observations']:,}",
            "sub": f"Since {snap['common_first_date']}",
        },
        {
            "label": "Model date",
            "value": str(model_date),
            "sub": "Latest common five-asset date",
        },
    ])

    st.markdown("#### Latest common-calendar moves")
    moves = snap["moves"].copy()
    display_cols = ["label", "latest_level", "move_1", "move_5", "move_20", "move_63", "unit"]
    move_disp = moves[display_cols].rename(columns={
        "label": "Asset", "latest_level": "Latest level", "move_1": "1D move",
        "move_5": "5D move", "move_20": "20D move", "move_63": "63D move",
        "unit": "Move unit",
    })
    st.dataframe(
        move_disp.style.format({
            "Latest level": "{:.3f}", "1D move": "{:+.2f}",
            "5D move": "{:+.2f}", "20D move": "{:+.2f}", "63D move": "{:+.2f}",
        }, na_rep="—"), hide_index=True, use_container_width=True,
    )
    st.caption(
        "SPX, DXY and BCOM moves are log returns in percent. UST 10Y and US HY "
        "OAS moves are changes in basis points. Missing values are not replaced by zero."
    )

    st.markdown("#### Current correlation matrix")
    matrix = snap["correlation_matrix"]
    fig_h = go.Figure(go.Heatmap(
        z=matrix.values, x=matrix.columns, y=matrix.index,
        zmin=-1, zmax=1, colorscale="RdBu", reversescale=True,
        text=np.round(matrix.values, 2), texttemplate="%{text:.2f}",
        colorbar=dict(title="Corr"), hovertemplate="%{y} vs %{x}: %{z:.3f}<extra></extra>",
    ))
    fig_h.update_layout(**DARK_LAYOUT, height=430, margin=dict(l=20, r=20, t=20, b=30))
    st.plotly_chart(fig_h, use_container_width=True, key="linkage_matrix",
                    config={"displayModeBar": False})

    corr_hist = snap["correlation_history"].tail(int(history_window))
    pair_options = all_pair_keys()
    defaults = [
        "SPX_vs_USGG10YR", "SPX_vs_DXY", "SPX_vs_LF98OAS", "DXY_vs_BCOM",
    ]
    selected = st.multiselect(
        "Pairs shown in rolling history",
        options=pair_options,
        default=[p for p in defaults if p in pair_options],
        format_func=pair_label,
        key="linkage_pairs",
    )
    st.markdown("#### Rolling pairwise correlations")
    fig_c = go.Figure()
    for key in selected:
        fig_c.add_trace(go.Scatter(
            x=corr_hist.index, y=corr_hist[key], mode="lines",
            name=pair_label(key), line=dict(width=1.3),
        ))
    fig_c.add_hline(y=0, line=dict(color="#555", width=0.7, dash="dot"))
    fig_c.update_layout(
        height=360, template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(size=10, color=TEXT_DIM), hovermode="x unified",
        margin=dict(l=50, r=20, t=25, b=30),
        yaxis=dict(title="Correlation", range=[-1, 1], gridcolor=GRID),
        xaxis=dict(showgrid=False), legend=dict(orientation="h", y=1.08, x=0),
    )
    st.plotly_chart(fig_c, use_container_width=True, key="linkage_corr_history",
                    config={"displayModeBar": False})

    st.markdown("#### Cross-asset integration history")
    integ = snap["integration_history"].tail(int(history_window))
    fig_i = go.Figure()
    fig_i.add_trace(go.Scatter(
        x=integ.index, y=integ["mean_abs_corr"], mode="lines",
        name="Mean absolute pair correlation", line=dict(width=1.7),
    ))
    fig_i.add_trace(go.Scatter(
        x=integ.index, y=integ["max_abs_corr"], mode="lines",
        name="Maximum absolute pair correlation", line=dict(width=1.0, dash="dot"),
    ))
    fig_i.update_layout(
        height=300, template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(size=10, color=TEXT_DIM), hovermode="x unified",
        margin=dict(l=50, r=20, t=25, b=30),
        yaxis=dict(title="Absolute correlation", range=[0, 1], gridcolor=GRID),
        xaxis=dict(showgrid=False), legend=dict(orientation="h", y=1.08, x=0),
    )
    st.plotly_chart(fig_i, use_container_width=True, key="linkage_integration",
                    config={"displayModeBar": False})

    reading = build_market_linkage_current_reading(
        ficc, corr_window=int(corr_window), long_window=63
    )
    st.markdown("#### Current reading")
    st.info(reading.get("summary", "No current reading available."))
    st.caption(reading.get("methodology_note", ""))

    with st.expander("Methodology and limitations", expanded=False):
        st.markdown(
            "- The five raw level series are intersected before daily moves are calculated.\n"
            "- SPX, DXY and BCOM use log returns; UST 10Y and HY OAS use basis-point changes.\n"
            "- The matrix and history use Pearson correlation over the selected common-observation window.\n"
            "- Mean absolute correlation summarizes co-movement strength across all ten pairs.\n"
            "- It is not a systemic-risk score, causal attribution, fair-value model or forecast.\n"
            "- The separate 05c PCA page remains Experimental."
        )

    render_section_footer(page)
