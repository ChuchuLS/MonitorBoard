"""charts/pages/sector_rotation.py — 06 · Sector Rotation & Breadth
Descriptive monitor. No attribution, no flows, no forecast.
Uses ONLY pure model functions."""
from __future__ import annotations
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import streamlit as st

from config.pages import get_page
from config.theme import section_color, BG, GRID, TEXT_DIM
from charts.common import (
    render_page_header, render_top_tabs, render_kpi_strip,
    render_explanation_box, render_current_reading_list,
    render_model_note, render_missing_data_warning,
    render_section_footer, render_data_source_note,
)
from config.tickers import SPX_SECTOR_CONFIG
from data.external_loaders import load_spx_sector_weights
from models.sector_rotation import (
    build_sector_snapshot, build_sector_breadth_history,
    build_sector_current_reading, available_sector_inputs,
    build_reference_breadth_dispersion_history,
    build_spx_dispersion_index, DEFAULT_FLAT_THRESHOLD_PCT,
)
from ._context import PageContext

QUADRANT_COLORS = {
    "Leader": "#22c55e", "Improving": "#06b6d4",
    "Weakening": "#eab308", "Laggard": "#ef4444",
    "Neutral / inconclusive": "#666666", "—": "#444444",
}

def _fmt(v, fmt="+.2f", suffix="%"):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    return f"{v:{fmt}}{suffix}"


def _trailing_percentile(series: pd.Series, window: int = 252):
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return np.nan
    trailing = clean.tail(window)
    return float(100 * (trailing <= clean.iloc[-1]).mean())


def render(ctx: PageContext) -> None:
    page = get_page("sector_rotation")
    render_top_tabs(page["id"])

    weights = load_spx_sector_weights()
    reading = build_sector_current_reading(ctx.df, weights)

    if reading["status"] == "Missing data":
        avail = available_sector_inputs(ctx.df, weights)
        missing = reading.get("missing", [])
        render_page_header(page, latest_date="—",
                           viewing="Sector inputs missing")
        render_missing_data_warning(required=missing, missing=missing)
        render_section_footer(page); return

    if reading["status"] == "Partial":
        missing = reading.get("missing", [])
        st.warning(
            "Sector monitor is Partial. Calculations use only available S5 sector "
            "indices and the displayed breadth denominator reflects the actual "
            f"available set. Missing inputs: {', '.join(missing) or '—'}."
        )

    sector_only_date = reading["sector_only_date"]
    relative_model_date = reading["relative_model_date"]
    weight_date = reading["weight_date"]
    reference_history = build_reference_breadth_dispersion_history(ctx.df)
    if reference_history.empty:
        ref_breadth = ref_dispersion = np.nan
        ref_breadth_pctile = ref_dispersion_pctile = np.nan
        ref_denominator = ref_dispersion_count = 0
    else:
        latest_reference = reference_history.iloc[-1]
        ref_breadth = latest_reference.get("above_ma_breadth_pct", np.nan)
        ref_dispersion = latest_reference.get("return_dispersion_pct", np.nan)
        ref_denominator = int(latest_reference.get("breadth_denominator", 0) or 0)
        ref_dispersion_count = int(latest_reference.get("dispersion_valid_count", 0) or 0)
        ref_breadth_pctile = _trailing_percentile(
            reference_history["above_ma_breadth_pct"]
        )
        ref_dispersion_pctile = _trailing_percentile(
            reference_history["return_dispersion_pct"]
        )

    dspx = build_spx_dispersion_index(ctx.df, asof=relative_model_date)
    dspx_latest = float(dspx.iloc[-1]) if not dspx.empty else np.nan
    dspx_date = dspx.index[-1].date() if not dspx.empty else None
    dspx_pctile = _trailing_percentile(dspx) if not dspx.empty else np.nan

    render_page_header(page,
        latest_date=str(relative_model_date).upper(),
        viewing=f"Relative model date · Sector-only: {sector_only_date} · Weight: {weight_date}")

    render_explanation_box(
        "Sector Rotation & Breadth Monitor",
        "Descriptive monitor for the 11 S&P 500 sector indices. Uses SPX as "
        "the benchmark. All relative-return calculations use a <b>fully "
        "aligned</b> observation calendar. Weight context is periodic "
        "(SPX_Sector_Weights). "
        "<b>Not</b> official SPX return attribution, causal factor "
        "attribution, or a forecast. Weight changes are not investor flows.")

    # KPI strip
    kpis = [
        {"label": "Relative model date", "value": str(relative_model_date),
         "sub": f"{reading['relative_obs']} aligned obs",
         "accent": section_color(page["color_key"])},
        {"label": "Above own 50D average",
         "value": _fmt(ref_breadth, ".0f"),
         "sub": f"{ref_denominator}/11 valid · 1Y pctile {_fmt(ref_breadth_pctile, '.0f', '')}"},
        {"label": "21D sector dispersion",
         "value": _fmt(ref_dispersion, ".2f", "pp"),
         "sub": f"{ref_dispersion_count}/11 valid · 1Y pctile {_fmt(ref_dispersion_pctile, '.0f', '')}"},
        {"label": "Cboe DSPX",
         "value": _fmt(dspx_latest, ".2f", ""),
         "sub": (f"{dspx_date} · 1Y pctile {_fmt(dspx_pctile, '.0f', '')}"
                 if dspx_date else "Missing data")},
        {"label": "Weight date", "value": str(weight_date or "—"),
         "sub": f"previous: {reading.get('previous_weight_date') or '—'}"},
        {"label": "Weight sum", "value": _fmt(reading.get("weight_sum_pct"), ".2f"),
         "sub": f"{reading.get('valid_weight_count', 0)}/11 valid sectors"},
        {"label": "Top-three weight share",
         "value": _fmt(reading.get("top_three_weight_share_pct"), ".2f")},
    ]
    # Largest sector weight
    per = reading["per_sector"]
    valid_w = [(p["display_name"], p["weight_pct"]) for p in per if pd.notna(p.get("weight_pct"))]
    if valid_w:
        top_name, top_w = max(valid_w, key=lambda x: x[1])
        kpis.append({"label": "Largest sector weight",
                     "value": _fmt(top_w, ".2f"), "sub": top_name})
    render_kpi_strip(kpis)

    # Sector performance table
    st.markdown("<div style='margin:0.8rem 0 0.3rem;font-size:11px;color:#888;"
                "letter-spacing:0.1em;text-transform:uppercase;'>"
                "Sector performance</div>", unsafe_allow_html=True)
    perf_rows = []
    for p in per:
        perf_rows.append({
            "Sector": p["display_name"], "Ticker": p["ticker"],
            "1D (%)": _fmt(p.get("ret_1d_pct"), "+.2f", ""),
            "5D (%)": _fmt(p.get("ret_5d_pct"), "+.2f", ""),
            "20D (%)": _fmt(p.get("ret_20d_pct"), "+.2f", ""),
            "63D (%)": _fmt(p.get("ret_63d_pct"), "+.2f", ""),
            "5D vs SPX (pp)": _fmt(p.get("rel_ret_5d_pct"), "+.2f", ""),
            "20D vs SPX (pp)": _fmt(p.get("rel_ret_20d_pct"), "+.2f", ""),
            "63D vs SPX (pp)": _fmt(p.get("rel_ret_63d_pct"), "+.2f", ""),
            "Weight (%)": _fmt(p.get("weight_pct"), ".2f", ""),
            "Quadrant": p.get("quadrant", "—"),
            "Status": p.get("status", "—"),
        })
    st.dataframe(pd.DataFrame(perf_rows), hide_index=True, use_container_width=True)

    # Rotation quadrant scatter
    st.markdown("<div style='margin:0.8rem 0 0.3rem;font-size:11px;color:#888;"
                "letter-spacing:0.1em;text-transform:uppercase;'>"
                "Rotation quadrants (63D vs 20D relative return)</div>",
                unsafe_allow_html=True)
    fig_q = go.Figure()
    thr = reading["flat_threshold_pct"]
    # Threshold lines
    fig_q.add_hline(y=thr, line=dict(color="#444", width=0.5, dash="dot"))
    fig_q.add_hline(y=-thr, line=dict(color="#444", width=0.5, dash="dot"))
    fig_q.add_vline(x=thr, line=dict(color="#444", width=0.5, dash="dot"))
    fig_q.add_vline(x=-thr, line=dict(color="#444", width=0.5, dash="dot"))
    fig_q.add_hline(y=0, line=dict(color="#666", width=0.5))
    fig_q.add_vline(x=0, line=dict(color="#666", width=0.5))
    for p in per:
        x = p.get("rel_ret_63d_pct")
        y = p.get("rel_ret_20d_pct")
        w = p.get("weight_pct", 0)
        if pd.isna(x) or pd.isna(y):
            continue
        size = max(10, min(60, (w or 5) * 3))
        fig_q.add_trace(go.Scatter(
            x=[x], y=[y], mode="markers+text",
            marker=dict(size=size, color=QUADRANT_COLORS.get(p["quadrant"], "#666"),
                        line=dict(width=1, color="#111"), opacity=0.85),
            text=[p["display_name"].split()[0][:6]],
            textposition="top center",
            textfont=dict(size=9, color="#ccc"),
            name=p["display_name"],
            hovertemplate=f"<b>{p['display_name']}</b><br>"
                          f"63D rel: {x:+.2f}pp<br>20D rel: {y:+.2f}pp<br>"
                          f"Weight: {w:.2f}%<br>Quadrant: {p['quadrant']}"
                          "<extra></extra>",
            showlegend=False,
        ))
    fig_q.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
        font=dict(family="Inter, system-ui, sans-serif", size=10, color=TEXT_DIM),
        height=440, margin=dict(l=60, r=30, t=25, b=45),
        xaxis=dict(title=f"63D relative return vs SPX (pp)", gridcolor=GRID, zeroline=False),
        yaxis=dict(title=f"20D relative return vs SPX (pp)", gridcolor=GRID, zeroline=False),
    )
    st.plotly_chart(fig_q, use_container_width=True, key="sector_quadrant",
                    config={"displayModeBar": False})
    st.caption(f"Bubble size = latest sector weight ({weight_date}). "
               f"Threshold: ±{thr}pp. Weight, not return contribution.")

    # Breadth & dispersion using the exact definitions on reference-pack page 23.
    if not reference_history.empty:
        st.markdown("<div style='margin:0.8rem 0 0.3rem;font-size:11px;color:#888;"
                    "letter-spacing:0.1em;text-transform:uppercase;'>"
                    "SPX sector breadth · share above own 50D average</div>",
                    unsafe_allow_html=True)
        fig_b = go.Figure()
        fig_b.add_trace(go.Scatter(
            x=reference_history.index,
            y=reference_history["above_ma_breadth_pct"],
            mode="lines", line=dict(color="#22c55e", width=1.4),
            name="Share above own 50D average",
            hovertemplate=(
                "%{x|%Y-%m-%d}<br>Above 50D average: %{y:.0f}%"
                "<extra></extra>"
            ),
        ))
        fig_b.add_hline(y=50, line=dict(color="#444", width=0.5, dash="dot"))
        fig_b.update_layout(template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
            font=dict(family="Inter, system-ui, sans-serif", size=10, color=TEXT_DIM),
            height=260, showlegend=False,
            margin=dict(l=50, r=20, t=25, b=25),
            yaxis=dict(title="% of sectors", gridcolor=GRID, range=[0, 100]),
            xaxis=dict(showgrid=False))
        st.plotly_chart(fig_b, use_container_width=True, key="sector_reference_breadth",
                        config={"displayModeBar": False})
        st.caption(
            "Reference-pack definition: number of valid S&P 500 sector indices "
            "above their own 50-observation moving average divided by the actual "
            "valid-sector denominator."
        )

        st.markdown("<div style='margin:0.8rem 0 0.3rem;font-size:11px;color:#888;"
                    "letter-spacing:0.1em;text-transform:uppercase;'>"
                    "Cross-sector return dispersion · trailing 21 observations</div>",
                    unsafe_allow_html=True)
        has_dspx = not dspx.empty
        fig_d = make_subplots(specs=[[{"secondary_y": has_dspx}]])
        fig_d.add_trace(go.Scatter(
            x=reference_history.index,
            y=reference_history["return_dispersion_pct"], mode="lines",
            line=dict(color="#a855f7", width=1.2),
            name="Realised 21D cross-sector dispersion",
            hovertemplate=(
                "%{x|%Y-%m-%d}<br>Realised dispersion: %{y:.2f} pp"
                "<extra></extra>"
            ),
        ), secondary_y=False)
        if has_dspx:
            fig_d.add_trace(go.Scatter(
                x=dspx.index, y=dspx, mode="lines",
                line=dict(color="#f97316", width=1.2),
                name="Cboe DSPX implied 30D dispersion",
                hovertemplate=(
                    "%{x|%Y-%m-%d}<br>Cboe DSPX: %{y:.2f}"
                    "<extra></extra>"
                ),
            ), secondary_y=True)
        fig_d.update_layout(
            template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
            font=dict(family="Inter, system-ui, sans-serif", size=10, color=TEXT_DIM),
            height=270, showlegend=True,
            legend=dict(orientation="h", y=1.12, x=0, font=dict(size=9)),
            margin=dict(l=50, r=55 if has_dspx else 20, t=35, b=25),
            xaxis=dict(showgrid=False),
        )
        fig_d.update_yaxes(
            title_text="Realised cross-sectional std (pp)", gridcolor=GRID,
            secondary_y=False,
        )
        if has_dspx:
            fig_d.update_yaxes(
                title_text="Cboe DSPX index level", showgrid=False,
                secondary_y=True,
            )
        st.plotly_chart(fig_d, use_container_width=True, key="sector_disp",
                        config={"displayModeBar": False})
        if has_dspx:
            st.caption(
                "Purple = realised cross-sectional dispersion of sector returns. "
                "Orange = Cboe DSPX, a separate forward-looking 30-calendar-day "
                "implied-dispersion index. Separate axes are used; the two series "
                "are not interchangeable."
            )
        else:
            st.caption(
                "Cboe DSPX overlay requested, but DSPX INDEX is not present in "
                "DATA.xlsx. No substitute or synthetic series is used. The chart "
                "therefore shows only realised cross-sectional sector-return "
                "dispersion."
            )

    with st.expander("Additional return-breadth diagnostics", expanded=False):
        horizon_choice = st.selectbox(
            "Return horizon", [5, 20, 63], index=1, key="sector_bh_horizon"
        )
        bh = build_sector_breadth_history(ctx.df, horizon=horizon_choice)
        if bh.empty:
            st.caption("Return-breadth history is unavailable for this horizon.")
        else:
            fig_extra = go.Figure()
            fig_extra.add_trace(go.Scatter(
                x=bh.index, y=bh["positive_breadth_pct"], mode="lines",
                line=dict(color="#22c55e", width=1.2), name="Positive return breadth",
            ))
            fig_extra.add_trace(go.Scatter(
                x=bh.index, y=bh["relative_breadth_pct"], mode="lines",
                line=dict(color="#06b6d4", width=1.2), name="Outperforming SPX",
            ))
            fig_extra.add_hline(y=50, line=dict(color="#444", width=0.5, dash="dot"))
            fig_extra.update_layout(
                template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
                font=dict(family="Inter, system-ui, sans-serif", size=10, color=TEXT_DIM),
                height=260, legend=dict(orientation="h", y=1.08, x=0),
                margin=dict(l=50, r=20, t=25, b=25),
                yaxis=dict(title="% of valid sectors", gridcolor=GRID, range=[0, 100]),
                xaxis=dict(showgrid=False),
            )
            st.plotly_chart(
                fig_extra, use_container_width=True, key="sector_return_breadth",
                config={"displayModeBar": False},
            )
            st.caption(
                "Supplementary diagnostics only. The primary breadth and "
                "dispersion panels above follow the reference-pack definitions."
            )

    # Sector weight table
    st.markdown("<div style='margin:0.8rem 0 0.3rem;font-size:11px;color:#888;"
                "letter-spacing:0.1em;text-transform:uppercase;'>"
                "Sector weight table</div>", unsafe_allow_html=True)
    w_rows = []
    for p in per:
        w_rows.append({
            "Sector": p["display_name"],
            "Latest weight (%)": _fmt(p.get("weight_pct"), ".2f", ""),
            "1-period change (pp)": _fmt(p.get("chg_1p_pp"), "+.2f", ""),
            "3-period change (pp)": _fmt(p.get("chg_3p_pp"), "+.2f", ""),
            "12-period change (pp)": _fmt(p.get("chg_12p_pp"), "+.2f", ""),
            "Weight date": str(weight_date or "—"),
            "Weight status": "Ready" if pd.notna(p.get("weight_pct")) else "Missing data",
            "Price status": p.get("status", "—"),
        })
    st.dataframe(pd.DataFrame(w_rows), hide_index=True, use_container_width=True)
    st.caption("Weight changes may reflect relative price performance, index "
               "rebalancing, constituent changes, or classification changes. "
               "They are NOT investor flows or capital rotation.")

    # Current Reading
    items = [
        ("Relative model date", str(relative_model_date)),
        ("Sector-only date", str(sector_only_date)),
        ("Weight date", str(weight_date or "—")),
        ("Previous weight date", str(reading.get("previous_weight_date") or "—")),
        ("Weight sum", _fmt(reading.get("weight_sum_pct"), ".2f")),
        ("Top-three weight share", _fmt(reading.get("top_three_weight_share_pct"), ".2f")),
        (f"Positive breadth ({reading['short_window']}D)",
         f"{reading['positive_count']}/{reading['positive_denom']} "
         f"({_fmt(reading.get('positive_breadth_pct'), '.0f')})"),
        (f"SPX-outperform breadth ({reading['short_window']}D)",
         f"{reading['outperf_count']}/{reading['positive_denom']} "
         f"({_fmt(reading.get('relative_breadth_pct'), '.0f')})"),
        (f"{reading['short_window']}D dispersion",
         _fmt(reading.get('dispersion_pct'), '.2f')),
        ("Above own 50D average",
         f"{_fmt(ref_breadth, '.0f')} · 1Y percentile {_fmt(ref_breadth_pctile, '.0f', '')}"),
        ("21D cross-sector dispersion",
         f"{_fmt(ref_dispersion, '.2f', 'pp')} · 1Y percentile {_fmt(ref_dispersion_pctile, '.0f', '')}"),
        ("Cboe DSPX implied dispersion",
         (f"{_fmt(dspx_latest, '.2f', '')} · {dspx_date} · 1Y percentile "
          f"{_fmt(dspx_pctile, '.0f', '')}" if dspx_date else "Missing data")),
    ]
    if reading.get("top_rel"):
        top_str = "; ".join(f"{n} ({v:+.2f}pp)" for n, v in reading["top_rel"])
        items.append((f"Top 3 relative ({reading['short_window']}D)", top_str))
    if reading.get("bottom_rel"):
        bot_str = "; ".join(f"{n} ({v:+.2f}pp)" for n, v in reading["bottom_rel"])
        items.append((f"Lowest-ranked 3 relative ({reading['short_window']}D)", bot_str))
    q_counts = reading.get("quadrant_counts", {})
    if q_counts:
        q_str = ", ".join(f"{k}={v}" for k, v in q_counts.items())
        items.append(("Quadrant counts", q_str))
    render_current_reading_list("Current reading", items)

    render_model_note("Methodology",
        "<b>Sector indices:</b> 11 S&P 500 sector indices (S5xxx). "
        "<b>Benchmark:</b> SPX INDEX. "
        "<b>Returns:</b> log returns in %; relative returns in percentage points. "
        "<b>Sector-only calendar:</b> common date for the available S5 sectors; "
        "Ready status requires all 11. "
        "<b>Relative calendar:</b> common date for the available sectors and SPX; "
        "breadth denominators use the actual valid sector count. "
        f"<b>Rotation quadrants:</b> {reading['short_window']}D and "
        f"{reading['long_window']}D relative returns with ±{DEFAULT_FLAT_THRESHOLD_PCT}pp "
        "flat threshold (diagnostic, not industry-standard). "
        "<b>Weights:</b> periodic SPX_Sector_Weights (not daily). "
        "Weight changes are NOT investor flows. "
        "<b>Reference-pack breadth:</b> share of sectors above their own 50-observation moving average. "
        "<b>Reference-pack dispersion:</b> cross-sectional population standard deviation of trailing 21-observation simple sector returns. "
        "When DSPX INDEX is present it is overlaid on a separate axis as Cboe's "
        "forward-looking implied-dispersion index; it is never synthesised. "
        "Subtracting the common SPX return would produce the identical realised dispersion. "
        "ETF proxies (XLC/XLY/XLP/XLE/XLV/XLI/XLB/XLRE/XLU) are excluded from "
        "the production model. "
        "<b>Descriptive only</b> — no causal attribution, official attribution, "
        "fair-value, or forecast claim.")

    render_data_source_note("DATA.xlsx / Sheet1 + SPX_Sector_Weights",
                             str(relative_model_date))
    render_section_footer(page)
