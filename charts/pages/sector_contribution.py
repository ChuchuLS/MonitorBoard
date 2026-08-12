"""charts/pages/sector_contribution.py — 06b · Sector Contribution Estimate
Transparent approximation with explicit residual. Not official attribution.
"""
from __future__ import annotations

import numpy as np
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
from data.external_loaders import load_spx_sector_weights
from models.sector_contribution import (
    DEFAULT_CONTRIBUTION_HORIZONS,
    MAX_WEIGHT_AGE_DAYS,
    build_sector_contribution_current_reading,
    build_sector_contribution_history,
    build_sector_contribution_summary,
)
from ._context import PageContext


def _fmt(value, fmt="+.2f", suffix=""):
    if value is None or pd.isna(value):
        return "—"
    return f"{value:{fmt}}{suffix}"


def render(ctx: PageContext) -> None:
    page = get_page("sector_contribution")
    render_top_tabs(page["id"])

    horizon = st.selectbox(
        "Contribution window (common observations)",
        list(DEFAULT_CONTRIBUTION_HORIZONS),
        index=2,
        format_func=lambda value: f"{value}D",
        key="sector_contribution_horizon",
    )
    weights = load_spx_sector_weights()
    reading = build_sector_contribution_current_reading(
        ctx.df, weights, horizon=horizon
    )

    if reading["status"] == "Missing data":
        render_page_header(page, latest_date="—", viewing="Required inputs unavailable")
        missing = reading.get("missing", [])
        render_missing_data_warning(required=missing, missing=missing)
        render_section_footer(page)
        return

    render_page_header(
        page,
        latest_date=str(reading.get("end_date") or "—").upper(),
        viewing=(
            f"{horizon}D estimate · Start {reading.get('start_date')} · "
            f"Weight {reading.get('weight_date')}"
        ),
    )

    if reading["status"] == "Partial":
        warnings = reading.get("warnings", [])
        st.warning(
            "Sector contribution estimate is Partial. "
            + (" ".join(warnings) if warnings else "Review the input audit below.")
        )

    render_explanation_box(
        "Sector Contribution Estimate",
        "A transparent approximation using the latest periodic sector weights "
        "available on or before the return-window start date. Each sector's "
        "estimated contribution equals <b>start-period weight × sector simple "
        "return</b>. The difference versus the actual SPX return is shown as a "
        "residual. <b>This is not official SPX attribution</b>, and weights are "
        "not normalised or treated as investor flows.",
    )

    kpis = [
        {"label": "Actual SPX return", "value": _fmt(reading.get("actual_spx_return_pct"), "+.2f", "%"),
         "sub": f"{reading.get('start_date')} → {reading.get('end_date')}",
         "accent": section_color(page["color_key"])},
        {"label": "Estimated return", "value": _fmt(reading.get("estimated_spx_return_pct"), "+.2f", "%"),
         "sub": "Σ start weight × sector return"},
        {"label": "Residual", "value": _fmt(reading.get("residual_pp"), "+.2f", "pp"),
         "sub": "Actual SPX − estimated"},
        {"label": "Start weight date", "value": str(reading.get("weight_date") or "—"),
         "sub": f"{reading.get('weight_age_days', '—')} calendar days before start"},
        {"label": "Weight sum", "value": _fmt(reading.get("weight_sum_pct"), ".2f", "%"),
         "sub": f"{reading.get('valid_weight_count', 0)}/11 valid sectors; not normalised"},
        {"label": "Positive contributions", "value": _fmt(reading.get("positive_contribution_pp"), "+.2f", "pp")},
        {"label": "Negative contributions", "value": _fmt(reading.get("negative_contribution_pp"), "+.2f", "pp")},
    ]
    render_kpi_strip(kpis)

    per_sector = [
        row for row in reading.get("per_sector", [])
        if pd.notna(row.get("estimated_contribution_pp"))
    ]
    ordered = sorted(per_sector, key=lambda row: row["estimated_contribution_pp"])

    st.markdown(
        "<div style='margin:0.9rem 0 0.3rem;font-size:11px;color:#888;"
        "letter-spacing:0.1em;text-transform:uppercase;'>"
        "Estimated sector contributions</div>",
        unsafe_allow_html=True,
    )
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=[row["estimated_contribution_pp"] for row in ordered],
        y=[row["display_name"] for row in ordered],
        orientation="h",
        marker=dict(
            color=["#22c55e" if row["estimated_contribution_pp"] >= 0 else "#ef4444" for row in ordered],
            line=dict(width=0),
        ),
        customdata=np.array([
            [row["start_weight_pct"], row["sector_return_pct"], row["ticker"]]
            for row in ordered
        ], dtype=object),
        hovertemplate=(
            "<b>%{y}</b><br>Estimated contribution: %{x:+.3f}pp"
            "<br>Start weight: %{customdata[0]:.2f}%"
            "<br>Sector return: %{customdata[1]:+.2f}%"
            "<br>%{customdata[2]}<extra></extra>"
        ),
    ))
    fig.add_vline(x=0, line=dict(color="#666", width=0.7))
    fig.update_layout(
        template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(family="Inter, system-ui, sans-serif", size=10, color=TEXT_DIM),
        height=440, showlegend=False,
        margin=dict(l=150, r=25, t=20, b=40),
        xaxis=dict(title="Estimated contribution to SPX return (percentage points)", gridcolor=GRID),
        yaxis=dict(showgrid=False),
    )
    st.plotly_chart(fig, use_container_width=True, key="sector_contribution_bar",
                    config={"displayModeBar": False})
    st.caption(
        "Bar length is the estimated return contribution, not market value, flow, "
        "or an official index-provider attribution figure."
    )

    table_rows = []
    for row in sorted(per_sector, key=lambda item: item["estimated_contribution_pp"], reverse=True):
        table_rows.append({
            "Rank": row.get("contribution_rank"),
            "Sector": row["display_name"],
            "Ticker": row["ticker"],
            "Start weight (%)": _fmt(row.get("start_weight_pct"), ".2f"),
            "Sector return (%)": _fmt(row.get("sector_return_pct"), "+.2f"),
            "Estimated contribution (pp)": _fmt(row.get("estimated_contribution_pp"), "+.3f"),
            "Weight date": str(row.get("weight_date") or "—"),
            "Start date": str(row.get("start_date") or "—"),
            "End date": str(row.get("end_date") or "—"),
            "Status": row.get("status", "—"),
        })
    st.dataframe(pd.DataFrame(table_rows), hide_index=True, use_container_width=True)

    st.markdown(
        "<div style='margin:0.9rem 0 0.3rem;font-size:11px;color:#888;"
        "letter-spacing:0.1em;text-transform:uppercase;'>"
        "Reconciliation across windows</div>",
        unsafe_allow_html=True,
    )
    summary = build_sector_contribution_summary(ctx.df, weights)
    if not summary.empty:
        summary_display = summary.copy()
        summary_display["Window"] = summary_display["horizon"].map(lambda value: f"{int(value)}D")
        summary_display = summary_display.rename(columns={
            "start_date": "Start date",
            "end_date": "End date",
            "weight_date": "Weight date",
            "weight_age_days": "Weight age (days)",
            "weight_sum_pct": "Weight sum (%)",
            "actual_spx_return_pct": "Actual SPX return (%)",
            "estimated_spx_return_pct": "Estimated return (%)",
            "residual_pp": "Residual (pp)",
            "status": "Status",
        })[[
            "Window", "Start date", "End date", "Weight date", "Weight age (days)",
            "Weight sum (%)", "Actual SPX return (%)", "Estimated return (%)",
            "Residual (pp)", "Status",
        ]]
        st.dataframe(
            summary_display.style.format({
                "Weight sum (%)": "{:.2f}",
                "Actual SPX return (%)": "{:+.2f}",
                "Estimated return (%)": "{:+.2f}",
                "Residual (pp)": "{:+.3f}",
            }, na_rep="—"),
            hide_index=True,
            use_container_width=True,
        )

    history = build_sector_contribution_history(ctx.df, weights, horizon=horizon)
    if not history.empty:
        st.markdown(
            "<div style='margin:0.9rem 0 0.3rem;font-size:11px;color:#888;"
            "letter-spacing:0.1em;text-transform:uppercase;'>"
            f"Rolling {horizon}D estimate versus actual SPX return</div>",
            unsafe_allow_html=True,
        )
        fig_h = go.Figure()
        fig_h.add_trace(go.Scatter(
            x=history.index, y=history["actual_spx_return_pct"], mode="lines",
            name="Actual SPX return", line=dict(color="#f8fafc", width=1.4),
        ))
        fig_h.add_trace(go.Scatter(
            x=history.index, y=history["estimated_spx_return_pct"], mode="lines",
            name="Estimated return", line=dict(color="#06b6d4", width=1.2),
        ))
        fig_h.update_layout(
            template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
            font=dict(family="Inter, system-ui, sans-serif", size=10, color=TEXT_DIM),
            height=285, margin=dict(l=55, r=20, t=25, b=30),
            legend=dict(orientation="h", y=1.12, x=0),
            yaxis=dict(title="Return (%)", gridcolor=GRID), xaxis=dict(showgrid=False),
        )
        st.plotly_chart(fig_h, use_container_width=True, key="sector_contribution_history",
                        config={"displayModeBar": False})

        fig_r = go.Figure()
        fig_r.add_trace(go.Scatter(
            x=history.index, y=history["residual_pp"], mode="lines",
            name="Residual", line=dict(color="#a855f7", width=1.2),
            fill="tozeroy", fillcolor="rgba(168,85,247,0.12)",
        ))
        fig_r.add_hline(y=0, line=dict(color="#666", width=0.7))
        fig_r.update_layout(
            template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
            font=dict(family="Inter, system-ui, sans-serif", size=10, color=TEXT_DIM),
            height=235, margin=dict(l=55, r=20, t=20, b=30), showlegend=False,
            yaxis=dict(title="Residual (pp)", gridcolor=GRID), xaxis=dict(showgrid=False),
        )
        st.plotly_chart(fig_r, use_container_width=True, key="sector_contribution_residual",
                        config={"displayModeBar": False})

    reading_items = [
        ("Estimate status", reading.get("status", "—")),
        ("Return window", f"{reading.get('start_date')} → {reading.get('end_date')} ({horizon} observations)"),
        ("Start-period weight", f"{reading.get('weight_date')} ({reading.get('weight_age_days')} calendar days before start)"),
        ("Actual SPX return", _fmt(reading.get("actual_spx_return_pct"), "+.2f", "%")),
        ("Estimated return", _fmt(reading.get("estimated_spx_return_pct"), "+.2f", "%")),
        ("Residual", _fmt(reading.get("residual_pp"), "+.3f", "pp")),
    ]
    if reading.get("top_positive"):
        reading_items.append((
            "Largest positive estimates",
            "; ".join(
                f"{row['display_name']} ({row['estimated_contribution_pp']:+.3f}pp)"
                for row in reading["top_positive"]
            ),
        ))
    if reading.get("top_negative"):
        reading_items.append((
            "Largest negative estimates",
            "; ".join(
                f"{row['display_name']} ({row['estimated_contribution_pp']:+.3f}pp)"
                for row in reading["top_negative"]
            ),
        ))
    render_current_reading_list("Current reading", reading_items)

    render_model_note(
        "Methodology and limitations",
        "<b>Return convention:</b> simple arithmetic percentage returns over "
        "identical common timestamps. <b>Weight convention:</b> latest periodic "
        "SPX_Sector_Weights row available on or before the window start date. "
        "Weights are not normalised, interpolated, or replaced with zero. "
        f"A start-weight row older than {MAX_WEIGHT_AGE_DAYS} calendar days is "
        "flagged Partial under the project diagnostic rule. "
        "<b>Contribution estimate:</b> start weight ÷ 100 × sector return. "
        "<b>Residual:</b> actual SPX return minus the sum of estimated sector "
        "contributions. The residual captures approximation error and any effects "
        "not represented by periodic start weights and simple sector returns. "
        "<b>Not official attribution:</b> exact index attribution requires "
        "divisor-consistent treatment, daily weights, or official contribution data."
    )
    render_data_source_note(
        "DATA.xlsx / Sheet1 + SPX_Sector_Weights",
        str(reading.get("end_date") or "—"),
    )
    render_section_footer(page)
