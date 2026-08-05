"""charts/pages/earnings_valuation.py — 06c · SPX FY1 Earnings & Valuation."""
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
from data.equity_earnings_loader import load_equity_earnings_data
from models.earnings_valuation import (
    DEFAULT_BETA_WINDOW,
    DEFAULT_DECOMPOSITION_HORIZON,
    EPS_FIELD_METADATA,
    build_earnings_valuation_snapshot,
    build_global_earnings_overview,
)
from ._context import PageContext


def _fmt(value, fmt="+.2f", suffix=""):
    if value is None or pd.isna(value):
        return "—"
    return f"{value:{fmt}}{suffix}"


def _chart_layout(height: int = 330):
    return dict(
        template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(family="Inter, system-ui, sans-serif", size=10, color=TEXT_DIM),
        height=height, hovermode="x unified",
        margin=dict(l=55, r=20, t=35, b=35),
        legend=dict(orientation="h", y=1.12, x=0),
        xaxis=dict(showgrid=False),
        yaxis=dict(gridcolor=GRID),
    )


def render(ctx: PageContext) -> None:
    page = get_page("earnings_valuation")
    render_top_tabs(page["id"])

    data = load_equity_earnings_data()
    snap = build_earnings_valuation_snapshot(data)
    model_date = snap.get("model_date")

    if snap.get("status") == "Missing data":
        render_page_header(page, latest_date="—", viewing="Required inputs unavailable")
        missing = snap.get("missing", [])
        render_missing_data_warning(required=missing, missing=missing)
        render_section_footer(page)
        return

    render_page_header(
        page,
        latest_date=str(model_date or "—").upper(),
        viewing=(
            f"SPX Index · Weekly exact-date alignment · "
            f"{snap.get('aligned_observations', 0)} common observations"
        ),
    )

    render_explanation_box(
        "Confirmed EPS source and exact identity",
        "The FY1 EPS series is the Bloomberg <b>BEST_EPS</b> field with "
        "<b>BEST_FPERIOD_OVERRIDE=1FY</b>, requested weekly. The implied FY1 "
        "P/E is SPX Index level divided by FY1 EPS. On exact common weekly "
        "dates, the additive log identity is <b>SPX return = FY1 EPS growth + "
        "P/E change</b>. This is a descriptive arithmetic decomposition, not "
        "fair value, a forecast, or a causal attribution.",
    )

    h = DEFAULT_DECOMPOSITION_HORIZON
    kpis = [
        {"label": "SPX level", "value": _fmt(snap.get("price"), ",.2f"),
         "sub": str(model_date or "—"), "accent": section_color(page["color_key"])},
        {"label": "FY1 EPS", "value": _fmt(snap.get("eps_fy1"), ",.2f"),
         "sub": "BEST_EPS · 1FY · weekly"},
        {"label": "Implied FY1 P/E", "value": _fmt(snap.get("fy1_pe"), ".2f", "x"),
         "sub": f"Percentile {_fmt(snap.get('pe_percentile_available_history'), '.0f', '%')} "
                f"of {snap.get('pe_percentile_observations', 0)} common observations"},
        {"label": f"{h}W SPX return", "value": _fmt(snap.get("current_price_return_pct"), "+.2f", "%"),
         "sub": f"{snap.get('current_start_date')} → {snap.get('current_end_date')}"},
        {"label": f"{h}W FY1 EPS", "value": _fmt(snap.get("current_eps_growth_pct"), "+.2f", "%"),
         "sub": snap.get("eps_revision_direction", "—")},
        {"label": f"{h}W P/E change", "value": _fmt(snap.get("current_valuation_change_pct"), "+.2f", "%"),
         "sub": snap.get("valuation_direction", "—")},
    ]
    render_kpi_strip(kpis)

    frame = snap.get("frame", pd.DataFrame())
    if not frame.empty:
        normalized = frame[["price", "eps_fy1", "fy1_pe"]] / frame[["price", "eps_fy1", "fy1_pe"]].iloc[0] * 100
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=normalized.index, y=normalized["price"], name="SPX level", line=dict(width=1.6, color="#f8fafc")))
        fig.add_trace(go.Scatter(x=normalized.index, y=normalized["eps_fy1"], name="FY1 EPS", line=dict(width=1.4, color="#5fb04f")))
        fig.add_trace(go.Scatter(x=normalized.index, y=normalized["fy1_pe"], name="Implied FY1 P/E", line=dict(width=1.2, color="#b184ff")))
        fig.update_layout(**_chart_layout(330), title="SPX, FY1 EPS and implied FY1 P/E — normalized to 100")
        fig.update_yaxes(title="Index (first common observation = 100)")
        st.plotly_chart(fig, use_container_width=True, key="earnings_normalized", config={"displayModeBar": False})
        st.caption("All three series use the exact common weekly observation calendar. No forward-fill is used.")

    hist = snap.get("decomposition_history", pd.DataFrame())
    if not hist.empty:
        fig_d = go.Figure()
        fig_d.add_trace(go.Bar(
            x=hist.index, y=hist["eps_growth_pct"], name="FY1 EPS growth",
            marker_color="#5fb04f",
        ))
        fig_d.add_trace(go.Bar(
            x=hist.index, y=hist["valuation_change_pct"], name="P/E change",
            marker_color="#b184ff",
        ))
        fig_d.add_trace(go.Scatter(
            x=hist.index, y=hist["price_return_pct"], name="SPX net return",
            line=dict(color="#f8fafc", width=1.4),
        ))
        fig_d.update_layout(**_chart_layout(360), barmode="relative",
                            title=f"Rolling {h}-week exact log-return decomposition")
        fig_d.update_yaxes(title="Log return / change (%)")
        st.plotly_chart(fig_d, use_container_width=True, key="earnings_exact_decomp", config={"displayModeBar": False})
        st.caption(
            "Exact identity: SPX log return = FY1 EPS log growth + implied FY1 P/E log change. "
            "The identity residual is numerical rounding only."
        )

    col_left, col_right = st.columns([1.05, 0.95])
    with col_left:
        if not frame.empty:
            fig_pe = go.Figure()
            fig_pe.add_trace(go.Scatter(
                x=frame.index, y=frame["fy1_pe"], name="Implied FY1 P/E",
                line=dict(color="#b184ff", width=1.5),
            ))
            fig_pe.add_hline(y=float(frame["fy1_pe"].median()), line=dict(color="#666", width=0.8, dash="dot"),
                             annotation_text="Available-history median")
            fig_pe.update_layout(**_chart_layout(300), title="Implied FY1 P/E")
            fig_pe.update_yaxes(title="Multiple (x)")
            st.plotly_chart(fig_pe, use_container_width=True, key="earnings_pe", config={"displayModeBar": False})

    with col_right:
        render_current_reading_list(
            "Current reading",
            [
                ("Model date", str(model_date or "—")),
                (f"{h}W SPX return", _fmt(snap.get("current_price_return_pct"), "+.2f", "%")),
                (f"{h}W FY1 EPS growth", _fmt(snap.get("current_eps_growth_pct"), "+.2f", "%")),
                (f"{h}W P/E change", _fmt(snap.get("current_valuation_change_pct"), "+.2f", "%")),
                ("Larger component", str(snap.get("current_driver", "—"))),
                ("Identity residual", _fmt(snap.get("current_identity_residual_pct"), "+.6f", "%")),
            ],
        )
        render_model_note(
            "Weekly OLS diagnostic",
            f"A separate descriptive single-factor OLS uses the latest "
            f"{DEFAULT_BETA_WINDOW} weekly changes. Current beta: "
            f"<b>{_fmt(snap.get('regression_beta'), '+.3f')}</b>; R²: "
            f"<b>{_fmt(snap.get('regression_r_squared'), '.3f')}</b>. Fitted "
            f"earnings component over {h} weeks: "
            f"<b>{_fmt(snap.get('regression_fitted_earnings_pct'), '+.2f', '%')}</b>; "
            f"regression residual: <b>{_fmt(snap.get('regression_residual_pct'), '+.2f', '%')}</b>. "
            "This diagnostic is weekly, uses limited common history, and is not "
            "the reference pack's 3-year daily regression model. Low R² means "
            "the fitted split has little explanatory power.",
        )

    st.markdown(
        "<div style='margin:1rem 0 0.4rem;font-size:11px;color:#888;"
        "letter-spacing:0.1em;text-transform:uppercase;'>"
        "Global FY1 earnings and valuation overview — 13 weeks</div>",
        unsafe_allow_html=True,
    )
    overview = build_global_earnings_overview(data, horizon=13)
    if not overview.empty:
        display = overview.rename(columns={
            "index": "Index", "region": "Region", "model_date": "Model date",
            "aligned_observations": "Common obs", "price": "Index level",
            "eps_fy1": "FY1 EPS", "fy1_pe": "FY1 P/E (x)",
            "price_return_13w_pct": "13W index return (%)",
            "eps_growth_13w_pct": "13W EPS growth (%)",
            "valuation_change_13w_pct": "13W P/E change (%)",
            "status": "Status",
        })[[
            "Index", "Region", "Model date", "Common obs", "Index level",
            "FY1 EPS", "FY1 P/E (x)", "13W index return (%)",
            "13W EPS growth (%)", "13W P/E change (%)", "Status",
        ]]
        st.dataframe(
            display.style.format({
                "Index level": "{:,.2f}", "FY1 EPS": "{:,.2f}", "FY1 P/E (x)": "{:.2f}",
                "13W index return (%)": "{:+.2f}", "13W EPS growth (%)": "{:+.2f}",
                "13W P/E change (%)": "{:+.2f}",
            }, na_rep="—"),
            hide_index=True, use_container_width=True,
        )
        st.caption(
            "Each index uses its own exact common EPS/price dates. A missing status is not replaced by "
            "another market, a futures proxy, or zero."
        )

    render_data_source_note(
        "DATA.xlsx / Equity_EPS + Equity_Prices",
        latest_date=str(model_date or "—"),
        caveat="BEST_EPS with 1FY override; weekly exact-date alignment; not blended 12M or trailing EPS",
    )
    render_model_note(
        "Methodology and limitations",
        "FY1 EPS is confirmed from the Bloomberg formula shown by the user: "
        f"<code>{EPS_FIELD_METADATA['formula']}</code>. The main decomposition "
        "is an exact log identity and does not require regression. The implied "
        "P/E is a calculated ratio, not a Bloomberg-supplied valuation field. "
        "Historical percentiles use only the currently available exact common "
        "history. No claim of fair value, causality, or forecast is made.",
    )
    render_section_footer(page)
