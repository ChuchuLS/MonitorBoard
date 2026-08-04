"""
charts/pages/policy.py — Section 01 · Policy & Short Rates

Uses models.policy_short_rates for all analytics.
GCF and TPR are now confirmed via Bloomberg DES (OFR Short-Term Funding Monitor).
FED_RESERVES confirmed (H.4.1, USD millions, weekly).
FARWCBLS is Central Bank Liquidity Swaps — NOT repo/SRF.
"""
from __future__ import annotations
import pandas as pd, numpy as np
import plotly.graph_objects as go
import streamlit as st
from config.pages import get_page
from config.theme import section_color, BG, GRID, TEXT_DIM
from config.tickers import TICKERS, TICKER_METADATA
from data.loader import latest_valid_date
from charts.common import (
    render_page_header, render_top_tabs, render_kpi_strip,
    render_explanation_box, render_current_reading_list,
    render_model_note, render_missing_data_warning,
    render_section_footer, render_data_source_note,
)
from models.policy_short_rates import (
    CONFIRMED_POLICY_KEYS, SPREAD_KEYS,
    build_short_rate_snapshot, build_policy_spreads,
    build_funding_pressure_table, build_funding_pressure_score,
    build_policy_current_reading,
)
from ._context import PageContext

PC = {"Easy": "#22c55e", "Normal": "#06b6d4", "Tight": "#f97316",
      "Very tight": "#ef4444"}


def render(ctx: PageContext) -> None:
    page = get_page("policy")
    color = section_color(page["color_key"])
    render_top_tabs(page["id"])

    # Build model FIRST
    pressure = build_funding_pressure_score(ctx.df)
    ftable = build_funding_pressure_table(ctx.df)
    snap = build_short_rate_snapshot(ctx.df)

    model_date = pressure.get("latest_date")
    req = [TICKERS[k] for k in ["SOFR", "EFFR", "IORB"] if k in TICKERS]
    input_date = latest_valid_date(ctx.df, req) or ctx.df.index.max()

    latest_str = str(model_date) if model_date else input_date.strftime("%Y-%m-%d")
    render_page_header(page, latest_date=latest_str.upper(),
        viewing=f"Funding pressure model as of: {model_date or '—'} · "
                f"Latest individual input: {input_date.date()}")

    # A. KPI strip
    kpis = []
    for key in ["SOFR", "EFFR", "IORB"]:
        if snap.empty: continue
        r = snap[snap["key"] == key]
        if r.empty: continue
        row = r.iloc[0]
        kpis.append({"label": key, "value": f"{row['latest_pct']:.3f}%",
                     "sub": f"1M: {row['1m_change_bp']:+.0f} bp · {row['latest_valid_date']}",
                     "accent": color if key == "SOFR" else ""})

    if not ftable.empty:
        for sname in ["SOFR − IORB", "EFFR − IORB"]:
            frow = ftable[ftable["Indicator"] == sname]
            if not frow.empty:
                fr = frow.iloc[0]
                kpis.append({"label": sname, "value": f"{fr['Latest_bp']:+.1f} bp",
                             "sub": f"{fr['Latest_valid_date']}"})

    pc_color = PC.get(pressure["status"], "#666")
    if pd.notna(pressure["score"]):
        aligned = "dates aligned" if pressure["dates_aligned"] else "dates NOT aligned"
        kpis.append({"label": "Plumbing pressure",
                     "value": f"{pressure['score']:+.2f}",
                     "sub": f"{pressure['status']} · {pressure['n_spreads']} spreads · {aligned}",
                     "accent": pc_color})
    render_kpi_strip(kpis)

    render_explanation_box("Policy plumbing",
        "Spot overnight and repo rates vs the Fed's IORB floor. Includes "
        "SOFR, EFFR, TGCR, BGCR, GCF Repo (OFR), and Tri-Party Repo (OFR). "
        "The <b>plumbing pressure score</b> = average 1Y z-score. "
        "Boundaries: z<−1 Easy · −1≤z≤+1 Normal · +1<z≤+2 Tight · z>+2 Very tight. "
        "Diagnostic only — not official Fed classifications.")

    # B. Corridor chart (all confirmed rates)
    st.markdown("<div style='margin:0.8rem 0 0.3rem;font-size:11px;color:#888;"
                "letter-spacing:0.1em;text-transform:uppercase;'>"
                "Policy corridor (confirmed rates)</div>", unsafe_allow_html=True)
    CORRIDOR = [
        ("Fed target lower", "FED_TARGET_LOWER", "#666"),
        ("IORB", "IORB", "#f97316"), ("EFFR", "EFFR", "#22c55e"),
        ("SOFR", "SOFR", "#06b6d4"), ("TGCR", "TGCR", "#eab308"),
        ("BGCR", "BGCR", "#a855f7"),
        ("GCF Repo", "GCF", "#ec4899"), ("Tri-Party Repo", "TPR", "#14b8a6"),
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
        height=340, showlegend=True,
        legend=dict(orientation="h", y=1.02, x=0, font=dict(size=10, color="#aaa")),
        margin=dict(l=50, r=20, t=30, b=25),
        yaxis=dict(title="Rate (%)", gridcolor=GRID, ticksuffix="%"),
        xaxis=dict(showgrid=False))
    st.plotly_chart(fig_c, use_container_width=True, key="pol_corridor",
                    config={"displayModeBar": False})

    # C. Spreads chart (bp) — now includes GCF and TPR
    spreads_df = build_policy_spreads(ctx.df)
    if not spreads_df.empty:
        st.markdown("<div style='margin:0.8rem 0 0.3rem;font-size:11px;color:#888;"
                    "letter-spacing:0.1em;text-transform:uppercase;'>"
                    "Confirmed funding spreads vs IORB (bp)</div>",
                    unsafe_allow_html=True)
        colors = ["#06b6d4", "#22c55e", "#eab308", "#a855f7", "#ec4899", "#14b8a6"]
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

    # D. Pressure table
    if not ftable.empty:
        st.markdown("<div style='margin:0.8rem 0 0.3rem;font-size:11px;color:#888;"
                    "letter-spacing:0.1em;text-transform:uppercase;'>"
                    "Funding pressure detail</div>", unsafe_allow_html=True)
        def _sc(val):
            c = PC.get(val, "#888")
            return f"color: {c}; font-weight: 700;"
        st.dataframe(ftable.style.map(_sc, subset=["Status"]),
                     hide_index=True, use_container_width=True)

    # E. Balance-sheet context (confirmed weekly series)
    st.markdown("<div style='margin:0.8rem 0 0.3rem;font-size:11px;color:#888;"
                "letter-spacing:0.1em;text-transform:uppercase;'>"
                "Balance-sheet context (weekly, H.4.1)</div>", unsafe_allow_html=True)
    bc1, bc2 = st.columns(2)
    res_tick = TICKERS.get("FED_RESERVES")
    if res_tick and res_tick in ctx.dff.columns:
        rs = ctx.dff[res_tick].dropna()
        if len(rs):
            with bc1:
                st.metric("Reserve Balances ($M)", f"{rs.iloc[-1]:,.0f}",
                          help=f"FARBRBFB INDEX · H.4.1 · last: {rs.index[-1].date()}")
    swaps_tick = TICKERS.get("CENTRAL_BANK_LIQUIDITY_SWAPS")
    if swaps_tick and swaps_tick in ctx.dff.columns:
        sw = ctx.dff[swaps_tick].dropna()
        if len(sw):
            with bc2:
                st.metric("CB Liquidity Swaps ($M)", f"{sw.iloc[-1]:,.0f}",
                          help=f"FARWCBLS INDEX · H.4.1 · last: {sw.index[-1].date()}")
    st.caption("SRF usage: Missing data — no confirmed SRF ticker identified.")

    # F. Current Reading
    reading = build_policy_current_reading(ctx.df)
    items = []
    if model_date:
        items.append(("Funding pressure model date", str(model_date)))
    items.append(("Latest individual input date", str(input_date.date())))
    if pd.notna(reading.get("pressure_score")):
        items.append(("Pressure score", f"{reading['pressure_score']:+.2f} ({reading['pressure_status']})"))
    items.append(("Dates aligned", "Yes" if reading.get("dates_aligned") else "No"))
    if reading.get("tightest"):
        t = reading["tightest"]
        items.append(("Tightest", f"{t['indicator']} (z={t['z']:+.2f}, {t['bp']:+.1f} bp)"))
    if reading.get("easiest"):
        e = reading["easiest"]
        items.append(("Easiest", f"{e['indicator']} (z={e['z']:+.2f}, {e['bp']:+.1f} bp)"))
    if reading.get("missing"):
        items.append(("Missing inputs", ", ".join(reading["missing"]) or "None"))
    render_current_reading_list("Current reading", items)

    # G. Scope warnings
    render_missing_data_warning(
        message="<b>FOMC path and SOFR strip</b> are not live. Generic FF / SFR / SER "
                "futures prices exist in DATA.xlsx, but expiry metadata, contract "
                "conventions, meeting calendar, and methodology are not yet implemented.",
    )

    render_model_note("Methodology",
        "<b>Plumbing pressure score</b> = average 1Y z-score of confirmed "
        "overnight/repo rate spreads vs IORB (SOFR, EFFR, TGCR, BGCR, GCF, TPR). "
        "Boundaries: z < −1 Easy · −1 ≤ z ≤ +1 Normal · +1 < z ≤ +2 Tight · z > +2 Very tight. "
        "Diagnostic only. FARWCBLS INDEX is Central Bank Liquidity Swaps (H.4.1), "
        "not repo or SRF usage.")

    render_data_source_note("DATA.xlsx / Sheet1", latest_str)
    render_section_footer(page)
