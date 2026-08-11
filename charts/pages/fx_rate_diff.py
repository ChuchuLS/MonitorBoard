"""charts/pages/fx_rate_diff.py — 06 · FX Rate Differential Monitor
No zero fallbacks. Partial pairs show diagnostic info only."""
from __future__ import annotations
import logging
import pandas as pd, numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st
from config.pages import get_page
from config.theme import section_color, BG, GRID, TEXT_DIM
from charts.funding import render_xccy
from charts.common import (
    render_page_header, render_top_tabs, render_kpi_strip,
    render_explanation_box, render_current_reading_list,
    render_model_note, render_missing_data_warning,
    render_section_footer, render_data_source_note,
)
from models.fx_rate_differential import (
    FX_PAIR_CONFIG, REQUIRED_ANALYTICAL_COLUMNS,
    FLAT_FX_THRESHOLD, FLAT_DIFF_THRESHOLD,
    available_fx_pairs, build_fx_pair_data, build_fx_pair_snapshot,
    build_fx_linkage_table, build_fx_rolling_correlations,
    build_fx_current_reading, build_all_fx_snapshots,
)
from ._context import PageContext
logger = logging.getLogger(__name__)

PAIR_COLORS = {"EURUSD": "#06b6d4", "USDJPY": "#ef4444", "GBPUSD": "#22c55e", "AUDUSD": "#f97316"}

def _fmt(v, fmt="+.2f", suffix="", missing="—"):
    if v is None or (isinstance(v, float) and np.isnan(v)): return missing
    return f"{v:{fmt}}{suffix}"



def _render_xccy_dashboard(ctx: PageContext) -> None:
    st.markdown("<div style='height:0.8rem;'></div>", unsafe_allow_html=True)
    st.markdown("#### Cross-Currency Basis Swaps")
    st.caption(
        "EUR / JPY / AUD / GBP / CAD 3M and 12M basis history. "
        "Negative values indicate a USD funding premium; source series are shown descriptively."
    )
    try:
        render_xccy(ctx.dff, key_prefix="fx_rates_xccy")
    except Exception as exc:
        logger.exception("Failed to render the FX XCCY basis dashboard")
        st.warning(
            "Cross-Currency Basis charts are unavailable because rendering failed "
            f"({type(exc).__name__}). The underlying data are not treated as zero."
        )


def render(ctx: PageContext) -> None:
    page = get_page("fx_rate_diff")
    render_top_tabs(page["id"])
    all_snaps = {p: build_fx_pair_snapshot(ctx.df, p) for p in FX_PAIR_CONFIG}
    ready_dates = [s.get("common_latest_date") or s.get("model_date")
                   for s in all_snaps.values() if s.get("status") == "Ready"]
    page_date = str(max(ready_dates)) if ready_dates else "—"
    render_page_header(page, latest_date=page_date.upper(),
        viewing="FX model dates by pair (not raw workbook date)")

    render_explanation_box("FX Rate Differential Monitor",
        "Tracks four selected major FX pairs against 2Y nominal, 10Y nominal, and 10Y real "
        "yield differentials. Requires ALL four inputs (spot + 3 differentials) "
        "for Ready status. Rolling correlations are <b>descriptive</b>.")

    overview = build_all_fx_snapshots(ctx.df)
    if not overview.empty:
        st.dataframe(overview, hide_index=True, use_container_width=True)

    sel = st.selectbox("Select pair", list(FX_PAIR_CONFIG.keys()), key="fx_pair_sel")
    cfg = FX_PAIR_CONFIG[sel]
    snap = all_snaps[sel]
    avail = available_fx_pairs(ctx.df)
    readiness = avail[sel]

    # Handle non-Ready pairs
    if snap.get("status") != "Ready":
        st.markdown(f"<div style='margin:0.8rem 0;padding:10px 14px;border-left:2px solid #d99830;"
                    f"background:#1a1500;border-radius:4px;font-size:12px;color:#ccc;'>"
                    f"<b>{sel}</b> status: <b>{snap.get('status','—')}</b><br>"
                    f"Missing fields: {', '.join(readiness.get('missing', [])) or 'None'}<br>"
                    f"Reason: {readiness.get('reason', 'Unknown')}<br>"
                    f"Aligned observations: {readiness.get('aligned_obs', 0)}<br>"
                    f"Raw dates: {readiness.get('raw_dates', {})}"
                    f"</div>", unsafe_allow_html=True)
        _render_xccy_dashboard(ctx)
        render_section_footer(page); return

    aligned = build_fx_pair_data(ctx.df, sel)
    reading = build_fx_current_reading(ctx.df, sel)
    pair_date = str(snap["common_latest_date"])

    # KPI strip — no zero fallbacks
    kpis = [
        {"label": f"{sel} Spot", "value": _fmt(snap.get("spot"), ".4f"),
         "sub": cfg["spot_convention"], "accent": PAIR_COLORS.get(sel, "#888")},
        {"label": "20D FX return", "value": _fmt(snap.get("fx_return_20d_pct"), "+.2f", "%")},
        {"label": "2Y diff", "value": _fmt(snap.get("nom_2y_diff_bp"), "+.0f", " bp"),
         "sub": cfg["differential_direction"]},
        {"label": "10Y diff", "value": _fmt(snap.get("nom_10y_diff_bp"), "+.0f", " bp")},
        {"label": "10Y real diff", "value": _fmt(snap.get("real_10y_diff_bp"), "+.0f", " bp")},
        {"label": "Model date", "value": pair_date,
         "sub": f"{snap['aligned_obs']} aligned obs"},
    ]
    render_kpi_strip(kpis)

    # Charts — aligned frame only
    if not aligned.empty:
        for diff_col, diff_label, color in [
            ("nom_2y_diff", "2Y Nominal Diff (bp)", "#eab308"),
            ("nom_10y_diff", "10Y Nominal Diff (bp)", "#a855f7"),
            ("real_10y_diff", "10Y Real Diff (bp)", "#ec4899"),
        ]:
            if diff_col not in aligned.columns: continue
            fig = make_subplots(specs=[[{"secondary_y": True}]])
            fig.add_trace(go.Scatter(x=aligned.index, y=aligned["spot"], mode="lines",
                line=dict(color=PAIR_COLORS.get(sel, "#888"), width=1.4),
                name=f"{sel} Spot"), secondary_y=False)
            fig.add_trace(go.Scatter(x=aligned.index, y=aligned[diff_col], mode="lines",
                line=dict(color=color, width=1.2), name=diff_label), secondary_y=True)
            fig.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
                font=dict(family="Inter, system-ui, sans-serif", size=10, color=TEXT_DIM),
                height=280, showlegend=True,
                legend=dict(orientation="h", y=1.08, x=0, font=dict(size=10)),
                margin=dict(l=60, r=60, t=25, b=20))
            fig.update_yaxes(title_text=cfg["spot_convention"], gridcolor=GRID, secondary_y=False)
            fig.update_yaxes(title_text="bp", gridcolor="#111", secondary_y=True)
            fig.update_xaxes(showgrid=False)
            st.plotly_chart(fig, use_container_width=True, key=f"fx_{sel}_{diff_col}",
                            config={"displayModeBar": False})

    # Linkage table
    linkage = build_fx_linkage_table(ctx.df, sel)
    if not linkage.empty:
        st.dataframe(linkage, hide_index=True, use_container_width=True)

    # Rolling correlations
    corrs = build_fx_rolling_correlations(ctx.df, sel)
    if not corrs.empty:
        fig_c = go.Figure()
        cc = {"corr_fx_2y": ("#eab308", "vs 2Y"), "corr_fx_10y": ("#a855f7", "vs 10Y"),
              "corr_fx_real10y": ("#ec4899", "vs 10Y Real")}
        for col in corrs.columns:
            s = corrs[col].dropna()
            if len(s):
                fig_c.add_trace(go.Scatter(x=s.index, y=s, mode="lines",
                    line=dict(color=cc.get(col, ("#888",""))[0], width=1.2),
                    name=cc.get(col, ("",""))[1]))
        fig_c.add_hline(y=0, line=dict(color="#333", width=0.5, dash="dot"))
        fig_c.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
            font=dict(size=10, color=TEXT_DIM), height=260, showlegend=True,
            legend=dict(orientation="h", y=1.06, x=0, font=dict(size=10)),
            margin=dict(l=50, r=20, t=25, b=20),
            yaxis=dict(title="Correlation", gridcolor=GRID, range=[-1,1]),
            xaxis=dict(showgrid=False))
        st.plotly_chart(fig_c, use_container_width=True, key=f"fx_corr_{sel}",
                        config={"displayModeBar": False})
    elif readiness.get("enough_history") is False:
        st.caption("Rolling correlations unavailable — insufficient aligned history.")

    # Current Reading
    items = [
        ("Convention", f"{cfg['spot_convention']} · {cfg['differential_direction']}"),
        ("Common model date", pair_date),
        ("Aligned obs", str(snap["aligned_obs"])),
    ]
    raw_d = snap.get("raw_dates", {})
    for k, l in [("spot","Spot"),("2y_diff","2Y diff"),("10y_diff","10Y diff"),("real_10y_diff","Real 10Y")]:
        items.append((f"Raw {l} latest", str(raw_d.get(k, "—"))))
    items.append(("20D FX return", _fmt(snap.get("fx_return_20d_pct"), "+.2f", "%")))
    for dk, dl in [("nom_2y_diff","2Y"),("nom_10y_diff","10Y"),("real_10y_diff","10Y real")]:
        chg = snap.get(f"{dk}_chg_20d_bp")
        align = reading.get(f"alignment_{dk}", "—")
        items.append((f"20D {dl} Δ", f"{_fmt(chg, '+.1f', ' bp')} · {align}"))
    if reading.get("strongest_corr_metric"):
        items.append(("Strongest 63D linkage",
            f"{reading['strongest_corr_metric']} ({reading['strongest_corr_value']:+.3f})"))
    render_current_reading_list("Current reading", items)

    render_model_note("Methodology",
        f"<b>Pair:</b> {sel} ({cfg['spot_convention']}). "
        f"<b>Differential:</b> {cfg['differential_direction']}. "
        "Requires ALL four inputs (spot + 2Y nom + 10Y nom + 10Y real). "
        "All analytics on the fully aligned calendar. "
        f"Flat thresholds: |FX| < {FLAT_FX_THRESHOLD}%, |diff Δ| < {FLAT_DIFF_THRESHOLD} bp. "
        "<b>Descriptive only.</b>")
    render_data_source_note("DATA.xlsx / Sheet1", pair_date)
    _render_xccy_dashboard(ctx)
    render_section_footer(page)
