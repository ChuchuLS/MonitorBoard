"""A2 · CTA Score Backtest — fixed-specification, limited-sample evaluation."""
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
from config.theme import ACCENT_GREEN, ACCENT_RED, BG, GRID, TEXT_DIM, section_color
from data.external_loaders import load_pulsar
from models.scoring.backtest import BacktestConfig, build_score_backtest

from ._context import PageContext


PRIMARY_CONFIG = BacktestConfig(rebalance="weekly", top_n=3)


def _fmt(value, fmt="+.3f", suffix="") -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:{fmt}}{suffix}"


def _chart_layout(height: int, y_title: str) -> dict:
    return dict(
        template="plotly_dark",
        paper_bgcolor=BG,
        plot_bgcolor=BG,
        font=dict(family="Inter, system-ui, sans-serif", size=10, color=TEXT_DIM),
        height=height,
        margin=dict(l=58, r=20, t=28, b=34),
        xaxis=dict(showgrid=False),
        yaxis=dict(title=y_title, gridcolor=GRID),
        showlegend=False,
    )


def _render_period_charts(periods: pd.DataFrame, unit: str, key_prefix: str) -> None:
    dates = pd.to_datetime(periods["outcome_date"])
    spread = pd.to_numeric(periods["top_minus_bottom"], errors="coerce")
    colors = [ACCENT_GREEN if value > 0 else ACCENT_RED for value in spread]

    fig_spread = go.Figure(go.Bar(
        x=dates,
        y=spread,
        marker_color=colors,
        customdata=pd.to_datetime(periods["signal_date"]).dt.strftime("%Y-%m-%d"),
        hovertemplate=(
            "Signal: %{customdata}<br>Outcome: %{x|%Y-%m-%d}<br>"
            f"Top 3 − Bottom 3: %{{y:+.3f}} {unit}<extra></extra>"
        ),
    ))
    fig_spread.add_hline(y=0, line=dict(color="#666", width=0.8))
    fig_spread.update_layout(**_chart_layout(310, f"Top 3 − Bottom 3 ({unit})"))
    st.plotly_chart(
        fig_spread,
        use_container_width=True,
        key=f"{key_prefix}_spread",
        config={"displayModeBar": False},
    )

    rank_ic = pd.to_numeric(periods["rank_ic"], errors="coerce")
    fig_ic = go.Figure(go.Scatter(
        x=dates,
        y=rank_ic,
        mode="lines+markers",
        line=dict(color="#e8b931", width=1.4),
        marker=dict(size=5),
        hovertemplate="%{x|%Y-%m-%d}<br>Spearman rank IC: %{y:+.3f}<extra></extra>",
    ))
    fig_ic.add_hline(y=0, line=dict(color="#666", width=0.8))
    layout = _chart_layout(260, "Spearman rank IC")
    layout["yaxis"] = dict(title="Spearman rank IC", gridcolor=GRID, range=[-1, 1])
    fig_ic.update_layout(**layout)
    st.plotly_chart(
        fig_ic,
        use_container_width=True,
        key=f"{key_prefix}_rank_ic",
        config={"displayModeBar": False},
    )


def _render_period_table(periods: pd.DataFrame, unit: str) -> None:
    table = periods[[
        "signal_date", "outcome_date", "n_assets", "top_codes", "bottom_codes",
        "top_outcome", "bottom_outcome", "top_minus_bottom", "rank_ic",
    ]].copy()
    table["signal_date"] = pd.to_datetime(table["signal_date"]).dt.date.astype(str)
    table["outcome_date"] = pd.to_datetime(table["outcome_date"]).dt.date.astype(str)
    for column in ("top_outcome", "bottom_outcome", "top_minus_bottom"):
        table[column] = table[column].apply(
            lambda value: f"{value:+.3f} {unit}" if pd.notna(value) else "—"
        )
    table["rank_ic"] = table["rank_ic"].apply(
        lambda value: f"{value:+.3f}" if pd.notna(value) else "—"
    )
    table = table.rename(columns={
        "signal_date": "Signal date",
        "outcome_date": "Outcome date",
        "n_assets": "N",
        "top_codes": "Top 3",
        "bottom_codes": "Bottom 3",
        "top_outcome": "Top outcome",
        "bottom_outcome": "Bottom outcome",
        "top_minus_bottom": "Spread",
        "rank_ic": "Rank IC",
    })
    st.dataframe(
        table,
        hide_index=True,
        use_container_width=True,
        height=42 + 34 * len(table),
    )


def _render_chronological_stability(frame: pd.DataFrame, unit: str) -> None:
    st.markdown("#### Chronological stability")
    if frame is None or frame.empty:
        st.info("At least eight usable periods are required for two four-period slices.")
        return
    table = frame.copy()
    table["window"] = (
        table["first_signal_date"].astype(str)
        + " → "
        + table["last_outcome_date"].astype(str)
    )
    table["average_top_minus_bottom"] = table["average_top_minus_bottom"].map(
        lambda value: f"{value:+.3f} {unit}" if pd.notna(value) else "—"
    )
    table["median_top_minus_bottom"] = table["median_top_minus_bottom"].map(
        lambda value: f"{value:+.3f} {unit}" if pd.notna(value) else "—"
    )
    table["hit_rate_pct"] = table["hit_rate_pct"].map(
        lambda value: f"{value:.1f}%" if pd.notna(value) else "—"
    )
    table["mean_rank_ic"] = table["mean_rank_ic"].map(
        lambda value: f"{value:+.3f}" if pd.notna(value) else "—"
    )
    table = table[[
        "slice", "window", "periods", "average_top_minus_bottom",
        "median_top_minus_bottom", "hit_rate_pct", "mean_rank_ic",
    ]].rename(columns={
        "slice": "Slice",
        "window": "Observed window",
        "periods": "Periods",
        "average_top_minus_bottom": "Average spread",
        "median_top_minus_bottom": "Median spread",
        "hit_rate_pct": "Positive spread",
        "mean_rank_ic": "Mean rank IC",
    })
    st.dataframe(table, hide_index=True, use_container_width=True)
    st.caption(
        "The split compares two contiguous halves. It is not a train/test or "
        "historical-vintage out-of-sample test."
    )


def _render_leave_one_out(diagnostic: dict, unit: str) -> None:
    if diagnostic.get("status") != "Available":
        return
    low = diagnostic.get("leave_one_out_mean_min")
    high = diagnostic.get("leave_one_out_mean_max")
    sign_text = "unchanged" if diagnostic.get("mean_sign_stable") else "changed"
    st.info(
        "Single-period dependence check: after removing each observed week in turn, "
        f"the average spread ranges from {_fmt(low, '+.3f', f' {unit}')} to "
        f"{_fmt(high, '+.3f', f' {unit}')}; its sign is {sign_text}. This only "
        "tests dependence on one week within the primary specification."
    )


def _render_sensitivity(frame: pd.DataFrame, unit: str) -> None:
    st.markdown("#### Fixed-specification sensitivity")
    if frame is None or frame.empty:
        st.info("Sensitivity diagnostics are unavailable.")
        return
    table = frame.copy()
    table["specification"] = table.apply(
        lambda row: (
            f"{row['specification']} (primary)"
            if row["is_primary"] else row["specification"]
        ),
        axis=1,
    )
    table["average_top_minus_bottom"] = table["average_top_minus_bottom"].map(
        lambda value: f"{value:+.3f} {unit}" if pd.notna(value) else "—"
    )
    table["median_top_minus_bottom"] = table["median_top_minus_bottom"].map(
        lambda value: f"{value:+.3f} {unit}" if pd.notna(value) else "—"
    )
    table["hit_rate_pct"] = table["hit_rate_pct"].map(
        lambda value: f"{value:.1f}%" if pd.notna(value) else "—"
    )
    table["mean_rank_ic"] = table["mean_rank_ic"].map(
        lambda value: f"{value:+.3f}" if pd.notna(value) else "—"
    )
    table = table[[
        "specification", "periods", "average_top_minus_bottom",
        "median_top_minus_bottom", "hit_rate_pct", "mean_rank_ic",
    ]].rename(columns={
        "specification": "Pre-declared variant",
        "periods": "Periods",
        "average_top_minus_bottom": "Average spread",
        "median_top_minus_bottom": "Median spread",
        "hit_rate_pct": "Positive spread",
        "mean_rank_ic": "Mean rank IC",
    })
    st.dataframe(table, hide_index=True, use_container_width=True)
    st.caption(
        "These five variants are reported together and are not used to select a "
        "winning specification. The production Score remains 50/50 and Top 3."
    )


def _render_market_tab(
    periods: pd.DataFrame,
    summary: dict,
    market: str,
    chronological: pd.DataFrame,
    leave_one_out: dict,
    sensitivity: pd.DataFrame,
) -> None:
    if periods.empty:
        render_missing_data_warning(
            required=["90-day factor lookback", "score inputs", "next-period outcome"],
            missing=["No usable backtest periods"],
            message=f"{market} backtest is unavailable from the current workbook.",
        )
        return

    unit = str(summary.get("outcome_unit", ""))
    accent = section_color("scoring")
    render_kpi_strip([
        {
            "label": "Usable periods",
            "value": str(summary.get("periods", 0)),
            "sub": f"{summary.get('first_signal_date', '—')} → {summary.get('last_outcome_date', '—')}",
            "accent": accent,
        },
        {
            "label": "Average spread",
            "value": _fmt(summary.get("average_top_minus_bottom"), "+.3f", f" {unit}"),
            "sub": "Top 3 minus Bottom 3",
        },
        {
            "label": "Median spread",
            "value": _fmt(summary.get("median_top_minus_bottom"), "+.3f", f" {unit}"),
            "sub": "Across usable periods",
        },
        {
            "label": "Positive spread",
            "value": _fmt(summary.get("hit_rate_pct"), ".1f", "%"),
            "sub": "Share of usable periods",
        },
        {
            "label": "Mean rank IC",
            "value": _fmt(summary.get("mean_rank_ic"), "+.3f"),
            "sub": "Spearman cross-sectional IC",
        },
        {
            "label": "Status",
            "value": str(summary.get("status", "Missing data")),
            "sub": "Not strategy validation",
        },
    ])

    if market == "Equity":
        st.caption(
            "Outcome is the next-week cash-index price return. All 18 indices use "
            "the same four-factor Macro + EPS score; FCI is not an input."
        )
    else:
        st.caption(
            "Outcome is minus the next-week 10Y yield change in basis points. This "
            "is a direction proxy, not sovereign-bond total-return P&L."
        )

    _render_period_charts(periods, unit, market.lower())
    _render_chronological_stability(chronological, unit)
    _render_leave_one_out(leave_one_out, unit)
    _render_sensitivity(sensitivity, unit)
    st.markdown("#### Period detail")
    _render_period_table(periods, unit)
    st.download_button(
        f"Download {market.lower()} periods as CSV",
        data=periods.to_csv(index=False).encode("utf-8"),
        file_name=f"cta_score_backtest_{market.lower()}.csv",
        mime="text/csv",
        key=f"download_{market.lower()}_backtest",
    )


def render(ctx: PageContext) -> None:
    page = get_page("scoring_backtest")
    render_top_tabs(page["id"])
    data = load_pulsar()
    result = build_score_backtest(data or {}, PRIMARY_CONFIG)
    equity = result["equity_periods"]
    rates = result["rates_periods"]
    summaries = [result["equity_summary"], result["rates_summary"]]
    latest_dates = [s.get("last_outcome_date") for s in summaries if s.get("last_outcome_date")]
    latest = max(latest_dates) if latest_dates else None

    render_page_header(
        page,
        latest_date=str(latest or "—").upper(),
        viewing="Weekly · fixed 50/50 pillar weights · Top 3 minus Bottom 3",
    )
    render_explanation_box(
        "Historical signal check — not a validated trading strategy",
        "The specification is fixed to the Board defaults: weekly non-overlapping "
        "observations, full 90-calendar-day factor lookback, and Top 3 minus Bottom 3. "
        "The page deliberately provides no parameter-optimisation controls. Every "
        "usable period is displayed; missing outcomes are not replaced by zero or a proxy.",
    )
    st.warning(
        "The available high-frequency factor history begins on 2026-02-16. "
        "Macro observations are revised rather than historical vintages, equity "
        "returns are cash-index price returns, rates use a yield-change proxy, and "
        "transaction costs are not included. The current workbook provides "
        f"{result['equity_summary'].get('periods', 0)} equity and "
        f"{result['rates_summary'].get('periods', 0)} rates weekly observations; "
        "fewer than 26 remains an insufficient sample. Sharpe ratio, drawdown and "
        "cumulative portfolio P&L are therefore intentionally not presented."
    )

    tab_equity, tab_rates = st.tabs(["Equity Score", "Rates Score"])
    with tab_equity:
        _render_market_tab(
            equity,
            result["equity_summary"],
            "Equity",
            result["equity_chronological_stability"],
            result["equity_leave_one_out"],
            result["equity_sensitivity"],
        )
    with tab_rates:
        _render_market_tab(
            rates,
            result["rates_summary"],
            "Rates",
            result["rates_chronological_stability"],
            result["rates_leave_one_out"],
            result["rates_sensitivity"],
        )

    render_model_note(
        "Primary specification and limitations",
        "<b>Signal timing:</b> each score uses observations dated on or before the "
        "signal date. <b>Equity:</b> four-factor Macro 50% + EPS 50%; FCI contributes "
        "0%. <b>Rates:</b> Macro 50% + Markets 50%. <b>Portfolio test:</b> equal-weight "
        "Top 3 minus equal-weight Bottom 3 for the immediately following weekly "
        "observation. <b>Limitations:</b> revised macro data, limited history, gross "
        "returns and no investable sovereign total-return series. The chronological, "
        "leave-one-period-out and fixed-grid panels are robustness diagnostics; they "
        "do not turn the current sample into a validated or vintage-safe backtest.",
    )
    render_data_source_note(
        "DATA.xlsx / scoring sheets",
        latest_date=str(latest or "—"),
        caveat="Limited-sample signal evaluation; no claim of statistical validation or deployable P&L.",
    )
    render_section_footer(page)
