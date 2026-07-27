"""
charts/pages/policy.py — Section 01 · Policy & Short Rates

Uses ONLY models.policy_short_rates for all analytics.
Does not calculate anything independently.
Does not use unconfirmed RRP candidates.
"""
from __future__ import annotations
import pandas as pd, numpy as np
import plotly.graph_objects as go
import streamlit as st
from config.pages import get_page
from config.theme import section_color, BG, GRID, TEXT_DIM
from config.tickers import TICKERS
from data.loader import latest_valid_date
from charts.common import (
    render_page_header, render_top_tabs, render_kpi_strip,
    render_explanation_box, render_current_reading_list,
    render_model_note, render_missing_data_warning,
    render_section_footer, render_data_source_note,
)
from models.policy_short_rates import (
    CONFIRMED_POLICY_KEYS, NEEDS_CONFIRMATION_KEYS, SPREAD_KEYS,
    available_policy_inputs, build_short_rate_snapshot,
    build_policy_spreads, build_funding_pressure_table,
    build_funding_pressure_score, build_policy_current_reading,
)
from ._context import PageContext

PRESSURE_COLORS = {
    "Easy": "#22c55e", "Normal": "#06b6d4",
    "Tight": "#f97316", "Very tight": "#ef4444", "No data": "#666",
    "No includable spreads": "#666", "No valid z-scores": "#666",
}


def render(ctx: PageContext) -> None:
    page = get_page("policy")
    color = section_color(page["color_key"])
    render_top_tabs(page["id"])

    # Page date from confirmed policy columns
    req = [TICKERS[k] for k in ["SOFR", "EFFR", "IORB"] if k in TICKERS]
    lvd = latest_valid_date(ctx.df, req) or ctx.df.index.max()
    latest = lvd.strftime("%b %d, %Y").upper()
    render_page_header(page, latest_date=latest, viewing="Data source: DATA.xlsx / Sheet1")

    # A. KPI strip
    snap = build_short_rate_snapshot(ctx.df)
    pressure = build_funding_pressure_score(ctx.df)

    def _snap_val(key):
        if snap.empty: return None
        r = snap[snap["key"] == key]
        return r.iloc[0] if not r.empty else None

    sofr, effr, iorb = _snap_val("SOFR"), _snap_val("EFFR"), _snap_val("IORB")
    kpis = []
    for label, row in [("SOFR", sofr), ("EFFR", effr), ("IORB", iorb)]:
        if row is not None:
            sub = f"1M: {row['1m_change_bp']:+.0f} bp · {row['latest_valid_date']}"
            kpis.append({"label": label, "value": f"{row['latest_pct']:.3f}%",
                         "sub": sub, "accent": color if label == "SOFR" else ""})
    if sofr is not None and iorb is not None:
        sp = 100 * (sofr["latest_pct"] - iorb["latest_pct"])
        kpis.append({"label": "SOFR − IORB", "value": f"{sp:+.1f} bp"})
    if effr is not None and iorb is not None:
        sp = 100 * (effr["latest_pct"] - iorb["latest_pct"])
        kpis.append({"label": "EFFR − IORB", "value": f"{sp:+.1f} bp"})
    pc = PRESSURE_COLORS.get(pressure["status"], "#666")
    if pd.notna(pressure["score"]):
        aligned = "✓" if pressure["dates_aligned"] else "dates not aligned"
        kpis.append({"label": "Plumbing pressure",
                     "value": f"{pressure['score']:+.2f}",
                     "sub": f"{pressure['status']} · {pressure['n_spreads']} spreads · {aligned}",
                     "accent": pc})
    render_kpi_strip(kpis)

    render_explanation_box("Policy plumbing",
        "Spot overnight and repo rates vs the Fed's IORB floor. Rising "
        "spreads signal funding pressure. The <b>plumbing pressure score</b> "
        "is the average 1Y z-score across confirmed spreads — a diagnostic, "
        "not a policy-expectation model. Thresholds are not official Fed "
        "classifications.")

    # B. Spot rates chart (confirmed only)
    st.markdown("<div style='margin:0.8rem 0 0.3rem;font-size:11px;color:#888;"
                "letter-spacing:0.1em;text-transform:uppercase;'>"
                "Policy corridor (confirmed rates)</div>", unsafe_allow_html=True)
    CORRIDOR = [
        ("Fed target lower", "FED_TARGET_LOWER", "#666"),
        ("IORB", "IORB", "#f97316"),
        ("EFFR", "EFFR", "#22c55e"),
        ("SOFR", "SOFR", "#06b6d4"),
        ("TGCR", "TGCR", "#eab308"),
        ("BGCR", "BGCR", "#a855f7"),
    ]
    fig_c = go.Figure()
    for name, key, c in CORRIDOR:
        tick = TICKERS.get(key)
        if tick and tick in ctx.dff.columns:
            s = ctx.dff[tick].dropna()
            if len(s):
                fig_c.add_trace(go.Scatter(x=s.index, y=s, mode="lines",
                    line=dict(color=c, width=1.4), name=name))
    fig_c.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(family="Inter, system-ui, sans-serif", size=10, color=TEXT_DIM),
        height=320, showlegend=True,
        legend=dict(orientation="h", y=1.02, x=0, font=dict(size=10, color="#aaa")),
        margin=dict(l=50, r=20, t=30, b=25),
        yaxis=dict(title="Rate (%)", gridcolor=GRID, ticksuffix="%"),
        xaxis=dict(showgrid=False))
    st.plotly_chart(fig_c, use_container_width=True, key="pol_corridor",
                    config={"displayModeBar": False})

    # C. Funding spreads chart (bp)
    spreads_df = build_policy_spreads(ctx.df)
    if not spreads_df.empty:
        st.markdown("<div style='margin:0.8rem 0 0.3rem;font-size:11px;color:#888;"
                    "letter-spacing:0.1em;text-transform:uppercase;'>"
                    "Confirmed funding spreads vs IORB (bp)</div>",
                    unsafe_allow_html=True)
        colors = ["#06b6d4", "#22c55e", "#eab308", "#a855f7"]
        fig_sp = go.Figure()
        for i, col in enumerate(spreads_df.columns):
            s = spreads_df[col].dropna()
            tail = s.loc[ctx.dff.index.min():] if len(s) else s
            if len(tail):
                fig_sp.add_trace(go.Scatter(x=tail.index, y=tail, mode="lines",
                    line=dict(color=colors[i % len(colors)], width=1.2), name=col))
        fig_sp.add_hline(y=0, line=dict(color="#333", width=0.5, dash="dot"))
        fig_sp.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
            font=dict(family="Inter, system-ui, sans-serif", size=10, color=TEXT_DIM),
            height=300, showlegend=True,
            legend=dict(orientation="h", y=1.02, x=0, font=dict(size=10, color="#aaa")),
            margin=dict(l=50, r=20, t=30, b=25),
            yaxis=dict(title="bp", gridcolor=GRID), xaxis=dict(showgrid=False))
        st.plotly_chart(fig_sp, use_container_width=True, key="pol_spreads",
                        config={"displayModeBar": False})

    # D. Funding pressure table
    ftable = build_funding_pressure_table(ctx.df)
    if not ftable.empty:
        st.markdown("<div style='margin:0.8rem 0 0.3rem;font-size:11px;color:#888;"
                    "letter-spacing:0.1em;text-transform:uppercase;'>"
                    "Funding pressure detail</div>", unsafe_allow_html=True)
        def _sc(val):
            c = PRESSURE_COLORS.get(val, "#888")
            return f"color: {c}; font-weight: 700;"
        st.dataframe(ftable.style.map(_sc, subset=["Status"]),
                     hide_index=True, use_container_width=True)

    # E. Balance-sheet context — needs-confirmation fields, shown with caveat
    avail = available_policy_inputs(ctx.df)
    nc_avail = {k: v for k, v in avail.items() if v["status"] == "needs_confirmation" and v["available"]}
    if nc_avail:
        with st.expander("Balance-sheet context (needs confirmation)", expanded=False):
            st.caption("These fields are available but their exact Bloomberg "
                       "descriptions are not documented. Values shown for reference only.")
            for key, info in nc_avail.items():
                tick = info["ticker"]
                if tick in ctx.dff.columns:
                    s = ctx.dff[tick].dropna()
                    if len(s):
                        st.metric(f"{key} ({tick})", f"{s.iloc[-1]:,.0f}",
                                  help=f"Needs confirmation · last: {s.index[-1].date()}")

    # F. Current Reading
    reading = build_policy_current_reading(ctx.df)
    items = []
    if pd.notna(reading.get("pressure_score")):
        items.append(("Pressure score", f"{reading['pressure_score']:+.2f} ({reading['pressure_status']})"))
    if reading.get("latest_date"):
        items.append(("Model as-of date", str(reading["latest_date"])))
    items.append(("Dates aligned", "Yes" if reading.get("dates_aligned") else "No"))
    items.append(("Included spreads", str(reading.get("n_spreads", 0))))
    if reading.get("tightest"):
        t = reading["tightest"]
        items.append(("Tightest spread", f"{t['indicator']} (z={t['z']:+.2f}, {t['bp']:+.1f} bp)"))
    if reading.get("easiest"):
        e = reading["easiest"]
        items.append(("Easiest spread", f"{e['indicator']} (z={e['z']:+.2f}, {e['bp']:+.1f} bp)"))
    if reading.get("missing"):
        items.append(("Missing inputs", ", ".join(reading["missing"]) or "None"))
    if reading.get("excluded_stale"):
        items.append(("Excluded (stale)", ", ".join(reading["excluded_stale"])))
    render_current_reading_list("Current reading", items)

    # G. Scope warnings
    render_missing_data_warning(
        message="<b>FOMC path and SOFR strip</b> are not live. Generic FF / SFR / SER "
                "futures prices exist in DATA.xlsx, but expiry metadata, contract "
                "conventions, meeting calendar, and methodology are not yet implemented.",
    )
    render_missing_data_warning(
        message="<b>ON RRP usage</b> is not shown. FDTRFTRL INDEX is the Fed Funds "
                "Target Rate lower bound, not ON RRP take-up. RRP candidate fields "
                "(RRPQTOON, RRPQONAR) are not confirmed and excluded from production.",
    )

    render_model_note("Methodology",
        "<b>Plumbing pressure score</b> = average 1Y z-score of confirmed "
        "overnight/repo rate spreads vs IORB. Thresholds: "
        "z < −1 Easy · ±1 Normal · +1–2 Tight · > +2 Very tight. "
        "Diagnostic only — not official Federal Reserve classifications. "
        "Spreads are excluded if stale (>5 bdays behind freshest) or constant "
        "(σ=0). GCF, TPR, FED_RESERVES, FED_REPO are shown only in the "
        "needs-confirmation expander.")

    render_data_source_note("DATA.xlsx / Sheet1", latest)
    render_section_footer(page)
