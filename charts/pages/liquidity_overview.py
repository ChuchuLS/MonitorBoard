"""
charts/pages/liquidity_overview.py
==================================
Section 00 — Liquidity Overview. Wraps the existing render_index_page /
render_summary_panel (untouched) inside the new PDF-style shell.

The Composite Liquidity Index computation is NOT modified in Phase 1. This
module only adds the header, KPI strip, explanation box and footer around it.
"""

from __future__ import annotations

import logging

import pandas as pd
import streamlit as st

from config.pages import get_page
from config.theme import section_color, REGIME_COLORS

from charts.common import (
    render_page_header, render_top_tabs, render_kpi_strip,
    render_explanation_box, render_section_footer,
)
from charts.liquidity import render_driver_cards, render_index_page
from charts.funding import render_xccy_summary
from data.loader import source_signature
from index.methodology import INDEX_METHODOLOGY

from ._context import PageContext

logger = logging.getLogger(__name__)


def render(ctx: PageContext) -> None:
    page = get_page("liquidity")
    color = section_color(page["color_key"])

    render_top_tabs(page["id"])
    r = ctx.index_result
    published = r.index.dropna()
    published_date = published.index[-1] if len(published) else None
    raw_latest_date = ctx.df.index.max() if len(ctx.df) else None
    latest = (published_date.strftime("%b %d, %Y").upper()
              if published_date is not None else "—")
    viewing = (
        f"{ctx.start_date.strftime('%b %Y').upper()} → "
        f"{ctx.end_date.strftime('%b %Y').upper()} · "
        f"raw workbook latest {raw_latest_date.date() if raw_latest_date is not None else '—'}"
    )
    render_page_header(page, latest_date=latest, viewing=viewing)

    regime = getattr(r, "latest_regime", "—")
    regime_color = REGIME_COLORS.get(regime, "#9aa0a6")

    def _fmt_change(v, unit="pts"):
        if v is None or pd.isna(v):
            return "—"
        return f"{v:+.1f} {unit}"

    changes = r.changes() if callable(getattr(r, "changes", None)) else {}
    kpi_cards = [
        {"label": "Composite Liquidity Index",
         "value": f"{r.latest:.1f}" if pd.notna(r.latest) else "—",
         "sub": f"50 = neutral · regime <b style='color:{regime_color}'>{regime}</b>",
         "accent": color},
        {"label": "1-week change",
         "value": _fmt_change(changes.get("1w")),
         "sub": "vs 5 business days ago"},
        {"label": "1-month change",
         "value": _fmt_change(changes.get("1m")),
         "sub": "vs 21 business days ago"},
        {"label": "3-month change",
         "value": _fmt_change(changes.get("3m")),
         "sub": "vs 63 business days ago"},
    ]
    render_kpi_strip(kpi_cards)

    contribution_sum = None
    if getattr(r, "bucket_terms", None) is not None and published_date is not None:
        try:
            contribution_sum = float(r.bucket_terms.loc[published_date].sum())
        except Exception:
            contribution_sum = None
    reconciliation_gap = (
        contribution_sum - (float(r.latest) - 50.0)
        if contribution_sum is not None and pd.notna(r.latest) else None
    )
    reconciliation_text = (
        f"{reconciliation_gap:+.8f} index points"
        if reconciliation_gap is not None
        else "unavailable"
    )
    render_explanation_box(
        "Version and data-update reconciliation",
        f"<b>Methodology:</b> {INDEX_METHODOLOGY['version']} — unchanged in this update. "
        f"<b>Published model date:</b> {published_date.date() if published_date is not None else '—'}. "
        f"<b>Raw workbook latest row:</b> {raw_latest_date.date() if raw_latest_date is not None else '—'}. "
        f"<b>Source hash:</b> <code>{source_signature()[:12]}</code>. "
        f"<b>Bucket reconciliation gap:</b> {reconciliation_text}."
    )
    st.caption(
        "The calculation formula and methodology version are unchanged. Updating or "
        "revising Bloomberg source observations can change recent index values and can "
        "advance the latest published model date; this is a data-vintage effect, not a "
        "silent formula change."
    )

    render_explanation_box(
        "What this section shows",
        "A raw-indicator liquidity gauge, z-scored across five buckets "
        "(money-market funding, dollar funding, credit, central-bank reserves, "
        "market liquidity) and rescaled so <b>50 = neutral</b> and higher = "
        "looser. The panels below decompose today's reading into bucket and "
        "component contributions, benchmark it against Bloomberg FCI and the "
        "Chicago Fed NFCI, and expose the full methodology audit trail. "
        "The <b>Export to Excel</b> button ships a multi-sheet workbook of "
        "index, buckets, components, contributions, reconciliation, "
        "forward-fill audit and methodology parameters.",
    )

    # Build export bytes lazily — only if the user is on this page.
    export_bytes = ctx.export_builder() if ctx.export_builder else None

    # The research-pack shell above already renders level and horizon changes.
    # Keep only the contributor cards here so the four headline KPIs appear
    # exactly once on the page.
    render_driver_cards(r)
    st.markdown("<div style='height:0.8rem;'></div>", unsafe_allow_html=True)
    render_index_page(
        ctx.df, ctx.dff, r, ctx.audit_bundle,
        export_bytes=export_bytes,
        export_name=ctx.export_name,
    )

    # ── Compact XCCY basis summary; full 5×2 history is on FX 07. ──
    try:
        render_xccy_summary(ctx.dff)
    except Exception as exc:
        logger.exception("Failed to render the Liquidity XCCY summary")
        st.warning(
            "Dollar-funding / XCCY summary is unavailable because the audit "
            f"failed ({type(exc).__name__}). This does not mean the source "
            "series are zero or absent."
        )

    # ── CLI Rolling Correlations (only if target data exists) ──
    try:
        from models.cli_correlations import available_targets, build_all_correlations, CORR_TARGETS
        targets = available_targets(ctx.df)
        if targets:
            import plotly.graph_objects as go
            from config.theme import BG, GRID, TEXT_DIM

            st.markdown(
                "<div style='margin:1.2rem 0 0.3rem;font-size:11px;color:#888;"
                "letter-spacing:0.1em;text-transform:uppercase;'>"
                "CLI rolling correlations (20-day)</div>",
                unsafe_allow_html=True,
            )

            corrs = build_all_correlations(ctx.df, r.index, window=20)
            if corrs:
                COLORS = {"SPX": "#3b82f6", "HSI": "#ef4444", "BTC": "#f97316"}
                fig = go.Figure()
                for key, series in corrs.items():
                    label = CORR_TARGETS[key]["label"]
                    fig.add_trace(go.Scatter(
                        x=series.index, y=series, mode="lines",
                        line=dict(color=COLORS.get(key, "#888"), width=1.4),
                        name=f"CLI vs {label}",
                    ))
                fig.add_hline(y=0, line=dict(color="#333", width=0.5, dash="dot"))
                fig.update_layout(
                    template="plotly_dark", paper_bgcolor=BG, plot_bgcolor=BG,
                    font=dict(family="Inter, system-ui, sans-serif", size=10, color=TEXT_DIM),
                    height=300, showlegend=True,
                    legend=dict(orientation="h", y=1.02, x=0, font=dict(size=10, color="#aaa")),
                    margin=dict(l=50, r=20, t=30, b=25),
                    yaxis=dict(title="Correlation", gridcolor=GRID, range=[-1, 1]),
                    xaxis=dict(showgrid=False),
                )
                st.plotly_chart(fig, use_container_width=True, key="cli_corrs",
                                config={"displayModeBar": False})

                # Show which targets are live vs missing
                live_keys = list(corrs.keys())
                all_keys = list(CORR_TARGETS.keys())
                missing_keys = [k for k in all_keys if k not in live_keys]
                cap_parts = [
                    "20-day rolling correlation between CLI level changes and "
                    "asset log returns. Positive = asset tends to rise when "
                    "liquidity loosens.",
                ]
                if missing_keys:
                    missing_labels = [CORR_TARGETS[k]["label"] for k in missing_keys]
                    cap_parts.append(
                        f"Not shown (data missing): {', '.join(missing_labels)}. "
                        "Add tickers to DATA.xlsx to enable.")
                st.caption(" ".join(cap_parts))
        else:
            # Data missing — show honest status
            from charts.common import render_missing_data_warning
            render_missing_data_warning(
                required=["HSI INDEX (Hang Seng)", "XBTUSD BGN Curncy (Bitcoin)"],
                missing=["HSI INDEX", "XBTUSD / BTC price"],
                message=(
                    "<b>CLI rolling correlations</b> are not shown because "
                    "neither HSI nor Bitcoin price data is in DATA.xlsx. "
                    "Add these tickers to the Bloomberg BDH pull to enable "
                    "the correlation charts."
                ),
            )
    except Exception:
        pass

    # ── Q-list Answering Panel ──
    try:
        from models.qlist import build_qlist

        st.markdown(
            "<div style='margin:1.4rem 0 0.3rem;font-size:11px;color:#888;"
            "letter-spacing:0.1em;text-transform:uppercase;'>"
            "Dashboard Q&amp;A</div>",
            unsafe_allow_html=True,
        )

        qlist = build_qlist(ctx.df, r, r.index)

        STATUS_COLORS_Q = {
            "real_data": "#5fb04f", "partial": "#d99830", "data_missing": "#d04848",
        }

        for qa in qlist:
            sc = STATUS_COLORS_Q.get(qa.data_status, "#666")
            with st.expander(f"❓ {qa.question}", expanded=False):
                st.markdown(
                    f"<div style='font-size:13px;color:#fff;font-weight:700;"
                    f"margin-bottom:6px;'>{qa.answer}</div>"
                    f"<div style='font-size:10px;color:#888;margin-bottom:4px;'>"
                    f"Evidence: <code>{qa.evidence}</code></div>"
                    f"<div style='display:inline-block;padding:2px 8px;"
                    f"border:1px solid {sc}55;color:{sc};border-radius:3px;"
                    f"font-size:9px;font-weight:700;text-transform:uppercase;'>"
                    f"{qa.data_status.replace('_', ' ')}</div>",
                    unsafe_allow_html=True,
                )
                if qa.details:
                    for d in qa.details:
                        st.markdown(f"<div style='font-size:11px;color:#aaa;"
                                    f"margin-left:12px;'>• {d}</div>",
                                    unsafe_allow_html=True)
    except Exception:
        pass

    render_section_footer(page)
