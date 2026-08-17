"""06c · Global Index Trend & Market Breadth."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from charts.common import (
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
from data.index_breadth_loader import BREADTH_METRICS, load_index_breadth
from models.earnings_valuation import INDEX_META
from models.index_breadth import build_index_breadth_snapshot
from ._context import PageContext


def _fmt(value, fmt=",.2f", suffix=""):
    return "—" if value is None or pd.isna(value) else f"{value:{fmt}}{suffix}"


def _layout(height=230, title=None):
    return dict(
        template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(family="Inter, system-ui, sans-serif", size=10, color=TEXT_DIM),
        height=height, hovermode="x unified", title=title,
        margin=dict(l=55, r=20, t=38, b=32),
        legend=dict(orientation="h", y=1.16, x=0),
        xaxis=dict(showgrid=False), yaxis=dict(gridcolor=GRID),
    )


def _add_bar_panel(frame, columns, labels, colors, title, key):
    available = [column for column in columns if column in frame and frame[column].notna().any()]
    if not available:
        return
    fig = go.Figure()
    for column, label, color in zip(columns, labels, colors):
        if column in available:
            fig.add_trace(go.Bar(x=frame.index, y=frame[column], name=label, marker_color=color))
    fig.update_layout(**_layout(230, title), barmode="relative")
    fig.add_hline(y=0, line=dict(color="#555", width=0.7))
    st.plotly_chart(fig, use_container_width=True, key=key, config={"displayModeBar": False})


def render(ctx: PageContext) -> None:
    page = get_page("index_breadth")
    render_top_tabs(page["id"])
    data = load_equity_earnings_data()
    prices = data.get("prices", pd.DataFrame())
    breadth = load_index_breadth()

    c1, c2 = st.columns([2, 1])
    with c1:
        code = st.selectbox(
            "Index", list(INDEX_META), index=list(INDEX_META).index("ES1"),
            format_func=lambda item: f"{INDEX_META[item]['display_name']} · {INDEX_META[item]['region']}",
            key="index_breadth_selector",
        )
    with c2:
        frequency = st.selectbox("Frequency", ["Daily", "Weekly"], key="index_breadth_frequency")

    name = INDEX_META[code]["display_name"]
    snap = build_index_breadth_snapshot(prices, breadth, code, frequency)
    render_page_header(
        page,
        latest_date=str(snap.get("model_date") or "—").upper(),
        viewing=f"{name} · {frequency} · {snap.get('status')}",
    )
    render_explanation_box(
        "Price trend is live; constituent breadth requires separate source fields",
        "The price panel uses the selected index's own cash-index close from "
        "<b>Equity_Prices</b>. The 50D and 200D averages are calculated only when "
        "enough actual daily closes exist. The reference-style breadth panels require "
        "constituent counts or percentages for the same index and are never inferred "
        "from index-level price, sector indices, ETFs, or another market.",
    )

    render_kpi_strip([
        {"label": f"{name} close", "value": _fmt(snap.get("price")),
         "sub": str(snap.get("model_date") or "—"), "accent": section_color(page["color_key"])},
        {"label": "50DMA", "value": _fmt(snap.get("ma_50d")),
         "sub": "Observed daily closes"},
        {"label": "200DMA", "value": _fmt(snap.get("ma_200d")),
         "sub": "Observed daily closes"},
        {"label": "100-week MA", "value": _fmt(snap.get("ma_100w")),
         "sub": f"{snap.get('weekly_observations', 0)}/100 weekly closes"},
    ])

    trend = snap.get("trend", pd.DataFrame())
    if not trend.empty and trend["price"].notna().any():
        fig = go.Figure()
        for column, label, color, width in [
            ("price", f"{name} close", "#f8fafc", 1.5),
            ("ma_50d", "50DMA", "#e8b931", 1.2),
            ("ma_200d", "200DMA", "#8bd450", 1.4),
            ("ma_100w", "100-week MA", "#52d7df", 1.2),
        ]:
            series = trend[column].dropna() if column in trend else pd.Series(dtype=float)
            if len(series):
                fig.add_trace(go.Scatter(x=series.index, y=series, name=label,
                                         mode="lines", line=dict(color=color, width=width)))
        fig.update_layout(**_layout(390, f"{name} price trend"))
        fig.update_yaxes(title="Index level")
        st.plotly_chart(fig, use_container_width=True, key="index_breadth_price", config={"displayModeBar": False})
        st.caption("The workbook supplies close only, so this is a line chart rather than an invented OHLC candlestick chart.")

    metrics = snap.get("breadth", pd.DataFrame())
    if metrics.empty or snap.get("missing_metrics"):
        render_missing_data_warning(
            required=list(BREADTH_METRICS.values()),
            missing=snap.get("missing_metrics") or list(BREADTH_METRICS.values()),
            message=(
                f"{name} constituent breadth is Partial because DATA.xlsx has no usable "
                "Index_Breadth observations for all reference indicators. Price trend "
                "remains live; missing breadth panels are withheld rather than proxied."
            ),
        )

    if not metrics.empty:
        _add_bar_panel(metrics, ["advance_decline"], ["Advancers − decliners"],
                       ["#78d64b"], "Advance–Decline", "breadth_ad")
        _add_bar_panel(metrics, ["new_52w_highs_pct", "new_52w_lows_pct"],
                       ["% new 52-week highs", "% new 52-week lows"],
                       ["#52d7df", "#f04f4f"], "New 52-week highs / lows", "breadth_52w")
        line_cols = [c for c in ["above_200dma_pct", "above_50dma_pct"]
                     if c in metrics and metrics[c].notna().any()]
        if line_cols:
            fig_ma = go.Figure()
            for column, label, color in [
                ("above_200dma_pct", "% above 200DMA", "#8bd450"),
                ("above_50dma_pct", "% above 50DMA", "#e8b931"),
            ]:
                if column in line_cols:
                    fig_ma.add_trace(go.Scatter(x=metrics.index, y=metrics[column], name=label,
                                                line=dict(color=color, width=1.3)))
            fig_ma.update_layout(**_layout(230, "Constituents above moving averages"))
            fig_ma.update_yaxes(title="Percent (%)")
            st.plotly_chart(fig_ma, use_container_width=True, key="breadth_ma", config={"displayModeBar": False})
        _add_bar_panel(metrics, ["rsi14_above70_pct", "rsi14_below30_pct"],
                       ["% RSI14 > 70", "% RSI14 < 30"], ["#35bdf4", "#f6bd60"],
                       "14-day RSI extremes", "breadth_rsi")
        if "index_put_call_ratio" in metrics and metrics["index_put_call_ratio"].notna().any():
            fig_pc = go.Figure(go.Scatter(x=metrics.index, y=metrics["index_put_call_ratio"],
                                          name="Index put/call ratio", line=dict(color="#f8fafc", width=1.3)))
            fig_pc.update_layout(**_layout(230, "Index put/call ratio"))
            st.plotly_chart(fig_pc, use_container_width=True, key="breadth_put_call", config={"displayModeBar": False})

    render_data_source_note(
        "DATA.xlsx / Equity_Prices + optional Index_Breadth",
        latest_date=str(snap.get("model_date") or "—"),
        caveat="No constituent breadth metric is calculated from sector proxies or index-level price.",
    )
    render_model_note(
        "Data needed to complete the reference panels",
        "For every requested index: Date, index code, advancers minus decliners, "
        "% new 52-week highs/lows, % of constituents above 50DMA/200DMA, and % "
        "with RSI14 above 70/below 30. Index put/call ratio is optional and should "
        "only be shown where an index-specific source series is supplied. A 100-week "
        "average additionally requires at least 100 observed weekly closes.",
    )
    render_section_footer(page)
