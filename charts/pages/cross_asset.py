"""
charts/pages/cross_asset.py
===========================
Section 05 — Cross-Asset Regime Timeline.

8-regime directional classification using vol-scaled signals: 20-day change
in SPX / UST 10Y yield / DXY divided by 21-day trailing realized volatility.
The sign of each vol-scaled signal determines UP/DOWN. 2^3 = 8 regimes.

A simplified "raw sign" mode is available as a toggle but is NOT the
PDF-reference methodology. The PCA-based model lives in market_linkage.py.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config.pages import get_page
from config.theme import section_color, BG, GRID, TEXT_DIM, DARK_LAYOUT

from charts.common import (
    render_page_header, render_top_tabs, render_kpi_strip,
    render_explanation_box, render_model_note,
    render_missing_data_warning, render_section_footer,
)
from data.external_loaders import load_crossasset

from ._context import PageContext


REQUIRED_COLUMNS = ["SPX", "USGG10YR", "DXY"]

REGIMES_8 = {
    "R1": {"spx": "UP",   "rates": "UP",   "dxy": "UP",   "label": "SPX ↑ Rates ↑ DXY ↑", "color": "#22c55e"},
    "R2": {"spx": "UP",   "rates": "UP",   "dxy": "DOWN", "label": "SPX ↑ Rates ↑ DXY ↓", "color": "#06b6d4"},
    "R3": {"spx": "UP",   "rates": "DOWN", "dxy": "UP",   "label": "SPX ↑ Rates ↓ DXY ↑", "color": "#84cc16"},
    "R4": {"spx": "UP",   "rates": "DOWN", "dxy": "DOWN", "label": "SPX ↑ Rates ↓ DXY ↓", "color": "#3b82f6"},
    "R5": {"spx": "DOWN", "rates": "UP",   "dxy": "UP",   "label": "SPX ↓ Rates ↑ DXY ↑", "color": "#f97316"},
    "R6": {"spx": "DOWN", "rates": "UP",   "dxy": "DOWN", "label": "SPX ↓ Rates ↑ DXY ↓", "color": "#eab308"},
    "R7": {"spx": "DOWN", "rates": "DOWN", "dxy": "UP",   "label": "SPX ↓ Rates ↓ DXY ↑", "color": "#a855f7"},
    "R8": {"spx": "DOWN", "rates": "DOWN", "dxy": "DOWN", "label": "SPX ↓ Rates ↓ DXY ↓", "color": "#ef4444"},
}


def classify_8regime(prices: pd.DataFrame, mode: str = "vol_scaled",
                     lookback: int = 20, vol_window: int = 21) -> pd.DataFrame:
    """Classify each day into one of 8 directional regimes.

    mode = "vol_scaled" (default, PDF-reference): 20D change divided by 21D
           trailing realized volatility.
    mode = "raw_sign" : simple sign of the N-day change (no vol scaling).
    """
    spx_ret = np.log(prices["SPX"]).diff()
    ust_diff = prices["USGG10YR"].diff()
    dxy_ret = np.log(prices["DXY"]).diff()

    if mode == "vol_scaled":
        spx_20d = np.log(prices["SPX"]).diff(lookback)
        ust_20d = prices["USGG10YR"].diff(lookback)
        dxy_20d = np.log(prices["DXY"]).diff(lookback)

        spx_vol = spx_ret.rolling(vol_window).std()
        ust_vol = ust_diff.rolling(vol_window).std()
        dxy_vol = dxy_ret.rolling(vol_window).std()

        spx_sig = spx_20d / spx_vol.replace(0, np.nan)
        ust_sig = ust_20d / ust_vol.replace(0, np.nan)
        dxy_sig = dxy_20d / dxy_vol.replace(0, np.nan)
    else:
        spx_sig = np.log(prices["SPX"]).diff(lookback)
        ust_sig = prices["USGG10YR"].diff(lookback)
        dxy_sig = np.log(prices["DXY"]).diff(lookback)

    def _regime(row):
        s = "UP" if row["spx"] >= 0 else "DOWN"
        r = "UP" if row["rates"] >= 0 else "DOWN"
        d = "UP" if row["dxy"] >= 0 else "DOWN"
        for rk, rv in REGIMES_8.items():
            if rv["spx"] == s and rv["rates"] == r and rv["dxy"] == d:
                return rk
        return "R1"

    df = pd.DataFrame({
        "spx": spx_sig, "rates": ust_sig, "dxy": dxy_sig,
        "spx_signal": spx_sig, "rates_signal": ust_sig, "dxy_signal": dxy_sig,
    }).dropna()
    df["regime"] = df.apply(_regime, axis=1)
    return df


def _days_in_current(regime_series: pd.Series) -> int:
    """Count how many consecutive days the latest regime has been active."""
    if regime_series.empty:
        return 0
    current = regime_series.iloc[-1]
    count = 0
    for v in regime_series.iloc[::-1]:
        if v == current:
            count += 1
        else:
            break
    return count


def _regime_stats(regime_series: pd.Series, window_years: int = 2) -> pd.DataFrame:
    """Regime frequency table over the trailing window_years period."""
    if regime_series.empty:
        return pd.DataFrame()
    cutoff = regime_series.index.max() - pd.DateOffset(years=window_years)
    s = regime_series.loc[regime_series.index >= cutoff]
    total = len(s)
    current = s.iloc[-1] if len(s) else None

    # Build runs
    changes = s != s.shift()
    run_ids = changes.cumsum()
    runs_list = []
    for _, grp in pd.DataFrame({"regime": s, "run": run_ids}).groupby("run"):
        runs_list.append({"regime": grp["regime"].iloc[0], "duration": len(grp)})
    runs_df = pd.DataFrame(runs_list)

    rows = []
    for i in range(1, 9):
        rk = f"R{i}"
        info = REGIMES_8[rk]
        sub = runs_df[runs_df["regime"] == rk]
        days = int(sub["duration"].sum()) if len(sub) else 0
        n_runs = len(sub)
        avg_run = float(sub["duration"].mean()) if n_runs else 0
        rows.append({
            "Regime": rk,
            "Description": info["label"],
            "Days": days,
            f"% of {window_years}Y": f"{days / total * 100:.1f}%" if total else "—",
            "Runs": n_runs,
            "AvgRun": round(avg_run, 1),
            "Active": rk == current,
        })
    return pd.DataFrame(rows)


def render(ctx: PageContext) -> None:
    page = get_page("cross_asset")
    color = section_color(page["color_key"])

    render_top_tabs(page["id"])

    prices = load_crossasset()

    # Column check — all three required
    if prices is None:
        render_page_header(page, latest_date="—")
        render_missing_data_warning(
            required=REQUIRED_COLUMNS,
            missing=["Required cross-asset columns not found in DATA.xlsx"],
        )
        render_section_footer(page)
        return

    missing_cols = [c for c in REQUIRED_COLUMNS if c not in prices.columns]
    if missing_cols:
        render_page_header(page, latest_date="—")
        render_missing_data_warning(
            required=REQUIRED_COLUMNS,
            available=[c for c in REQUIRED_COLUMNS if c in prices.columns],
            missing=missing_cols,
            message="DATA.xlsx Sheet1 is missing required cross-asset columns.",
        )
        render_section_footer(page)
        return

    data_latest = prices.index.max().strftime("%b %d, %Y").upper()
    render_page_header(page, latest_date=data_latest,
                       viewing=f"Data source: DATA.xlsx / Sheet1 cross-asset columns · {len(prices):,} rows")

    render_explanation_box(
        "8-regime vol-scaled directional classification",
        "Each trading day is classified by the <b>sign of a vol-scaled signal</b> "
        "in three assets: <b>SPX</b>, <b>UST 10Y yield</b>, <b>DXY</b>. "
        "Default: <b>20-day change ÷ 21-day trailing realized volatility</b>. "
        "This produces 2³ = 8 directional regimes. A 'raw sign' mode (unscaled "
        "N-day change) is available as a simplified toggle but is NOT the "
        "PDF-reference methodology.",
    )

    c1, c2 = st.columns([1, 3])
    with c1:
        mode = st.radio("Signal mode", ["Vol-scaled (PDF ref)", "Raw sign (simplified)"],
                        index=0, key="ca8_mode", horizontal=False)
    mode_key = "vol_scaled" if "Vol-scaled" in mode else "raw_sign"

    result = classify_8regime(prices, mode=mode_key)
    if result.empty:
        st.warning("Insufficient data.")
        render_section_footer(page)
        return

    current = result["regime"].iloc[-1]
    cur_info = REGIMES_8[current]
    days_in = _days_in_current(result["regime"])
    last_row = result.iloc[-1]

    render_kpi_strip([
        {"label": "Current regime", "value": cur_info["label"],
         "sub": f"{current} · {days_in} days in regime · {result.index[-1].date()}",
         "accent": cur_info["color"]},
        {"label": "SPX signal", "value": f"{last_row.get('spx_signal', 0):+.2f}",
         "sub": "vol-scaled" if mode_key == "vol_scaled" else "raw"},
        {"label": "Rates signal", "value": f"{last_row.get('rates_signal', 0):+.2f}"},
        {"label": "DXY signal", "value": f"{last_row.get('dxy_signal', 0):+.2f}"},
    ])

    # Regime timeline
    st.markdown("<div style='margin:0.8rem 0 0.3rem;font-size:11px;color:#888;"
                "letter-spacing:0.1em;text-transform:uppercase;'>"
                "Regime timeline</div>", unsafe_allow_html=True)

    legend_bits = " &nbsp; ".join(
        f"<span style='display:inline-block;width:8px;height:8px;"
        f"background:{REGIMES_8[f'R{i}']['color']};vertical-align:middle;"
        f"margin-right:3px;border-radius:1px;'></span>"
        f"<span style='color:#aaa;font-size:9px;'>{REGIMES_8[f'R{i}']['label']}</span>"
        for i in range(1, 9)
    )
    st.markdown(f"<div style='margin-bottom:6px;line-height:2;'>{legend_bits}</div>",
                unsafe_allow_html=True)

    regime_series = result["regime"]
    changes = regime_series != regime_series.shift()
    run_ids = changes.cumsum()
    runs = []
    for _, grp in result.groupby(run_ids):
        runs.append({"regime": grp["regime"].iloc[0],
                      "start": grp.index[0], "end": grp.index[-1],
                      "duration": len(grp)})
    runs_df = pd.DataFrame(runs)

    fig = go.Figure()
    for _, row in runs_df.iterrows():
        c = REGIMES_8[row["regime"]]["color"]
        fig.add_trace(go.Scatter(
            x=[row["start"], row["end"]], y=[0.5, 0.5],
            mode="lines", line=dict(color=c, width=24),
            hovertext=f"{REGIMES_8[row['regime']]['label']}<br>"
                      f"{row['start'].date()} → {row['end'].date()}<br>{row['duration']}d",
            hoverinfo="text", showlegend=False))
    fig.update_layout(**DARK_LAYOUT, height=100,
                      margin=dict(l=10, r=10, t=5, b=20),
                      yaxis=dict(visible=False, range=[0, 1]),
                      xaxis=dict(showgrid=False, tickfont=dict(size=10)))
    st.plotly_chart(fig, use_container_width=True, key="ca8_timeline",
                    config={"displayModeBar": False})

    # Regime frequency table (2Y window)
    with st.expander("Regime frequency (trailing 2 years)", expanded=False):
        stats = _regime_stats(regime_series, window_years=2)
        st.dataframe(stats, hide_index=True, use_container_width=True)

    render_model_note(
        "Methodology",
        "<b>Default (vol-scaled):</b> 20-day log return (SPX, DXY) or yield "
        "change (UST 10Y) divided by 21-day trailing realized volatility. "
        "The sign of each vol-scaled signal determines UP/DOWN. This matches "
        "the PDF-reference methodology.<br>"
        "<b>Raw sign (simplified):</b> sign of the raw 20-day change with no "
        "vol normalization. NOT the PDF-reference model.<br>"
        "The PCA-based dominant-theme model (4 relative regimes) is on the "
        "next page: <b>05b · Market Linkage & Correlations</b>.",
    )

    render_section_footer(page)
