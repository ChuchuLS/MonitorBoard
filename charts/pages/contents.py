"""
charts/pages/contents.py
========================
Contents / daily front page. Shows a compact dashboard-state panel and the
full section listing with status pills.
"""
from __future__ import annotations
import html as _html
import logging
import pandas as pd
import streamlit as st
from config.pages import PAGES, STATUS_LABELS, STATUS_COLORS
from config.theme import section_color
from charts.common import (
    render_page_header, render_top_tabs, render_section_footer,
    render_kpi_strip, render_current_reading_list, render_model_status_chip,
)
from ._context import PageContext

logger = logging.getLogger(__name__)

CONTENTS_PAGE_META = {
    "id": "contents", "section": "—", "title": "Contents",
    "color_key": "data_quality",
    "description": "Daily macro / liquidity research pack.",
    "builds_on": None, "next": "liquidity",
}


def render(ctx: PageContext) -> None:
    from data.loader import latest_valid_date
    render_top_tabs("contents")
    lvd = latest_valid_date(ctx.df)
    latest = lvd.strftime("%b %d, %Y").upper() if lvd else "—"
    render_page_header(CONTENTS_PAGE_META, latest_date=latest)

    # ── Today's Dashboard State ──
    st.markdown("<div style='margin:0.4rem 0 0.3rem;font-size:11px;color:#888;"
                "letter-spacing:0.1em;text-transform:uppercase;'>"
                "Today's dashboard state</div>", unsafe_allow_html=True)

    r = ctx.index_result
    from config.theme import REGIME_COLORS
    regime = getattr(r, "latest_regime", "—")
    regime_color = REGIME_COLORS.get(regime, "#888")
    changes = r.changes() if callable(getattr(r, "changes", None)) else {}

    readings = [("Latest valid data date", latest)]
    state_failures: list[str] = []

    def _record_state_failure(label: str, exc: Exception) -> None:
        logger.exception("Contents summary failed: %s", label)
        state_failures.append(f"{label} ({type(exc).__name__})")

    # Liquidity
    if pd.notna(r.latest):
        readings.append(("Composite Liquidity Index",
                         f"<span style='color:{regime_color};'>{r.latest:.1f} ({regime})</span>"))
        for h in ("1w", "1m", "3m"):
            v = changes.get(h)
            if v is not None and pd.notna(v):
                readings.append((f"CLI {h.upper()} change", f"{v:+.1f} pts"))

    # Cross-Asset
    try:
        from data.external_loaders import load_crossasset
        from models.cross_asset.directional import classify_8regime, REGIMES_8, days_in_current_regime
        ca = load_crossasset()
        if ca is not None:
            ca_result = classify_8regime(ca)
            if not ca_result.empty:
                cur = ca_result["regime"].iloc[-1]
                days = days_in_current_regime(ca_result["regime"])
                clabel = REGIMES_8[cur]["label"]
                ccolor = REGIMES_8[cur]["color"]
                readings.append(("Cross-Asset regime",
                                 f"<span style='color:{ccolor};'>{clabel}</span> ({days}d)"))
    except Exception as exc:
        _record_state_failure("Cross-Asset regime", exc)

    # Curve Regime
    try:
        from models.curve_regimes import classify_pair_history, days_in_current_regime as _dicr
        h = classify_pair_history(ctx.df, "nominal", ("2Y", "10Y"), 10)
        if not h.empty and h["regime"].dropna().shape[0]:
            cr = h["regime"].dropna().iloc[-1]
            cr_d = _dicr(h["regime"])
            readings.append(("Nominal 2s10s regime",
                             f"{cr} ({cr_d}d)" if pd.notna(cr) else "—"))
    except Exception as exc:
        _record_state_failure("Nominal 2s10s regime", exc)

    # Rates
    try:
        from models.rate_decomposition import build_us_curve_snapshot
        snap = build_us_curve_snapshot(ctx.df)
        if not snap.empty:
            r10 = snap[snap["tenor"] == "10Y"]
            if not r10.empty:
                row = r10.iloc[0]
                readings.append(("US 10Y", f"{row['nominal']:.2f}% "
                                 f"(1M: {row['nominal_1m_change_bp']:+.0f} bp)"))
    except Exception as exc:
        _record_state_failure("US 10Y summary", exc)

    # Global
    try:
        from models.global_rates import build_slope_ranking, country_1m_changes
        slopes = build_slope_ranking(ctx.df)
        if not slopes.empty:
            readings.append(("Steepest global 2s10s",
                             f"{slopes.iloc[0]['label']} ({slopes.iloc[0]['slope_bp']:+.0f} bp)"))
        chg = country_1m_changes(ctx.df)
        if not chg.empty:
            readings.append(("Top 10Y 1M riser",
                             f"{chg.iloc[0]['label']} ({chg.iloc[0]['change_1m_bp']:+.0f} bp)"))
            readings.append(("Top 10Y 1M faller",
                             f"{chg.iloc[-1]['label']} ({chg.iloc[-1]['change_1m_bp']:+.0f} bp)"))
    except Exception as exc:
        _record_state_failure("Global rates summary", exc)

    # Data quality
    try:
        from data.quality import validate_data, quality_summary
        from config.tickers import TICKERS
        summary = quality_summary(validate_data(ctx.df, TICKERS))
        readings.append(("Data quality",
                         f"{summary['healthy']} healthy / {summary['stale']} stale / "
                         f"{summary['missing']} missing of {summary['total']}"))
    except Exception as exc:
        _record_state_failure("Data-quality summary", exc)

    render_current_reading_list("Today's readings", readings)
    if state_failures:
        st.warning(
            "Some dashboard-state summaries are unavailable: "
            + "; ".join(state_failures)
            + ". No missing reading was replaced with zero or a proxy."
        )

    # ── Content coverage vs reference PDF ──
    try:
        from config.model_roadmap import coverage_summary as _cov
        counts = _cov()
        total = sum(counts.values())
        st.markdown(
            "<div style='margin:1rem 0 0.3rem;font-size:11px;color:#888;"
            "letter-spacing:0.1em;text-transform:uppercase;'>"
            "Content coverage vs reference PDF</div>", unsafe_allow_html=True)
        cov_items = [
            (f"Live", f"<span style='color:#5fb04f;'>{counts.get('Live', 0)}</span>"),
            (f"Partial", f"<span style='color:#d99830;'>{counts.get('Partial', 0)}</span>"),
            (f"Experimental", f"<span style='color:#b184ff;'>{counts.get('Experimental', 0)}</span>"),
            (f"Data missing", f"<span style='color:#d04848;'>{counts.get('Data Missing', 0)}</span>"),
            (f"Not started", f"{counts.get('Not Started', 0)}"),
            (f"Total modules", f"<b>{total}</b>"),
        ]
        render_current_reading_list("Model coverage", cov_items)
        st.caption("See 08 · Model Roadmap for the full content gap analysis.")
    except Exception as exc:
        logger.exception("Contents model-coverage summary failed")
        st.warning(
            "Model coverage is unavailable because its audit failed "
            f"({type(exc).__name__}). The section list below remains available."
        )

    # ── Section listing ──
    st.markdown("<div style='margin:1.2rem 0 0.4rem;font-size:11px;color:#888;"
                "letter-spacing:0.1em;text-transform:uppercase;'>"
                "Sections</div>", unsafe_allow_html=True)
    rows_html = []
    for p in PAGES:
        color = section_color(p["color_key"])
        status = p["status"]
        status_label = STATUS_LABELS[status]
        status_color = STATUS_COLORS[status]
        title = _html.escape(p["title"])
        desc = _html.escape(p["description"])
        num = _html.escape(p["section"])
        rows_html.append(
            f"<div style='display:grid;grid-template-columns:52px 1fr 140px;"
            f"gap:14px;padding:10px 12px;border:1px solid #1a1a1a;"
            f"border-left:3px solid {color};border-radius:4px;"
            f"margin-bottom:8px;background:#0d0d0d;align-items:baseline;'>"
            f"<div style='font-size:20px;font-weight:700;color:{color};'>{num}</div>"
            f"<div><div style='font-size:14px;font-weight:700;color:#fff;'>{title}</div>"
            f"<div style='font-size:11.5px;color:#aaa;margin-top:3px;line-height:1.5;'>{desc}</div></div>"
            f"<div style='text-align:right;'>"
            f"<span style='display:inline-block;padding:3px 10px;border:1px solid {status_color}55;"
            f"color:{status_color};border-radius:3px;font-size:10px;letter-spacing:0.1em;"
            f"text-transform:uppercase;font-weight:700;'>{status_label}</span></div></div>"
        )
    st.markdown("".join(rows_html), unsafe_allow_html=True)

    legend_bits = " &nbsp; ".join(
        f"<span style='color:{STATUS_COLORS[k]};'>■</span> "
        f"<span style='color:#aaa;font-size:11px;letter-spacing:0.06em;"
        f"text-transform:uppercase;'>{STATUS_LABELS[k]}</span>"
        for k in ["live", "partial", "scaffold", "experimental", "requires"]
    )
    st.markdown(f"<div style='margin-top:10px;font-size:11px;'>"
                f"<span style='color:#666;letter-spacing:0.1em;text-transform:uppercase;'>"
                f"Legend</span> &nbsp;{legend_bits}</div>", unsafe_allow_html=True)

    # ── Export download (lazy) ──
    with st.expander("Export research pack", expanded=False):
        st.caption("Download the complete linked Board as a 16:9 PDF. The file "
                   "contains the cover, contents, all registered pages, PDF "
                   "bookmarks and internal navigation.")
        if ctx.pdf_export_builder:
            try:
                st.download_button(
                    "⬇  Download complete Board PDF",
                    data=ctx.pdf_export_builder,
                    file_name=ctx.pdf_export_name,
                    mime="application/pdf",
                    key="contents_export_board_pdf",
                    use_container_width=True,
                )
            except Exception as e:
                st.error(f"PDF export failed: {e}")

        st.caption("Optional machine-readable and standalone HTML exports")
        ec1, ec2 = st.columns(2)
        with ec1:
            if st.button("Generate HTML report", key="gen_html"):
                with st.spinner("Building HTML report..."):
                    try:
                        from scripts.export_research_pack_html import build_html
                        html_str, filename = build_html()
                        st.download_button("Download HTML", data=html_str,
                                           file_name=filename, mime="text/html",
                                           key="dl_html")
                    except Exception as e:
                        st.error(f"Export failed: {e}")
        with ec2:
            if st.button("Generate JSON snapshot", key="gen_json"):
                with st.spinner("Building snapshot..."):
                    try:
                        from scripts.export_research_pack_snapshot import build_snapshot
                        import json
                        snap = build_snapshot()
                        st.download_button("Download JSON", key="dl_json",
                                           data=json.dumps(snap, indent=2, default=str),
                                           file_name="snapshot.json",
                                           mime="application/json")
                    except Exception as e:
                        st.error(f"Export failed: {e}")

    render_section_footer(CONTENTS_PAGE_META)
