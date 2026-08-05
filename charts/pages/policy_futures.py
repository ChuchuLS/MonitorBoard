"""Section 01b — live generic FF / one-month SOFR / three-month SOFR strip."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from charts.common import (
    render_explanation_box,
    render_kpi_strip,
    render_missing_data_warning,
    render_model_note,
    render_page_header,
    render_section_footer,
    render_top_tabs,
)
from config.pages import get_page
from config.theme import BG, GRID, TEXT_DIM
from config.tickers import POLICY_FUTURES_CONFIG
from models.policy_futures_generic import (
    available_policy_futures_families,
    build_policy_futures_current_reading,
    build_policy_futures_family_snapshot,
    build_policy_futures_overview,
)
from ._context import PageContext


def _fmt(value, spec: str = ".3f", suffix: str = "") -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:{spec}}{suffix}"


def render(ctx: PageContext) -> None:
    page = get_page("policy_futures")
    render_top_tabs(page["id"])

    readiness = available_policy_futures_families(ctx.df)
    ready_families = [k for k, v in readiness.items() if v["status"] == "Ready"]
    if not ready_families:
        render_page_header(page, latest_date="—")
        missing = sorted({m for v in readiness.values() for m in v.get("missing", [])})
        render_missing_data_warning(
            required=[
                ticker
                for cfg in POLICY_FUTURES_CONFIG.values()
                for ticker in cfg["generic_tickers"].values()
            ],
            missing=missing,
        )
        render_section_footer(page)
        return

    family = st.selectbox(
        "Generic futures family",
        options=list(POLICY_FUTURES_CONFIG),
        format_func=lambda code: POLICY_FUTURES_CONFIG[code]["display_name"],
        key="policy_futures_family",
    )
    history_window = st.selectbox(
        "History shown (common observations)",
        [126, 252, 504, 756],
        index=1,
        key="policy_futures_history",
    )

    snap = build_policy_futures_family_snapshot(ctx.df, family)
    model_date = snap.get("model_date")
    render_page_header(
        page,
        latest_date=model_date.strftime("%b %d, %Y").upper() if hasattr(model_date, "strftime") else str(model_date or "—"),
        viewing=f"{POLICY_FUTURES_CONFIG[family]['display_name']} · generic ranks 1–3",
    )
    render_explanation_box(
        "Continuous-contract monitor — not a meeting path",
        "The page converts each generic futures price to an implied reference rate "
        "using <b>100 − price</b>. FF represents 30-Day Federal Funds futures, "
        "SER represents 1-Month SOFR futures, and SFR represents 3-Month SOFR "
        "futures. Generic ranks automatically roll across underlying contracts; "
        "they are not fixed expiries and cannot by themselves identify a specific "
        "FOMC meeting outcome or probability.",
    )

    if snap.get("status") != "Ready":
        st.warning(
            f"Status: {snap.get('status')}. Missing: "
            f"{', '.join(snap.get('missing', [])) or 'none'}; common observations: "
            f"{snap.get('aligned_observations', 0)}."
        )
        render_section_footer(page)
        return

    table = snap["strip_table"]
    front = table.loc[table["rank"] == 1].iloc[0]
    third = table.loc[table["rank"] == 3].iloc[0]
    render_kpi_strip([
        {
            "label": "Front implied rate",
            "value": _fmt(front["implied_rate_pct"], ".3f", "%"),
            "sub": front["ticker"],
        },
        {
            "label": "Third implied rate",
            "value": _fmt(third["implied_rate_pct"], ".3f", "%"),
            "sub": third["ticker"],
        },
        {
            "label": "Rank 3 − Rank 1",
            "value": _fmt(snap.get("front_to_third_bp"), "+.1f", " bp"),
            "sub": snap.get("curve_shape", "—"),
        },
        {
            "label": "Front − spot reference",
            "value": _fmt(snap.get("front_minus_spot_bp"), "+.1f", " bp"),
            "sub": f"Common date {snap.get('spot_reference_date') or '—'}",
        },
        {
            "label": "Common observations",
            "value": f"{snap['aligned_observations']:,}",
            "sub": f"Since {snap['common_first_date']}",
        },
    ])

    st.markdown("#### Current generic strip")
    current = table.copy()
    current = current[[
        "rank_label", "ticker", "price", "implied_rate_pct",
        "relative_to_front_bp", "change_1d_bp", "change_5d_bp",
        "change_20d_bp", "change_63d_bp", "model_date",
    ]].rename(columns={
        "rank_label": "Generic rank",
        "ticker": "Bloomberg ticker",
        "price": "Price",
        "implied_rate_pct": "Implied rate (%)",
        "relative_to_front_bp": "Vs front (bp)",
        "change_1d_bp": "1D Δ rate (bp)",
        "change_5d_bp": "5D Δ rate (bp)",
        "change_20d_bp": "20D Δ rate (bp)",
        "change_63d_bp": "63D Δ rate (bp)",
        "model_date": "Common model date",
    })
    st.dataframe(
        current.style.format({
            "Price": "{:.4f}",
            "Implied rate (%)": "{:.3f}",
            "Vs front (bp)": "{:+.1f}",
            "1D Δ rate (bp)": "{:+.1f}",
            "5D Δ rate (bp)": "{:+.1f}",
            "20D Δ rate (bp)": "{:+.1f}",
            "63D Δ rate (bp)": "{:+.1f}",
        }, na_rep="—"),
        hide_index=True,
        use_container_width=True,
    )

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("#### Current implied-rate curve")
        fig_curve = go.Figure(go.Scatter(
            x=["Front", "Second", "Third"],
            y=table.sort_values("rank")["implied_rate_pct"],
            mode="lines+markers+text",
            text=[f"{v:.3f}%" for v in table.sort_values("rank")["implied_rate_pct"]],
            textposition="top center",
            line=dict(width=2),
            marker=dict(size=8),
            hovertemplate="%{x}: %{y:.4f}%<extra></extra>",
        ))
        fig_curve.update_layout(
            height=330, template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
            font=dict(size=10, color=TEXT_DIM), margin=dict(l=55, r=20, t=25, b=35),
            yaxis=dict(title="Implied reference rate (%)", gridcolor=GRID),
            xaxis=dict(title="Generic rank", showgrid=False),
        )
        st.plotly_chart(fig_curve, use_container_width=True, key="policy_futures_curve",
                        config={"displayModeBar": False})

    with c2:
        st.markdown("#### Rank 3 − Rank 1 history")
        slope = snap["slope_history_bp"].tail(int(history_window))
        fig_slope = go.Figure(go.Scatter(
            x=slope.index, y=slope, mode="lines",
            name="Rank 3 − Rank 1", line=dict(width=1.6),
            hovertemplate="%{x|%Y-%m-%d}: %{y:+.1f} bp<extra></extra>",
        ))
        fig_slope.add_hline(y=0, line=dict(color="#555", width=0.7, dash="dot"))
        fig_slope.update_layout(
            height=330, template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
            font=dict(size=10, color=TEXT_DIM), margin=dict(l=55, r=20, t=25, b=35),
            yaxis=dict(title="Generic slope (bp)", gridcolor=GRID),
            xaxis=dict(showgrid=False),
        )
        st.plotly_chart(fig_slope, use_container_width=True, key="policy_futures_slope",
                        config={"displayModeBar": False})

    st.markdown("#### Implied-rate history")
    history = snap["implied_rate_history"].tail(int(history_window))
    fig_hist = go.Figure()
    for rank, label in [(1, "Front"), (2, "Second"), (3, "Third")]:
        fig_hist.add_trace(go.Scatter(
            x=history.index, y=history[rank], mode="lines", name=label,
            line=dict(width=1.4),
        ))
    fig_hist.update_layout(
        height=360, template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(size=10, color=TEXT_DIM), hovermode="x unified",
        margin=dict(l=55, r=20, t=25, b=35),
        yaxis=dict(title="Implied reference rate (%)", gridcolor=GRID),
        xaxis=dict(showgrid=False), legend=dict(orientation="h", y=1.08, x=0),
    )
    st.plotly_chart(fig_hist, use_container_width=True, key="policy_futures_history_chart",
                    config={"displayModeBar": False})

    st.markdown("#### All generic families")
    overview = build_policy_futures_overview(ctx.df, horizons=(20,))
    overview = overview[[
        "family_name", "rank_label", "ticker", "implied_rate_pct",
        "change_20d_bp", "relative_to_front_bp", "model_date", "status",
    ]].rename(columns={
        "family_name": "Family", "rank_label": "Generic rank",
        "ticker": "Ticker", "implied_rate_pct": "Implied rate (%)",
        "change_20d_bp": "20D Δ rate (bp)",
        "relative_to_front_bp": "Vs front (bp)",
        "model_date": "Common model date", "status": "Status",
    })
    st.dataframe(
        overview.style.format({
            "Implied rate (%)": "{:.3f}",
            "20D Δ rate (bp)": "{:+.1f}",
            "Vs front (bp)": "{:+.1f}",
        }, na_rep="—"),
        hide_index=True,
        use_container_width=True,
    )

    reading = build_policy_futures_current_reading(ctx.df, family, change_window=20)
    st.markdown("#### Current reading")
    st.info(reading["summary"])
    st.caption(reading["limitations"])

    with st.expander("Contract-family definitions and limitations", expanded=False):
        meta_rows = []
        for code, cfg in POLICY_FUTURES_CONFIG.items():
            meta_rows.append({
                "Family": code,
                "Contract": cfg["display_name"],
                "Reference rate": cfg["reference_rate_label"],
                "Reference period": cfg["reference_period"],
                "Quote conversion": cfg["quote_conversion"],
                "Bloomberg generic root": cfg["bloomberg_root"],
                "Source documentation": cfg["source_documentation"],
            })
        st.dataframe(pd.DataFrame(meta_rows), hide_index=True, use_container_width=True)
        render_model_note(
            "Interpretation guardrail",
            "A generic rank is a rolling continuous series, not a fixed contract. "
            "Historical jumps can include contract-roll effects. The page does not "
            "map ranks to calendar months, infer post-meeting rates, or calculate "
            "FOMC probabilities. An expiry-mapped path requires actual contract codes, "
            "contract months and the FOMC calendar.",
        )

    render_section_footer(page)
