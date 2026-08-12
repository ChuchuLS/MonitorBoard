"""05b — PDF-aligned Market Linkage & Correlations."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from charts.common import (
    render_current_reading_list,
    render_data_source_note,
    render_explanation_box,
    render_kpi_strip,
    render_missing_data_warning,
    render_model_note,
    render_page_header,
    render_section_footer,
    render_top_tabs,
)
from config.pages import get_page
from config.theme import BG, GRID, TEXT_DIM, section_color
from data.external_loaders import load_crossasset
from models.market_linkage import (
    MARKET_LINKAGE_CONFIG,
    all_pair_keys,
    build_market_linkage_current_reading,
    build_market_linkage_snapshot,
    pair_label,
)
from ._context import PageContext

PAIR_COLORS = {
    "SPX_vs_USGG10YR": "#60a5fa",
    "SPX_vs_DXY": "#f97316",
    "USGG10YR_vs_DXY": "#2dd4bf",
}


def _fmt(v, fmt=".2f", suffix=""):
    if v is None or pd.isna(v):
        return "—"
    return f"{v:{fmt}}{suffix}"


def render(ctx: PageContext) -> None:
    page = get_page("market_linkage")
    render_top_tabs(page["id"])

    # ``ctx.df`` retains Bloomberg ticker names (SPX INDEX, USGG10YR INDEX,
    # DXY CURNCY), while the linkage model deliberately works with the shared
    # canonical cross-asset names (SPX, USGG10YR, DXY).  Use the same loader as
    # the preceding Cross-Asset page so the live page and exports receive the
    # identical, normalized three-series frame.
    model_df = load_crossasset()
    if model_df is None:
        model_df = pd.DataFrame(columns=list(MARKET_LINKAGE_CONFIG))

    snap = build_market_linkage_snapshot(model_df, corr_window=20, long_window=63)
    if snap.get("status") == "Missing data":
        render_page_header(page, latest_date="—")
        render_missing_data_warning(
            required=[m["ticker"] for m in MARKET_LINKAGE_CONFIG.values()],
            missing=snap.get("missing", []),
        )
        render_section_footer(page)
        return

    model_date = snap.get("model_date")
    render_page_header(
        page,
        latest_date=str(model_date or "—").upper(),
        viewing=(
            f"SPX / UST 10Y / DXY · 63D linkage gauge · "
            f"20D pairwise correlations"
        ),
    )
    render_explanation_box(
        "One-trade gauge — aligned to the reference chart pack",
        "SPX, UST 10Y and DXY are aligned on one calendar before daily moves "
        "are calculated. The main line is the share of total standardized "
        "three-asset variance explained by the first principal component over "
        "63 observations. <b>Higher = the three markets are moving more like "
        "one macro trade; lower = they are trading more independently.</b> "
        "The measure is descriptive and is not converted into a categorical regime label.",
    )

    if snap.get("status") != "Ready":
        st.warning(
            f"Status: {snap.get('status')}; aligned observations: "
            f"{snap.get('aligned_observations', 0)}."
        )
        render_section_footer(page)
        return

    latest_corrs = snap.get("latest_correlations", {})
    render_kpi_strip([
        {
            "label": "Market linkage",
            "value": _fmt(snap.get("pc1_explained_variance"), ".1%"),
            "sub": "PC1 share of total variance · 63D",
            "accent": section_color(page["color_key"]),
        },
        {
            "label": "2Y percentile",
            "value": _fmt(snap.get("linkage_percentile_2y"), ".0f", " / 100"),
            "sub": "within latest 504 valid readings",
        },
        {
            "label": "SPX / UST 10Y",
            "value": _fmt(latest_corrs.get("SPX_vs_USGG10YR"), "+.2f"),
            "sub": "20D correlation",
        },
        {
            "label": "SPX / DXY",
            "value": _fmt(latest_corrs.get("SPX_vs_DXY"), "+.2f"),
            "sub": "20D correlation",
        },
        {
            "label": "UST 10Y / DXY",
            "value": _fmt(latest_corrs.get("USGG10YR_vs_DXY"), "+.2f"),
            "sub": "20D correlation",
        },
        {
            "label": "Avg abs correlation",
            "value": _fmt(snap.get("mean_abs_correlation"), ".2f"),
            "sub": "three pairwise correlations",
        },
    ])

    gauge = snap.get("linkage_history", pd.Series(dtype=float))
    if not gauge.empty:
        st.markdown("#### Market linkage — one-trade gauge")
        fig = go.Figure(go.Scatter(
            x=gauge.index,
            y=100.0 * gauge,
            mode="lines",
            line=dict(color="#b184ff", width=1.8),
            name="PC1 explained variance",
            hovertemplate=(
                "%{x|%Y-%m-%d}<br>Common-movement gauge: "
                "%{y:.1f}%<extra></extra>"
            ),
        ))
        fig.update_layout(
            template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
            font=dict(family="Inter, system-ui, sans-serif", size=10, color=TEXT_DIM),
            height=330, showlegend=False, margin=dict(l=55, r=20, t=20, b=30),
            yaxis=dict(title="PC1 explained variance (%)", gridcolor=GRID,
                       range=[max(0, float((100*gauge).min())-5), 100]),
            xaxis=dict(showgrid=False),
        )
        st.plotly_chart(fig, use_container_width=True, key="market_linkage_gauge",
                        config={"displayModeBar": False})

    corrs = snap.get("correlation_history", pd.DataFrame())
    if not corrs.empty:
        st.markdown("#### Rolling pairwise correlations")
        fig_c = go.Figure()
        for key in all_pair_keys():
            if key not in corrs.columns:
                continue
            fig_c.add_trace(go.Scatter(
                x=corrs.index, y=corrs[key], mode="lines",
                name=pair_label(key),
                line=dict(color=PAIR_COLORS.get(key, "#888"), width=1.3),
                hovertemplate=(
                    f"<b>{pair_label(key)}</b><br>"
                    "%{x|%Y-%m-%d}: %{y:+.2f}<extra></extra>"
                ),
            ))
        fig_c.add_hline(y=0, line=dict(color="#444", width=0.6, dash="dot"))
        fig_c.update_layout(
            template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
            font=dict(family="Inter, system-ui, sans-serif", size=10, color=TEXT_DIM),
            height=330, hovermode="x unified", margin=dict(l=55, r=20, t=20, b=30),
            yaxis=dict(title="20D correlation", gridcolor=GRID, range=[-1, 1]),
            xaxis=dict(showgrid=False),
            legend=dict(orientation="h", y=1.1, x=0),
        )
        st.plotly_chart(fig_c, use_container_width=True, key="market_linkage_corrs",
                        config={"displayModeBar": False})

    reading = build_market_linkage_current_reading(
        model_df, corr_window=20, long_window=63
    )
    render_current_reading_list(
        "Current reading",
        [
            ("Model date", str(model_date or "—")),
            ("Market linkage", _fmt(snap.get("pc1_explained_variance"), ".1%")),
            ("2Y percentile", _fmt(snap.get("linkage_percentile_2y"), ".0f", " / 100")),
            ("SPX / UST 10Y", _fmt(latest_corrs.get("SPX_vs_USGG10YR"), "+.2f")),
            ("SPX / DXY", _fmt(latest_corrs.get("SPX_vs_DXY"), "+.2f")),
            ("UST 10Y / DXY", _fmt(latest_corrs.get("USGG10YR_vs_DXY"), "+.2f")),
        ],
    )
    st.caption(reading.get("summary", ""))

    render_model_note(
        "Methodology",
        "<b>Universe:</b> SPX log return, UST 10Y yield change in bp, and DXY "
        "log return. <b>Calendar:</b> the three level series are aligned first; "
        "daily moves therefore cover identical timestamps. <b>Linkage:</b> "
        "rolling 63-observation PCA on standardized daily moves; displayed value "
        "is PC1 explained variance. <b>Correlations:</b> rolling 20-observation "
        "Pearson correlations. This follows the structure of the reference PDF's "
        "Market Linkage page and does not classify a categorical linkage regime.",
    )
    render_data_source_note("DATA.xlsx / Sheet1", str(model_date or "—"))
    render_section_footer(page)
