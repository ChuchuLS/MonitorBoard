"""
charts/pages/scoring.py
=======================
Section 08 — Global Scoring (Phase 2: LIVE).

Integrates the Pulsar/CTA cross-sectional scoring model: ranks 10 sovereign
bond markets on macro + market factors, and 18 requested equity indices on macro +
EPS revisions. Uses DATA.xlsx / scoring sheets.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from config.pages import get_page
from config.theme import section_color

from charts.common import (
    render_page_header, render_top_tabs, render_kpi_strip,
    render_explanation_box, render_model_note,
    render_missing_data_warning, render_section_footer,
)
from data.external_loaders import load_pulsar

from ._context import PageContext


def _score_color(v: float) -> str:
    if pd.isna(v): return "#666"
    if v > 0.5: return "#5fb04f"
    if v > 0: return "#8bc87c"
    if v > -0.5: return "#d99830"
    return "#d04848"


def _score_bar(v: float, max_abs: float = 2.0) -> str:
    if pd.isna(v): return ""
    pct = min(abs(v) / max_abs * 100, 100)
    color = _score_color(v)
    direction = "right" if v >= 0 else "left"
    return (
        f"<div style='width:100%;height:14px;background:#1a1a1a;border-radius:2px;"
        f"position:relative;'>"
        f"<div style='position:absolute;{direction}:50%;width:{pct/2:.0f}%;"
        f"height:100%;background:{color};border-radius:2px;'></div>"
        f"<div style='position:absolute;left:50%;top:0;width:1px;height:100%;"
        f"background:#444;'></div></div>"
    )


def _render_scores_table(scores: pd.DataFrame, label_col: str,
                         score_col: str = "score", key: str = "tbl"):
    """Render a scoring table with inline bar charts."""
    if scores.empty:
        st.info("No scores available.")
        return

    cols_to_show = [c for c in ["macro_factor_count", "macro", "markets", "score", "p5d", "p1m", "p3m"]
                    if c in scores.columns]
    disp = scores[[label_col] + cols_to_show].copy()
    disp["Status"] = scores.get(
        "status",
        pd.Series(np.where(pd.to_numeric(scores[score_col], errors="coerce").notna(),
                           "Ready", "Missing data"), index=scores.index),
    )
    disp = disp.rename(columns={label_col: "Name"})

    # Format numbers
    for c in cols_to_show:
        if c == "macro_factor_count":
            disp[c] = disp[c].apply(lambda v: f"{int(v)}/4" if pd.notna(v) else "—")
        else:
            disp[c] = disp[c].apply(lambda v: f"{v:+.2f}" if pd.notna(v) else "—")

    st.dataframe(disp, hide_index=True, use_container_width=True,
                 height=min(600, 42 + 34 * len(disp)))


def render(ctx: PageContext) -> None:
    page = get_page("scoring")
    color = section_color(page["color_key"])

    render_top_tabs(page["id"])

    data = load_pulsar()
    if data is None:
        render_page_header(page, latest_date="—",
                           viewing="Scoring sheets not found in DATA.xlsx")
        render_missing_data_warning(
            required=["Scoring sheets in DATA.xlsx: Macro_GDP, Macro_CPI, etc."],
            missing=["Scoring model sheets not found"],
            message="The global scoring model requires sheets Macro_GDP, "
                    "Macro_CPI, Macro_Fiscal, Rates_10Y, Equity_ToT, "
                    "Equity_EPS and Equity_Prices in DATA.xlsx. Equity_FCI is "
                    "optional non-scoring context.",
        )
        render_section_footer(page)
        return

    # Determine the latest available date across all sheets
    sheet_info = []
    all_dates = []
    for k, sdf in data.items():
        if len(sdf):
            all_dates.append(sdf.index.max())
            sheet_info.append({"Sheet": k, "Latest date": str(sdf.index.max().date()),
                               "Rows": len(sdf), "Cols": sdf.shape[1]})
    asof_raw = max(all_dates) if all_dates else None

    from models.scoring.engine import determine_scoring_asof
    asof_info = determine_scoring_asof(data)
    if asof_info["asof_date"] is None:
        render_page_header(page, latest_date="—",
            viewing="No eligible production scoring dates available.")
        from charts.common import render_missing_data_warning
        render_missing_data_warning(
            message="<b>Scoring unavailable.</b> All available scoring observation "
                    "dates are in the future or no data was loaded. "
                    "No rates or equity scores will be calculated.")
        render_section_footer(page)
        return

    asof = pd.Timestamp(asof_info["asof_date"])
    future_rows = asof_info.get("future_rows", [])

    render_page_header(page, latest_date=asof.strftime("%b %d, %Y").upper(),
                       viewing=f"Production scoring as of: {asof.date()}"
                               f"{' · ' + str(len(future_rows)) + ' future-dated rows excluded' if future_rows else ''}")

    render_explanation_box(
        "Cross-sectional scoring model",
        "Ranks sovereign bond markets and equity indices on a blend of "
        "<b>macro</b> factors (GDP, CPI, fiscal balance) and <b>market</b> "
        "factors (momentum, carry, real yield for rates; terms of trade, "
        "EPS revisions for equities). Each scoring factor is z-scored "
        "cross-sectionally so the ranking is relative, not absolute. A positive "
        "composite score means higher-ranked relative to peers using "
        "observations available on or before the production model as-of date. "
        "FCI is displayed separately as context and has no effect on the score.",
    )

    if future_rows:
        with st.expander(f"⚠ {len(future_rows)} future-dated scoring rows excluded"):
            st.caption("These rows are dated after the current production date "
                       "and are excluded pending classification.")
            st.dataframe(pd.DataFrame(future_rows), hide_index=True,
                         use_container_width=True)

    # Per-sheet freshness table
    with st.expander("DATA.xlsx scoring-sheet freshness", expanded=False):
        st.dataframe(pd.DataFrame(sheet_info), hide_index=True,
                     use_container_width=True)

    from models.scoring.engine import (
        build_equity_fci_context, score_rates, score_equity,
        RATES_UNIVERSE, EQUITY_UNIVERSE,
    )

    st.caption(f"Scoring as of {asof.date()}")

    # Weight sliders
    tab_rates, tab_equity = st.tabs(["Global Rates Scoring", "Global Equity Scoring"])

    with tab_rates:
        st.markdown("<div style='font-size:11px;color:#888;letter-spacing:0.1em;"
                    "text-transform:uppercase;margin:0.4rem 0;'>"
                    "Factor weights</div>", unsafe_allow_html=True)
        rc1, rc2 = st.columns(2)
        with rc1:
            w_macro_r = st.slider("Macro weight", 0.0, 1.0, 0.5, 0.1,
                                  key="score_r_macro")
        with rc2:
            w_mkt_r = st.slider("Markets weight", 0.0, 1.0, 0.5, 0.1,
                                key="score_r_mkt")

        try:
            r_scores = score_rates(data, asof, {"macro": w_macro_r, "markets": w_mkt_r})
            render_kpi_strip([
                {"label": "Top pick (rates)", "value": r_scores.iloc[0]["country"],
                 "sub": f"Score {r_scores.iloc[0]['score']:+.2f}", "accent": "#5fb04f"},
                {"label": "Bottom pick", "value": r_scores.iloc[-1]["country"],
                 "sub": f"Score {r_scores.iloc[-1]['score']:+.2f}", "accent": "#d04848"},
                {"label": "Panel size", "value": str(len(r_scores)),
                 "sub": f"of {len(RATES_UNIVERSE)} markets"},
            ])
            _render_scores_table(r_scores, "country", key="rates_scores")
        except Exception as e:
            st.error(f"Rates scoring error: {e}")

    with tab_equity:
        st.markdown("<div style='font-size:11px;color:#888;letter-spacing:0.1em;"
                    "text-transform:uppercase;margin:0.4rem 0;'>"
                    "Factor weights</div>", unsafe_allow_html=True)
        ec1, ec2 = st.columns(2)
        with ec1:
            w_macro_e = st.slider("Macro weight", 0.0, 1.0, 0.5, 0.1,
                                  key="score_e_macro")
        with ec2:
            w_eps_e = st.slider("EPS weight", 0.0, 1.0, 0.5, 0.1,
                                key="score_e_eps")

        try:
            e_scores = score_equity(data, asof, {"macro": w_macro_e, "eps": w_eps_e})
            eligible_scores = e_scores.loc[e_scores["rank_eligible"]].copy()
            partial_names = e_scores.loc[e_scores["status"] == "Partial", "name"].tolist()
            missing_names = e_scores.loc[e_scores["status"] == "Missing data", "name"].tolist()
            top = eligible_scores.iloc[0] if not eligible_scores.empty else None
            bottom = eligible_scores.iloc[-1] if not eligible_scores.empty else None
            render_kpi_strip([
                {"label": "Top pick (equity)", "value": top["name"] if top is not None else "—",
                 "sub": f"Score {top['score']:+.2f}" if top is not None else "No valid score",
                 "accent": "#5fb04f"},
                {"label": "Bottom pick", "value": bottom["name"] if bottom is not None else "—",
                 "sub": f"Score {bottom['score']:+.2f}" if bottom is not None else "No valid score",
                 "accent": "#d04848"},
                {"label": "Ranking-ready panel", "value": str(len(eligible_scores)),
                 "sub": f"{len(partial_names)} Partial · {len(EQUITY_UNIVERSE)} requested"},
            ])
            if partial_names:
                st.caption(
                    "Partial (provisional score, excluded from headline ranking): "
                    + ", ".join(partial_names)
                    + ". One or more of the four required macro factors or EPS is "
                      "missing. No missing input is replaced by a proxy or zero."
                )
            if missing_names:
                st.caption(
                    "Missing data: " + ", ".join(missing_names) + ". These indices remain in "
                    "the requested universe but are excluded from top/bottom ranking until their "
                    "own macro, cash-index price and BEST_EPS/1FY inputs are present. No proxy or "
                    "renamed series is used."
                )
            _render_scores_table(e_scores, "name", key="eq_scores")

            st.markdown(
                "<div style='font-size:11px;color:#888;letter-spacing:0.1em;"
                "text-transform:uppercase;margin:1rem 0 0.35rem;'>"
                "FCI context · not used in Equity Score</div>",
                unsafe_allow_html=True,
            )
            st.caption(
                "The four supplied regional FCI series are shown at their own latest "
                "source dates. They are not mapped to individual indices, z-scored, "
                "filled across regions, or used in ranking and backtesting."
            )
            fci_context = build_equity_fci_context(data, asof)
            fci_display = fci_context.rename(columns={
                "region": "Region",
                "ticker": "Workbook ticker",
                "latest_value": "Latest value",
                "source_date": "Source date",
                "status": "Status",
            })
            fci_display["Latest value"] = fci_display["Latest value"].apply(
                lambda v: f"{v:.3f}" if pd.notna(v) else "—"
            )
            fci_display["Source date"] = fci_display["Source date"].apply(
                lambda v: str(v) if v is not None else "—"
            )
            st.dataframe(
                fci_display,
                hide_index=True,
                use_container_width=True,
                height=min(210, 42 + 34 * len(fci_display)),
            )
        except Exception as e:
            st.error(f"Equity scoring error: {e}")

    render_model_note(
        "Scoring methodology",
        "<b>Rates:</b> Macro pillar = mean(GDP_z, CPI_z inverted, Fiscal_z). "
        "Markets pillar = mean(3M momentum_z inverted, carry_z, real yield_z). "
        "Composite = weighted blend.<br>"
        "<b>Equity:</b> Macro pillar = mean(Growth_z, CPI_z inv, Fiscal_z, "
        "ToT momentum_z). If a macro factor is unavailable, a provisional "
        "Partial score is calculated from the observed macro factors but excluded "
        "from headline top/bottom ranking; Ready requires all four macro factors "
        "plus EPS. EPS = 3M change in FY1 bottom-up EPS, "
        "z-scored. Composite = weighted blend. All z-scores are cross-sectional "
        "(across the panel on each date), not time-series. At the default 50% "
        "Macro / 50% EPS weights, each of the four equally weighted Macro factors "
        "contributes 12.5% of the total score. FCI remains a separate raw context "
        "panel and contributes 0%.",
    )

    render_section_footer(page)
