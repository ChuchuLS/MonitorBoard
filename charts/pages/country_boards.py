"""
charts/pages/country_boards.py
==============================
Section 04b — Country Rate Boards.

Nominal sovereign curve boards for US / DE / JP / UK / CA / AU / CH using
fully aligned 2Y / 5Y / 10Y / 30Y observations.  Presentation only; all
calculations live in models/country_rate_boards.py.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from charts.common import (
    render_current_reading_box,
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
from config.theme import BG, GRID, TEXT_DIM
from models.country_rate_boards import (
    BOARD_HORIZONS,
    BOARD_SLOPE_PAIRS,
    available_country_boards,
    build_country_board,
    build_country_board_current_reading,
    build_global_country_board_overview,
)
from models.global_rates import COUNTRY_LABELS, STANDARD_TENORS
from models.global_rate_decomposition import (
    available_global_decomposition_tenors,
    build_global_decomposition_snapshot,
    rolling_global_rate_attribution,
)
from ._context import PageContext

COUNTRY_COLORS = {
    "US": "#ffffff",
    "DE": "#06b6d4",
    "JP": "#ef4444",
    "UK": "#22c55e",
    "CA": "#f97316",
    "AU": "#a855f7",
    "CH": "#eab308",
}
TENOR_COLORS = {
    "2Y": "#06b6d4",
    "5Y": "#22c55e",
    "10Y": "#f59e0b",
    "30Y": "#ef4444",
}
DECOMP_COLORS = {
    "nominal": "#ffffff",
    "real": "#06b6d4",
    "inflation": "#f59e0b",
}


def _fmt(value, spec: str, suffix: str = "—") -> str:
    if value is None or pd.isna(value):
        return "—"
    return format(float(value), spec) + (suffix if suffix != "—" else "")


def _fmt_pct(value) -> str:
    return "—" if value is None or pd.isna(value) else f"{float(value):.2f}%"


def _fmt_bp(value) -> str:
    return "—" if value is None or pd.isna(value) else f"{float(value):+.0f} bp"


def _filter_history(frame: pd.DataFrame, ctx: PageContext) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame()
    return frame.loc[pd.Timestamp(ctx.start_date):pd.Timestamp(ctx.end_date)]


def _render_country_decomposition(ctx: PageContext, country: str) -> None:
    """Render the reference-style real/inflation attribution when supported."""
    st.markdown(
        "<div style='margin:1rem 0 0.35rem;font-size:11px;color:#888;"
        "letter-spacing:0.1em;text-transform:uppercase;'>"
        "Nominal / real / inflation decomposition</div>",
        unsafe_allow_html=True,
    )

    tenors = available_global_decomposition_tenors(
        ctx.df,
        country,
        min_observations=21,
        asof=ctx.end_date,
    )
    if not tenors:
        render_missing_data_warning(
            required=["Same-tenor nominal government yield", "Same-market real government yield"],
            available=["Nominal 2Y / 5Y / 10Y / 30Y curve"],
            missing=["Confirmed same-market real-yield series"],
            message=(
                "This country has no confirmed exact-tenor real-yield input in "
                "DATA.xlsx. The reference pack uses a proxy for some markets, but "
                "this board does not substitute another country's inflation or real-rate series."
            ),
        )
        return

    default_tenor = "10Y" if "10Y" in tenors else tenors[0]
    tenor = st.selectbox(
        "Attribution tenor",
        tenors,
        index=tenors.index(default_tenor),
        key=f"country_decomposition_tenor_{country}",
    )
    snapshot = build_global_decomposition_snapshot(
        ctx.df,
        country,
        horizons=(5, 20),
        asof=ctx.end_date,
    )
    selected = snapshot[snapshot["tenor"] == tenor]
    if selected.empty:
        st.warning("The selected exact-tenor decomposition is unavailable.")
        return
    row = selected.iloc[0]

    render_kpi_strip([
        {
            "label": f"{tenor} nominal",
            "value": f"{row['nominal_pct']:.2f}%",
            "sub": f"20 common obs {row['nominal_change_20d_bp']:+.0f} bp",
        },
        {
            "label": f"{tenor} real",
            "value": f"{row['real_pct']:.2f}%",
            "sub": f"20 common obs {row['real_change_20d_bp']:+.0f} bp",
            "accent": DECOMP_COLORS["real"],
        },
        {
            "label": f"{tenor} inflation compensation",
            "value": f"{row['inflation_pct']:.2f}%",
            "sub": f"20 common obs {row['inflation_change_20d_bp']:+.0f} bp",
            "accent": DECOMP_COLORS["inflation"],
        },
        {
            "label": "Decomposition date",
            "value": str(row["model_date"]),
            "sub": f"{int(row['aligned_observations']):,} exact-date observations",
        },
    ])

    attribution = rolling_global_rate_attribution(
        ctx.df,
        country,
        tenor=tenor,
        window=10,
        asof=ctx.end_date,
    ).dropna()
    if attribution.empty:
        st.warning("Insufficient common observations for rolling 10D attribution.")
        return

    plot = attribution.iloc[-252:]
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=plot.index,
        y=plot["real_contribution_bp"],
        name="Real",
        marker_color=DECOMP_COLORS["real"],
        hovertemplate="%{x|%Y-%m-%d}: %{y:+.1f} bp<extra>Real</extra>",
    ))
    fig.add_trace(go.Bar(
        x=plot.index,
        y=plot["inflation_contribution_bp"],
        name="Inflation compensation",
        marker_color=DECOMP_COLORS["inflation"],
        hovertemplate="%{x|%Y-%m-%d}: %{y:+.1f} bp<extra>Inflation compensation</extra>",
    ))
    fig.add_trace(go.Scatter(
        x=plot.index,
        y=plot["nominal_change_bp"],
        mode="lines",
        name="Nominal 10D change",
        line=dict(color=DECOMP_COLORS["nominal"], width=1.4),
        hovertemplate="%{x|%Y-%m-%d}: %{y:+.1f} bp<extra>Nominal</extra>",
    ))
    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        barmode="relative",
        height=340,
        margin=dict(l=50, r=20, t=24, b=32),
        font=dict(family="Inter, system-ui, sans-serif", size=10, color=TEXT_DIM),
        legend=dict(orientation="h", y=1.04, x=0),
        yaxis=dict(title="Rolling 10-observation change (bp)", gridcolor=GRID),
        xaxis=dict(showgrid=False),
    )
    st.plotly_chart(
        fig,
        use_container_width=True,
        key=f"country_rate_decomposition_{country}_{tenor}",
        config={"displayModeBar": False},
    )
    max_residual = float(attribution["residual_bp"].abs().max())
    st.caption(
        "Inflation compensation = nominal government yield minus same-tenor "
        "inflation-linked government yield. Inputs are joined on exact dates; "
        "no forward-fill, interpolation, or cross-country proxy is used. "
        f"Maximum absolute identity residual: {max_residual:.2e} bp."
    )


def render(ctx: PageContext) -> None:
    page = get_page("country_boards")
    render_top_tabs(page["id"])

    readiness = available_country_boards(ctx.df)
    ready_countries = [c for c, info in readiness.items() if info["status"] == "Ready"]
    overview = build_global_country_board_overview(ctx.df, horizon=20)
    global_model_date = (
        overview["model_date"].iloc[0] if not overview.empty else None
    )
    latest = (
        pd.Timestamp(global_model_date).strftime("%b %d, %Y").upper()
        if global_model_date else "—"
    )
    render_page_header(
        page,
        latest_date=latest,
        viewing="Global comparison uses one common 28-series observation calendar",
    )

    if not ready_countries:
        st.warning("No fully aligned four-tenor country board is available.")
        render_data_source_note("DATA.xlsx / Sheet1", latest)
        render_section_footer(page)
        return

    label_to_country = {COUNTRY_LABELS[c]: c for c in ready_countries}
    default_idx = list(label_to_country).index("United States") if "United States" in label_to_country else 0
    selected_label = st.selectbox(
        "Country",
        options=list(label_to_country),
        index=default_idx,
        key="country_board_selector",
    )
    country = label_to_country[selected_label]
    board = build_country_board(ctx.df, country)
    reading = build_country_board_current_reading(ctx.df, country, horizon=20)

    if board.get("status") != "Ready":
        missing = ", ".join(board.get("missing_tenors", [])) or "insufficient common history"
        st.warning(f"{selected_label} board is {board.get('status')}: {missing}.")
        render_data_source_note("DATA.xlsx / Sheet1", latest)
        render_section_footer(page)
        return

    yield_table = board["yield_table"].set_index("tenor")
    slope_table = board["slope_table"].set_index("slope")
    model_date = board["model_date"]

    render_kpi_strip([
        {"label": "Country model date", "value": str(model_date)},
        {"label": "10Y yield", "value": _fmt_pct(yield_table.at["10Y", "yield_pct"])},
        {"label": "20D 10Y change", "value": _fmt_bp(yield_table.at["10Y", "change_20d_bp"])},
        {"label": "2s10s slope", "value": _fmt_bp(slope_table.at["2s10s", "slope_bp"])},
        {"label": "20D 2s10s change", "value": _fmt_bp(slope_table.at["2s10s", "change_20d_bp"])},
    ])

    render_explanation_box(
        "Country board scope",
        "Each board aligns the selected country's 2Y, 5Y, 10Y and 30Y nominal "
        "government yields before calculating levels, changes and slopes. No "
        "forward-fill or independently dated latest-value subtraction is used. "
        "Cross-country rankings use a stricter common calendar shared by all "
        "seven countries.",
    )

    # Global overview — comparable date for all seven countries.
    st.markdown(
        "<div style='margin:0.9rem 0 0.35rem;font-size:11px;color:#888;"
        "letter-spacing:0.1em;text-transform:uppercase;'>"
        "Seven-country overview — common comparison date</div>",
        unsafe_allow_html=True,
    )
    if not overview.empty:
        od = overview.copy()
        od = od[[
            "label", "yield_2y_pct", "yield_10y_pct", "yield_30y_pct",
            "change_20d_10y_bp", "slope_2s10s_bp", "change_20d_2s10s_bp",
            "model_date",
        ]]
        od.columns = [
            "Country", "2Y (%)", "10Y (%)", "30Y (%)", "20D 10Y Δ (bp)",
            "2s10s (bp)", "20D 2s10s Δ (bp)", "Common date",
        ]
        for col in ["2Y (%)", "10Y (%)", "30Y (%)"]:
            od[col] = od[col].map(lambda x: "—" if pd.isna(x) else f"{x:.2f}")
        for col in ["20D 10Y Δ (bp)", "2s10s (bp)", "20D 2s10s Δ (bp)"]:
            od[col] = od[col].map(lambda x: "—" if pd.isna(x) else f"{x:+.0f}")
        st.dataframe(od, hide_index=True, use_container_width=True)

    # Current / 20D / 63D yield curves.
    st.markdown(
        "<div style='margin:1rem 0 0.35rem;font-size:11px;color:#888;"
        "letter-spacing:0.1em;text-transform:uppercase;'>"
        "Yield curve snapshots</div>", unsafe_allow_html=True,
    )
    curve = board["curve_frame"]
    fig_curve = go.Figure()
    snapshots = [
        ("Current", -1, COUNTRY_COLORS.get(country, "#fff"), 2.5),
        ("20 observations ago", -21, "#6b7280", 1.4),
        ("63 observations ago", -64, "#374151", 1.2),
    ]
    for name, idx, color, width in snapshots:
        if len(curve) >= abs(idx):
            row = curve.iloc[idx]
            fig_curve.add_trace(go.Scatter(
                x=STANDARD_TENORS,
                y=[row[t] for t in STANDARD_TENORS],
                mode="lines+markers",
                name=f"{name} · {curve.index[idx].date()}",
                line=dict(color=color, width=width),
                marker=dict(size=6),
                hovertemplate="%{x}: %{y:.3f}%<extra></extra>",
            ))
    fig_curve.update_layout(
        template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
        height=360, margin=dict(l=50, r=20, t=20, b=35),
        font=dict(family="Inter, system-ui, sans-serif", size=10, color=TEXT_DIM),
        legend=dict(orientation="h", y=1.04, x=0),
        yaxis=dict(title="Nominal yield (%)", gridcolor=GRID, ticksuffix="%"),
        xaxis=dict(showgrid=False),
    )
    st.plotly_chart(fig_curve, use_container_width=True, key="country_board_curve",
                    config={"displayModeBar": False})

    # Yield changes by tenor.
    st.markdown(
        "<div style='margin:1rem 0 0.35rem;font-size:11px;color:#888;"
        "letter-spacing:0.1em;text-transform:uppercase;'>"
        "Yield changes by tenor</div>", unsafe_allow_html=True,
    )
    fig_changes = go.Figure()
    for horizon, color in [(5, "#06b6d4"), (20, "#f59e0b"), (63, "#a855f7")]:
        fig_changes.add_trace(go.Bar(
            x=STANDARD_TENORS,
            y=[yield_table.at[t, f"change_{horizon}d_bp"] for t in STANDARD_TENORS],
            name=f"{horizon}D",
            marker_color=color,
            hovertemplate="%{x}: %{y:+.1f} bp<extra></extra>",
        ))
    fig_changes.update_layout(
        template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
        barmode="group", height=330, margin=dict(l=50, r=20, t=20, b=35),
        font=dict(family="Inter, system-ui, sans-serif", size=10, color=TEXT_DIM),
        legend=dict(orientation="h", y=1.04, x=0),
        yaxis=dict(title="Yield change (bp)", gridcolor=GRID, zeroline=True,
                   zerolinecolor="#555"),
        xaxis=dict(showgrid=False),
    )
    st.plotly_chart(fig_changes, use_container_width=True, key="country_board_changes",
                    config={"displayModeBar": False})

    c1, c2 = st.columns(2)
    with c1:
        st.markdown(
            "<div style='margin:0.8rem 0 0.35rem;font-size:11px;color:#888;"
            "letter-spacing:0.1em;text-transform:uppercase;'>Yield table</div>",
            unsafe_allow_html=True,
        )
        yd = board["yield_table"].copy()
        yd = yd[[
            "tenor", "yield_pct", "change_1d_bp", "change_5d_bp",
            "change_20d_bp", "change_63d_bp", "percentile_1y_pct",
        ]]
        yd.columns = ["Tenor", "Yield (%)", "1D Δ", "5D Δ", "20D Δ", "63D Δ", "1Y percentile"]
        yd["Yield (%)"] = yd["Yield (%)"].map(lambda x: f"{x:.3f}")
        for col in ["1D Δ", "5D Δ", "20D Δ", "63D Δ"]:
            yd[col] = yd[col].map(lambda x: "—" if pd.isna(x) else f"{x:+.1f} bp")
        yd["1Y percentile"] = yd["1Y percentile"].map(
            lambda x: "—" if pd.isna(x) else f"{x:.0f}%"
        )
        st.dataframe(yd, hide_index=True, use_container_width=True)

    with c2:
        st.markdown(
            "<div style='margin:0.8rem 0 0.35rem;font-size:11px;color:#888;"
            "letter-spacing:0.1em;text-transform:uppercase;'>Curve slope table</div>",
            unsafe_allow_html=True,
        )
        sd = board["slope_table"].copy()
        sd = sd[[
            "slope", "slope_bp", "change_5d_bp", "change_20d_bp",
            "change_63d_bp", "percentile_1y_pct", "inverted",
        ]]
        sd.columns = ["Slope", "Level (bp)", "5D Δ", "20D Δ", "63D Δ", "1Y percentile", "Inverted"]
        for col in ["Level (bp)", "5D Δ", "20D Δ", "63D Δ"]:
            sd[col] = sd[col].map(lambda x: "—" if pd.isna(x) else f"{x:+.1f}")
        sd["1Y percentile"] = sd["1Y percentile"].map(
            lambda x: "—" if pd.isna(x) else f"{x:.0f}%"
        )
        sd["Inverted"] = sd["Inverted"].map(lambda x: "Yes" if x else "No")
        st.dataframe(sd, hide_index=True, use_container_width=True)

    # Slope histories using visible sidebar range.
    st.markdown(
        "<div style='margin:1rem 0 0.35rem;font-size:11px;color:#888;"
        "letter-spacing:0.1em;text-transform:uppercase;'>"
        "Selected slope history</div>", unsafe_allow_html=True,
    )
    slope_history = _filter_history(board["slope_history"], ctx)
    fig_slopes = go.Figure()
    for slope, color in [("2s10s", "#f59e0b"), ("5s30s", "#06b6d4")]:
        if slope in slope_history.columns:
            fig_slopes.add_trace(go.Scatter(
                x=slope_history.index, y=slope_history[slope], mode="lines",
                name=slope, line=dict(color=color, width=1.5),
                hovertemplate="%{x|%Y-%m-%d}: %{y:+.1f} bp<extra></extra>",
            ))
    fig_slopes.add_hline(y=0, line=dict(color="#555", width=0.8, dash="dot"))
    fig_slopes.update_layout(
        template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
        height=330, margin=dict(l=50, r=20, t=20, b=35),
        font=dict(family="Inter, system-ui, sans-serif", size=10, color=TEXT_DIM),
        legend=dict(orientation="h", y=1.04, x=0),
        yaxis=dict(title="Slope (bp)", gridcolor=GRID),
        xaxis=dict(showgrid=False),
    )
    st.plotly_chart(fig_slopes, use_container_width=True, key="country_board_slopes",
                    config={"displayModeBar": False})

    _render_country_decomposition(ctx, country)

    move = reading.get("move", {})
    render_current_reading_box(
        "Current reading",
        f"<b>{selected_label}</b> board date: <b>{model_date}</b>.<br>"
        f"10Y yield: <b>{_fmt_pct(reading.get('yield_10y_pct'))}</b>; "
        f"20D change: <b>{_fmt_bp(reading.get('change_20d_10y_bp'))}</b>.<br>"
        f"2s10s slope: <b>{_fmt_bp(reading.get('slope_2s10s_bp'))}</b>; "
        f"20D slope change: <b>{_fmt_bp(reading.get('change_20d_2s10s_bp'))}</b>.<br>"
        f"{move.get('summary', 'Curve move unavailable.')}",
    )

    render_model_note(
        "Methodology and limits",
        "Changes are measured in basis points over common observations, not "
        "calendar days. The 1Y percentile is the latest observation's empirical "
        "rank within up to 252 common observations. The curve-move description "
        "uses a disclosed ±5 bp diagnostic threshold for both level and 2s10s "
        "shape changes. It is descriptive, not a forecast, policy view or trade "
        "recommendation. Where the real-yield extension is available, implied "
        "inflation compensation is an arithmetic nominal-minus-real residual; it "
        "is not a pure forecast of expected inflation.",
    )

    with st.expander("Country board readiness", expanded=False):
        rows = []
        for c, info in readiness.items():
            rows.append({
                "Country": info["label"],
                "Status": info["status"],
                "Aligned observations": info["aligned_observations"],
                "First common date": info["first_date"],
                "Latest common date": info["model_date"],
                "Missing tenors": ", ".join(info["missing_tenors"]) or "—",
            })
        st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)

    render_data_source_note("DATA.xlsx / Sheet1", str(model_date))
    render_section_footer(page)
