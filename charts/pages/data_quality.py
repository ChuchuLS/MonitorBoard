"""
charts/pages/data_quality.py
============================
Section 07 — Data Quality & Methodology.

Ordering (Phase 1.5 cleanup):
  1. All data source status (external audit FIRST)
  2. Data freshness warnings
  3. DATA.xlsx ticker coverage
  4. Composite Liquidity Index methodology & audit trail
  5. Forward-fill audit
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import streamlit as st

from config.pages import get_page, DATA_SOURCES
from config.theme import ACCENT_GREEN, ACCENT_AMBER, ACCENT_RED
from config.tickers import TICKERS

from charts.common import (
    render_page_header, render_top_tabs, render_kpi_strip,
    render_explanation_box, render_missing_data_warning, render_section_footer,
)
from data.loader import load_meta, cache_status_label
from data.quality import validate_data, quality_summary, STALE_BDAYS
from index.methodology import INDEX_METHODOLOGY

from ._context import PageContext

# Required scoring-model sheets expected inside DATA.xlsx
REQUIRED_SCORING_SHEETS = ["Macro_GDP", "Macro_CPI", "Macro_Fiscal", "Rates_10Y",
                           "Equity_ToT", "Equity_FCI", "Equity_EPS", "Equity_Prices"]

# Cross-asset columns required in DATA.xlsx Sheet1
REQUIRED_CROSSASSET_COLS = ["SPX INDEX", "USGG10YR INDEX", "DXY CURNCY"]
REQUIRED_FICC_COLS = ["USGG10YR INDEX", "DXY CURNCY", "SPX INDEX",
                      "USYC2Y10 INDEX", "USGGBE10 INDEX", "USGGT10Y INDEX",
                      "MOVE INDEX", "FXJPEMCS INDEX", "JYBSS12M CURNCY"]


def _file_hash(path: Path) -> str:
    if not path.exists():
        return "—"
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:16] + "…"


def render(ctx: PageContext) -> None:
    page = get_page("data_quality")

    render_top_tabs(page["id"])
    latest_date = ctx.df.index.max().date()
    render_page_header(page, latest_date=str(latest_date))

    render_explanation_box(
        "Trust chain",
        "The dashboard reads one source-of-truth workbook, <b>DATA.xlsx</b>. "
        "Sheet1 supplies daily market data and model inputs (148 columns). "
        "Additional sheets (Macro_GDP, Macro_CPI, etc.) supply the global "
        "scoring model. This page audits workbook freshness, required Sheet1 "
        "columns, required scoring sheets, ticker coverage, parquet cache, "
        "and the Composite Liquidity Index methodology.",
    )

    # ==================================================================
    # 1. DATA.xlsx WORKBOOK SECTIONS AUDIT
    # ==================================================================
    st.markdown(
        "<div style='margin:0.8rem 0 0.4rem;font-size:11px;color:#888;"
        "letter-spacing:0.1em;text-transform:uppercase;'>"
        "DATA.xlsx workbook sections</div>",
        unsafe_allow_html=True,
    )

    fpath = Path("data/DATA.xlsx")
    exists = fpath.exists()
    fhash = _file_hash(fpath) if exists else "—"

    # Read scoring sheet metadata via load_pulsar
    from data.external_loaders import load_pulsar
    scoring_data = load_pulsar() if exists else None
    scoring_first, scoring_last, scoring_rows, scoring_cols = "—", "—", 0, 0
    if scoring_data:
        all_d = [d.index.max() for d in scoring_data.values() if len(d)]
        all_s = [d.index.min() for d in scoring_data.values() if len(d)]
        if all_d:
            scoring_last = str(max(all_d).date())
        if all_s:
            scoring_first = str(min(all_s).date())
        scoring_rows = sum(len(d) for d in scoring_data.values())
        scoring_cols = sum(d.shape[1] for d in scoring_data.values())

    # Check required Sheet1 columns
    all_req_cols = sorted(set(REQUIRED_CROSSASSET_COLS + REQUIRED_FICC_COLS))
    present_cols = set(str(c).strip() for c in ctx.df.columns)
    missing_cols = [c for c in all_req_cols if c not in present_cols]

    # Check required scoring sheets
    try:
        import openpyxl
        wb = openpyxl.load_workbook(fpath, read_only=True)
        sheet_names = set(wb.sheetnames)
        wb.close()
        missing_sheets = [s for s in REQUIRED_SCORING_SHEETS if s not in sheet_names]
    except Exception:
        missing_sheets = ["(could not read sheets)"]

    audit_rows = [
        {
            "Source": "sheet1_market",
            "File": "data/DATA.xlsx",
            "Sheet": "Sheet1",
            "Exists": "✓" if exists else "✗",
            "Hash": fhash,
            "First date": str(ctx.df.index.min().date()),
            "Latest date": str(ctx.df.index.max().date()),
            "Rows": len(ctx.df),
            "Cols": ctx.df.shape[1],
            "Required": f"{len(all_req_cols)} cross-asset/FICC columns",
            "Missing": ", ".join(missing_cols) if missing_cols else "✓ all present",
            "Role": DATA_SOURCES.get("sheet1_market", {}).get("role", ""),
            "Pages": ", ".join(DATA_SOURCES.get("sheet1_market", {}).get("pages", [])),
        },
        {
            "Source": "scoring_sheets",
            "File": "data/DATA.xlsx",
            "Sheet": "Macro_GDP … Equity_Prices",
            "Exists": "✓" if exists and not missing_sheets else "✗",
            "Hash": "— (same workbook)",
            "First date": scoring_first,
            "Latest date": scoring_last,
            "Rows": scoring_rows,
            "Cols": scoring_cols,
            "Required": f"{len(REQUIRED_SCORING_SHEETS)} scoring sheets",
            "Missing": (", ".join(missing_sheets)
                        if missing_sheets else "✓ all present"),
            "Role": DATA_SOURCES.get("scoring_sheets", {}).get("role", ""),
            "Pages": ", ".join(DATA_SOURCES.get("scoring_sheets", {}).get("pages", [])),
        },
    ]

    st.dataframe(pd.DataFrame(audit_rows), hide_index=True,
                 use_container_width=True, height=min(200, 42 + 34 * len(audit_rows)))

    # ==================================================================
    # 2. FRESHNESS WARNING (scoring sheets vs Sheet1)
    # ==================================================================
    sheet1_latest = ctx.df.index.max().date()
    if scoring_last != "—":
        try:
            sc_date = pd.Timestamp(scoring_last).date()
            gap = (sheet1_latest - sc_date).days
            if gap > 5:
                render_missing_data_warning(
                    message=f"<b>Scoring sheets lag Sheet1 by {gap} days</b><br>"
                            f"Sheet1 latest: {sheet1_latest} · "
                            f"Scoring sheets latest: {sc_date}")
        except Exception:
            pass

    # ==================================================================
    # 3. DATA.xlsx TICKER COVERAGE
    # ==================================================================
    st.markdown(
        "<div style='margin:1.2rem 0 0.4rem;font-size:11px;color:#888;"
        "letter-spacing:0.1em;text-transform:uppercase;'>"
        "DATA.xlsx ticker coverage</div>",
        unsafe_allow_html=True,
    )

    meta = load_meta()
    status = cache_status_label()
    status_color = (ACCENT_GREEN if status.startswith(("Fresh", "Rebuilt"))
                    else ACCENT_AMBER)

    report = validate_data(ctx.df, TICKERS)
    summary = quality_summary(report)

    render_kpi_strip([
        {"label": "Source file", "value": "DATA.xlsx", "sub": "manual Bloomberg pull"},
        {"label": "Parquet cache", "value": status,
         "sub": f"end date: {meta.get('end_date', str(latest_date))}",
         "accent": status_color},
        {"label": "Latest data date", "value": str(latest_date),
         "sub": f"{len(ctx.df):,} rows · {ctx.df.shape[1]:,} cols"},
        {"label": "Tickers healthy", "value": f"{summary['healthy']}",
         "sub": f"of {summary['total']} tracked", "accent": ACCENT_GREEN},
        {"label": "Stale / missing",
         "value": f"{summary['stale']} / {summary['missing']}",
         "sub": f"stale = no obs in {STALE_BDAYS} bdays",
         "accent": ACCENT_AMBER if summary['stale'] else "#fff"},
    ])

    show = st.radio("FILTER", ["All", "Problems only (missing or stale)"],
                    index=0, horizontal=True, key="dq_filter")
    table = report.copy()
    if show.startswith("Problems"):
        table = table[(~table["exists"]) | (table["stale"])]

    table["last_date"] = pd.to_datetime(table["last_date"]).dt.date.astype("string")
    table["last_date"] = table["last_date"].fillna("—")
    table["missing_pct"] = (table["missing_pct"] * 100)
    disp = table.rename(columns={
        "key": "Key", "ticker": "Bloomberg ticker", "exists": "Exists",
        "last_date": "Last date", "missing_pct": "Missing %", "n_obs": "Obs",
        "stale": "Stale"})
    disp = disp[["Key", "Bloomberg ticker", "Exists", "Last date",
                 "Missing %", "Obs", "Stale"]]

    def _row_style(row):
        if not row["Exists"]:
            return ["background-color: rgba(208,72,72,0.12)"] * len(row)
        if row["Stale"]:
            return ["background-color: rgba(217,152,48,0.12)"] * len(row)
        return [""] * len(row)

    st.dataframe(
        disp.style.apply(_row_style, axis=1).format(
            {"Missing %": "{:.1f}", "Obs": "{:,}"}, na_rep="—"),
        hide_index=True, use_container_width=True, height=460)
    st.caption(
        "Red = ticker absent · amber = stale. Missing tickers degrade "
        "gracefully — the index and charts skip them.")

    # ==================================================================
    # 4. METHODOLOGY AUDIT
    # ==================================================================
    st.markdown(
        "<div style='margin:1.6rem 0 0.4rem;font-size:11px;color:#888;"
        "letter-spacing:0.1em;text-transform:uppercase;'>"
        "Composite Liquidity Index — methodology & audit trail</div>",
        unsafe_allow_html=True,
    )
    audit = ctx.audit_bundle.get("methodology", {}) if ctx.audit_bundle else {}
    ver = audit.get("version", INDEX_METHODOLOGY.get("version", "?"))
    st.markdown(
        f"<div style='font-size:13px;color:#fff;margin-bottom:6px;'>"
        f"Methodology Version: <b>{ver}</b></div>"
        f"<div style='font-size:11px;color:#888;margin-bottom:10px;'>"
        f"{INDEX_METHODOLOGY.get('description','')}</div>",
        unsafe_allow_html=True,
    )
    params = {
        "Version": ver,
        "Z-score window": audit.get("z_window", INDEX_METHODOLOGY.get("z_window")),
        "Min periods": audit.get("z_min_periods", INDEX_METHODOLOGY.get("z_min_periods")),
        "Z clip": f"±{audit.get('z_clip', INDEX_METHODOLOGY.get('z_clip'))}",
        "Min unique observations": audit.get("z_min_unique",
                                             INDEX_METHODOLOGY.get("z_min_unique")),
        "Min buckets": audit.get("min_available_buckets",
                                 INDEX_METHODOLOGY.get("min_available_buckets")),
        "Min components": audit.get("min_available_components",
                                    INDEX_METHODOLOGY.get("min_available_components")),
        "Min components / bucket": audit.get("min_components_per_bucket",
            INDEX_METHODOLOGY.get("min_components_per_bucket")),
        "Warm-up (bdays)": audit.get("warmup_days_after_first_valid",
            INDEX_METHODOLOGY.get("warmup_days_after_first_valid")),
        "Latest DATA.xlsx hash": str(audit.get("data_hash", "n/a"))[:16] + "…",
        "Components on latest date": audit.get("components_on_latest", "—"),
        "Buckets on latest date": audit.get("buckets_on_latest", "—"),
        "Latest index":
            f"{audit.get('latest_index'):.2f}"
            if audit.get("latest_index") is not None else "—",
    }
    pdf_frame = pd.DataFrame(
        {"Parameter": list(params.keys()),
         "Value": [str(v) for v in params.values()]})
    st.dataframe(pdf_frame, hide_index=True, use_container_width=True,
                 height=min(560, 42 + 34 * len(pdf_frame)))

    # ==================================================================
    # 5. FORWARD-FILL AUDIT
    # ==================================================================
    ffa = ctx.audit_bundle.get("ffill_audit") if ctx.audit_bundle else None
    if ffa is not None and len(ffa):
        st.markdown(
            "<div style='margin:1.3rem 0 0.4rem;font-size:11px;color:#888;"
            "letter-spacing:0.1em;text-transform:uppercase;'>"
            "Forward-fill audit</div>",
            unsafe_allow_html=True,
        )
        disp_ffa = ffa.rename(columns={
            "component": "ID", "name": "Component", "frequency": "Freq",
            "max_ffill_days": "Max ffill", "latest_raw_obs": "Latest raw",
            "latest_true_obs": "Latest true obs",
            "days_since_true_obs": "Days since",
            "is_live": "Live", "reason": "Reason",
            "stale_days_1y": "Stale days (1y)",
            "pct_ffilled_1y": "% ffilled (1y)"})
        st.dataframe(
            disp_ffa.style.format({"% ffilled (1y)": "{:.0f}%"}),
            hide_index=True, use_container_width=True, height=460)
        st.caption(
            "Weekly series (Fed reserves/repo) are observed on Wednesdays; "
            "the z-score is computed on those true observations and forward-"
            "filled at most 'Max ffill' business days.")

    render_section_footer(page)
